"""AI2 생성 파이프라인 (구현명세서 §6.1 · §6.4 · §6.5 · §9.1 · §8.4).

    R1(후보 3 병렬, A.1) → R2(후보 3 병렬, A.1 + [수정 요청]) → R3(후보 1, A.1b 최대 제약)
    → 그래도 없으면 neutral_fallback

각 라운드는 {생성 → 규칙 검사(§6.4 R-1·R-3·R-4) → checker(VALIDATOR)}이고, **게이트를 통과한
후보 중 인덱스가 가장 작은 것**이 표시된다. 선택은 내용 판단이 아니다 — 같은 게이트를 더 많은
후보에 적용할 뿐이고, 그래서 §1.5-8(판정 코드 금지)에 걸리지 않는다.

**왜 라운드인가**(D-48). v2는 초안 2개(최초 + 재생성 1회)였고 실참가자 4명 중 3명이
fallback으로 끝났다. 시도당 통과율이 가장 낮은 사건(P08)에서 q≈0.43이라 2회로는 fallback
확률이 32%다. 후보를 늘리면 그 확률이 내려가지만(3후보 2라운드면 3.5%) **직렬로 늘리면
시간이 먼저 터진다** — 한 후보가 12–17초다. 그래서 한 라운드 안에서는 병렬로 뽑고, 라운드
사이에서만 정보를 넘긴다.

**R3이 사다리의 마지막 생성이다.** R1·R2가 같은 벽에 부딪히는 사건(사건 자체가 제3자에 대해
말해야 하는 경우 등)에서는 후보를 더 뽑아도 같은 이유로 기각된다. R3은 프롬프트를 A.1b(최대
제약 모드)로 바꿔 **출력 공간 자체를 좁힌다**: 질문을 하지 않으면 R-3이, 사용자에 대해
서술하지 않으면 unsupported_inference가, 맥락 안에서만 쓰면 expansion이 성립할 수 없다.
그래도 실패하면 `neutral_fallback`이다 — 종착지는 그대로다(§9.1 dead-end 금지).

**벽시계 상한**(§0.5 `AI2_DEADLINE_SECONDS`, 기본 45초). 시도 수만으로는 §9.1이 닫히지 않는다
— 느린 제공사 한 번이면 90초 타임아웃 × 후보 수다. 상한은 두 곳에서 걸린다: ① 새 라운드를
시작할 잔여가 없으면 시작하지 않는다 ② 호출 타임아웃을 잔여로 깎는다. 잔여가 checker를
돌릴 수 없을 만큼 남으면 **규칙 계층만으로 판정하고 `checker_skipped`로 남긴다** — 판정
불능의 기존 처리와 같은 자리다(§9.1). 예산 때문에 fallback으로 떨어뜨리지 않는다.

v1.0.1에 있던 normalization 단계는 **삭제됐다**(D-34) — AI2 입력에 focal AI1 원문이 들어가므로
지시 복원이 필요 없다. 이 함수는 User1 **원문**을 받는다.

R-2도 성격이 바뀌었다: 대안 segment의 등장은 위반이 아니라 `alt_overlap` 플래그이고
(§6.4), 재생성을 부르지 않는다.

기록 규약 (§8.1 `generations`)
- 모델을 부른 후보마다 1행. `attempt`는 **라운드 번호**(1·2·3)이고, 한 라운드의 후보들은
  같은 `attempt`를 공유한다(`created_at` 순서가 후보 순서다).
- 표시된 텍스트를 가진 행이 `final=True`이고 세션당 정확히 1행이다.
- 세 상태가 구분된다: `rule_violations` 비어 있지 않음 = 규칙 기각 / `checker_result`가 있고
  `pass=false` = checker 기각 / 둘 다 비어 있는데 `final=False` = **필요 없어 쓰이지 않은
  후보**(앞 후보가 먼저 통과했다).
- fallback은 **별도 행**이다(마지막 라운드 번호를 그대로 쓰고 `fallback_used=True`). 위반한
  초안의 원문을 fallback 문안으로 덮어쓰지 않기 위해서다 — 초안이 남아야 integrity 보고가
  "무엇이 왜 기각됐는지"를 말할 수 있다(초안 §7.9).

⚠ 이 모듈은 `dossier_private`·`assignment`·`pairwise_items`를 import하지 않는다(NT-04).
R-1의 대조 문자열과 R-2의 대안 segment는 호출부(`api/leakage_sources.py`)가 넘긴다.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.dossier_loader import EffectiveAiVisible
from app.core.config import get_settings
from app.llm import checker as checker_module
from app.llm import context, integrity_rules, prompts
from app.llm.gateway.calls import CallFailed, dispatch_model, record_call
from app.llm.integrity_rules import AltSegment, ForbiddenText
from app.models.tables import Generation
from app.notify.discord import NotifyEvent, notify
from app.security import fernet

logger = logging.getLogger(__name__)

#: §6.1 — 라운드당 후보 수 [PI 확정 2026-08-29 · D-48]. R3만 1건이다(제약 모드는 표본
#: 다양성이 목적이 아니라 출력 공간 축소가 목적이다).
CANDIDATES_PER_ROUND = 3

#: 라운드 정의. `(라운드 번호, 프롬프트 키, 후보 수, 직전 라운드 피드백을 싣는가)`.
ROUND_POLICY = 1
ROUND_FEEDBACK = 2
ROUND_CONSTRAINED = 3

#: 새 라운드를 시작할 최소 잔여(초). 관측된 MAIN 호출이 9–14초라, 이보다 적게 남았으면
#: 시작해 봐야 타임아웃으로 끝난다 — 그 시간에 fallback을 띄우는 편이 낫다.
MIN_ROUND_SECONDS = 10.0

#: checker를 부를 최소 잔여(초). 관측된 VALIDATOR 호출이 1–3초다.
MIN_CHECKER_SECONDS = 3.0

#: 호출 자체가 실패한 경우의 기록 코드. 규칙 위반이 아니라 §9.1의 장애 경로다.
CALL_FAILED_CODE = "call_failed"

#: 예산 소진으로 라운드를 시작하지 못한 경우의 기록 코드.
DEADLINE_CODE = "deadline"


@dataclass(frozen=True, slots=True)
class Ai2Outcome:
    """표시할 텍스트와 그 경로. `generations` 최종 행과 1:1이다."""

    text: str
    generation_id: uuid.UUID
    #: 라운드 번호(1·2·3). `generations.attempt`와 같은 값이다.
    attempt: int
    fallback_used: bool
    regenerated: bool
    rule_violations: list[dict[str, Any]] = field(default_factory=list)
    checker_result: dict[str, Any] | None = None
    checker_skipped: bool = False
    #: §6.4 R-2 — 위반이 아니라 기록이다.
    alt_overlap: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class _Candidate:
    """라운드 안의 후보 1건 — `generations` 1행과 1:1."""

    index: int
    generation: Generation
    draft: str | None = None
    rule_violations: list[dict[str, Any]] = field(default_factory=list)
    alt_overlap: list[dict[str, str]] = field(default_factory=list)
    verdict: checker_module.CheckerVerdict | None = None

    @property
    def usable(self) -> bool:
        return (
            self.draft is not None
            and not self.rule_violations
            and self.verdict is not None
            and self.verdict.passed
        )


@dataclass(slots=True)
class _RoundResult:
    round_no: int
    candidates: list[_Candidate]

    @property
    def winner(self) -> _Candidate | None:
        """게이트를 통과한 후보 중 **인덱스가 가장 작은 것**. 내용 비교는 하지 않는다."""
        return next((item for item in self.candidates if item.usable), None)

    def rule_violations(self) -> list[dict[str, Any]]:
        """라운드 전체의 규칙 위반 — 유형 중복은 접는다."""
        merged: dict[str, dict[str, Any]] = {}
        for candidate in self.candidates:
            for item in candidate.rule_violations:
                merged.setdefault(str(item.get("rule")), item)
        return list(merged.values())

    def checker_violations(self) -> list[dict[str, Any]]:
        return [
            item
            for candidate in self.candidates
            if candidate.verdict is not None
            for item in candidate.verdict.violations
        ]

    def first_checker_result(self) -> dict[str, Any] | None:
        for candidate in self.candidates:
            if candidate.verdict is not None and candidate.verdict.result is not None:
                return candidate.verdict.result
        return None

    def any_checker_skipped(self) -> bool:
        return any(
            candidate.verdict is not None and candidate.verdict.skipped
            for candidate in self.candidates
        )


def _new_generation(session: AsyncSession, focal_run_id: uuid.UUID, attempt: int) -> Generation:
    row = Generation(
        focal_run_id=focal_run_id,
        attempt=attempt,
        rule_violations=[],
        alt_overlap=[],
        checker_skipped=False,
        fallback_used=False,
        final=False,
    )
    session.add(row)
    return row


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


async def _run_round(
    session: AsyncSession,
    *,
    focal_run_id: uuid.UUID,
    round_no: int,
    prompt_key: str,
    candidates: int,
    effective: EffectiveAiVisible,
    focal_ai1: str,
    user1: str,
    feedback: str,
    prohibited_inference: Sequence[str],
    forbidden: Sequence[ForbiddenText],
    alt_segments: Sequence[AltSegment],
    deadline: float,
) -> _RoundResult:
    """라운드 1회. 왕복은 동시에, DB 기록은 순서대로(§6.1)."""
    payload = context.build_ai2_payload(
        effective, focal_ai1, user1, feedback=feedback, prompt_key=prompt_key
    )
    budget_ms = max(1, int(_remaining(deadline) * 1000))
    attempts = await asyncio.gather(
        *(
            dispatch_model(
                prompt_key=prompt_key,
                system=payload.system,
                user=payload.user,
                timeout_override_ms=budget_ms,
            )
            for _ in range(candidates)
        )
    )

    # --- 기록 + 규칙 계층 (결정론·무료) ---------------------------------- #
    result = _RoundResult(round_no=round_no, candidates=[])
    for index, attempt in enumerate(attempts, start=1):
        generation = _new_generation(session, focal_run_id, round_no)
        await session.flush()  # llm_calls.generation_id가 이 id를 참조한다(§8.1)
        candidate = _Candidate(index=index, generation=generation)
        result.candidates.append(candidate)
        try:
            call = await record_call(session, attempt, generation_id=generation.id)
        except CallFailed as exc:
            # §9.1 — 동일 request id 1회 재시도는 `dispatch_model`이 이미 했다. 여기서 한 번
            # 더 부르지 않는다: 장애 후보는 그냥 탈락하고 라운드의 나머지가 이어받는다.
            logger.warning("AI2 후보 호출 실패 (R%s #%s): %s", round_no, index, exc)
            candidate.rule_violations = [
                {"rule": CALL_FAILED_CODE, "detail": f"AI2 호출 실패 (R{round_no} #{index})"}
            ]
            generation.rule_violations = candidate.rule_violations
            continue

        draft = call.text
        candidate.draft = draft
        generation.output_text = fernet.encrypt(draft)
        # `allowed`에 payload 전문을 넘긴다 — 이번 호출에서 정당하게 준 문자열은 누출의
        # 증거가 될 수 없다(§6.4 R-1의 "payload에 정당히 포함된 문자열 제외").
        candidate.rule_violations = [
            violation.as_dict()
            for violation in integrity_rules.check_all(draft, forbidden, allowed=payload.joined())
        ]
        # §6.4 R-2 — 기록만 한다. 재생성 판정에 넣지 않는다.
        candidate.alt_overlap = integrity_rules.flag_alt_overlap(draft, alt_segments)
        generation.rule_violations = candidate.rule_violations
        generation.alt_overlap = candidate.alt_overlap

    # --- checker (규칙을 통과한 후보만) ---------------------------------- #
    # 규칙 위반이 이미 있으면 checker를 부르지 않는다 — 판정 결과가 같고(기각) 예산을
    # 아낀다. `checker_result=null` + `rule_violations` 비어 있지 않음이 그 상태의 기록이다.
    clean = [item for item in result.candidates if item.draft is not None and not item.rule_violations]
    if not clean:
        return result

    if _remaining(deadline) < MIN_CHECKER_SECONDS:
        # 예산 소진 — 판정 불능과 같은 자리로 보낸다(§9.1). 규칙 계층만으로 판정한다.
        logger.warning("checker 예산 소진 — 규칙 계층만으로 판정한다 (R%s)", round_no)
        for candidate in clean:
            candidate.verdict = checker_module.skipped_verdict()
            candidate.generation.checker_skipped = True
        return result

    checker_budget_ms = max(1, int(_remaining(deadline) * 1000))
    verdict_attempts = await asyncio.gather(
        *(
            checker_module.dispatch(
                effective=effective,
                focal_ai1=focal_ai1,
                user1=user1,
                draft=candidate.draft or "",
                prohibited_inference=prohibited_inference,
                timeout_override_ms=checker_budget_ms,
            )
            for candidate in clean
        )
    )
    for candidate, attempt in zip(clean, verdict_attempts):
        verdict = await checker_module.absorb(
            session, attempt, generation_id=candidate.generation.id
        )
        candidate.verdict = verdict
        candidate.generation.checker_result = verdict.result
        candidate.generation.checker_skipped = verdict.skipped
    return result


async def run(
    session: AsyncSession,
    *,
    focal_run_id: uuid.UUID,
    effective: EffectiveAiVisible,
    focal_ai1: str,
    user1: str,
    neutral_fallback: str,
    prohibited_inference: Sequence[str] = (),
    forbidden: Sequence[ForbiddenText] = (),
    alt_segments: Sequence[AltSegment] = (),
) -> Ai2Outcome:
    """이 세션의 AI2 1턴. `effective`·`focal_ai1`·`user1` 셋이 곧 §6.2 allowlist다(D-34).

    `forbidden`·`alt_segments`는 **판정·기록용 대조 문자열**이지 payload가 아니다 — 어떤
    프롬프트에도 실리지 않는다(§6.4 · NT-01).
    """
    deadline = time.monotonic() + get_settings().ai2_deadline_seconds
    ladder = (
        (ROUND_POLICY, prompts.AI2_PROMPT_KEY, CANDIDATES_PER_ROUND, False),
        (ROUND_FEEDBACK, prompts.AI2_PROMPT_KEY, CANDIDATES_PER_ROUND, True),
        (ROUND_CONSTRAINED, prompts.AI2_CONSTRAINED_PROMPT_KEY, 1, False),
    )

    feedback = ""
    last: _RoundResult | None = None
    last_round = ROUND_POLICY

    for round_no, prompt_key, candidates, carries_feedback in ladder:
        if round_no > ROUND_POLICY and _remaining(deadline) < MIN_ROUND_SECONDS:
            logger.warning("AI2 예산 소진 — R%s를 시작하지 않는다 (§6.1)", round_no)
            break
        last_round = round_no
        result = await _run_round(
            session,
            focal_run_id=focal_run_id,
            round_no=round_no,
            prompt_key=prompt_key,
            candidates=candidates,
            effective=effective,
            focal_ai1=focal_ai1,
            user1=user1,
            feedback=feedback if carries_feedback else "",
            prohibited_inference=prohibited_inference,
            forbidden=forbidden,
            alt_segments=alt_segments,
            deadline=deadline,
        )
        last = result

        winner = result.winner
        if winner is not None:
            winner.generation.final = True
            return Ai2Outcome(
                text=winner.draft or "",
                generation_id=winner.generation.id,
                attempt=round_no,
                fallback_used=False,
                regenerated=round_no > ROUND_POLICY,
                rule_violations=[],
                checker_result=winner.verdict.result if winner.verdict else None,
                checker_skipped=bool(winner.verdict and winner.verdict.skipped),
                alt_overlap=winner.alt_overlap,
            )

        # §6.4 재생성 피드백 (D-48) — 유형별 지시 + checker span. 규칙 위반의 detail은
        # 싣지 않는다. 조립과 안전성 논증은 `context.render_feedback()`에 있다.
        feedback = context.render_feedback(result.rule_violations(), result.checker_violations())

    rule_violations = last.rule_violations() if last else [
        {"rule": DEADLINE_CODE, "detail": "AI2 예산 안에서 생성을 시작하지 못했다 (§6.1)"}
    ]
    return await _fallback(
        session,
        focal_run_id=focal_run_id,
        attempt=last_round,
        text=neutral_fallback,
        rule_violations=rule_violations,
        alt_overlap=last.candidates[0].alt_overlap if last and last.candidates else [],
        checker_result=last.first_checker_result() if last else None,
        checker_skipped=last.any_checker_skipped() if last else False,
    )


async def _fallback(
    session: AsyncSession,
    *,
    focal_run_id: uuid.UUID,
    attempt: int,
    text: str,
    rule_violations: list[dict[str, Any]],
    alt_overlap: list[dict[str, str]],
    checker_result: dict[str, Any] | None,
    checker_skipped: bool,
) -> Ai2Outcome:
    """§6.5 — 참가자별 사전 작성 fallback. 이 문안은 자산 계약에서 R-3·R-4를 이미 통과했다(NT-21)."""
    generation = _new_generation(session, focal_run_id, attempt)
    generation.output_text = fernet.encrypt(text)
    generation.rule_violations = rule_violations
    generation.alt_overlap = alt_overlap
    generation.checker_result = checker_result
    generation.checker_skipped = checker_skipped
    generation.fallback_used = True
    generation.final = True
    await session.flush()

    await notify(
        NotifyEvent.AI2_FALLBACK_USED,
        "AI2 neutral_fallback 표시",
        attempt=attempt,
        violations=",".join(
            sorted({str(item.get("rule") or item.get("type")) for item in rule_violations})
        )
        or None,
    )
    return Ai2Outcome(
        text=text,
        generation_id=generation.id,
        attempt=attempt,
        fallback_used=True,
        regenerated=attempt > ROUND_POLICY,
        rule_violations=rule_violations,
        checker_result=checker_result,
        checker_skipped=checker_skipped,
        alt_overlap=alt_overlap,
    )
