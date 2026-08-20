"""AI2 생성 파이프라인 (구현명세서 §6.1 · §6.4 · §6.5 · §9.1 · §8.4).

    [1] payload 조립(allowlist §6.2) → [2] AI2 생성(MAIN) → [3] 규칙 검사(§6.4 R-1·R-3·R-4)
    → [4] LLM checker(VALIDATOR) → 위반 시 재생성 1회 → 재위반 시 neutral_fallback

v1.0.1에 있던 normalization 단계는 **삭제됐다**(D-34) — AI2 입력에 focal AI1 원문이 들어가므로
지시 복원이 필요 없다. 이 함수는 User1 **원문**을 받는다.

R-2도 성격이 바뀌었다: 대안 segment의 등장은 위반이 아니라 `alt_overlap` 플래그이고
(§6.4), 재생성을 부르지 않는다.

**사다리의 끝은 언제나 표시 가능한 텍스트다**(§9.1 dead-end 금지). 호출 실패·위반·재위반·
checker 불능 — 어느 경로로 가도 참가자 화면에는 {정상 | 재생성 통과 | neutral_fallback} 중
하나가 뜬다. 세 경로는 참가자에게 구분되지 않지만(§4.7) `generations`·`llm_calls`만으로
사후 복원된다(§8.4 · NT-15).

기록 규약 (§8.1 `generations`)
- 모델을 부른 시도마다 1행. `attempt`는 1(최초)·2(재생성)다.
- 표시된 텍스트를 가진 행이 `final=True`이고 세션당 정확히 1행이다.
- fallback은 **별도 행**이다(마지막 시도 번호를 그대로 쓰고 `fallback_used=True`). 위반한
  초안의 원문을 fallback 문안으로 덮어쓰지 않기 위해서다 — 초안이 남아야 integrity 보고가
  "무엇이 왜 기각됐는지"를 말할 수 있다(초안 §7.9).

⚠ 이 모듈은 `dossier_private`·`assignment`·`pairwise_items`를 import하지 않는다(NT-04).
R-1의 대조 문자열과 R-2의 대안 segment는 호출부(`api/leakage_sources.py`)가 넘긴다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.dossier_loader import EffectiveAiVisible
from app.llm import checker as checker_module
from app.llm import context, integrity_rules, prompts
from app.llm.gateway.calls import CallFailed, call_model
from app.llm.integrity_rules import AltSegment, ForbiddenText
from app.models.tables import Generation
from app.notify.discord import NotifyEvent, notify
from app.security import fernet

logger = logging.getLogger(__name__)

#: §0.5 — AI2 재생성 최대 1회 → neutral fallback.
MAX_ATTEMPTS = 2

#: 호출 자체가 실패한 경우의 기록 코드. 규칙 위반이 아니라 §9.1의 장애 경로다.
CALL_FAILED_CODE = "call_failed"


@dataclass(frozen=True, slots=True)
class Ai2Outcome:
    """표시할 텍스트와 그 경로. `generations` 최종 행과 1:1이다."""

    text: str
    generation_id: uuid.UUID
    attempt: int
    fallback_used: bool
    regenerated: bool
    rule_violations: list[dict[str, Any]] = field(default_factory=list)
    checker_result: dict[str, Any] | None = None
    checker_skipped: bool = False
    #: §6.4 R-2 — 위반이 아니라 기록이다.
    alt_overlap: list[dict[str, str]] = field(default_factory=list)


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
    violation_types: list[str] = []
    last_rule_violations: list[dict[str, Any]] = []
    last_overlap: list[dict[str, str]] = []
    last_verdict: checker_module.CheckerVerdict | None = None
    attempt = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        generation = _new_generation(session, focal_run_id, attempt)
        await session.flush()  # llm_calls.generation_id가 이 id를 참조한다(§8.1)

        payload = context.build_ai2_payload(
            effective, focal_ai1, user1, violation_types=violation_types
        )
        try:
            result = await call_model(
                session,
                prompt_key=prompts.AI2_PROMPT_KEY,
                system=payload.system,
                user=payload.user,
                generation_id=generation.id,
            )
        except CallFailed as exc:
            # §9.1 — 동일 request id 1회 재시도는 `call_model`이 이미 했다. 여기서 재생성으로
            # 한 번 더 부르지 않는다: 장애 경로의 종착지는 fallback이다.
            logger.warning("AI2 호출 실패 — fallback으로 수렴한다: %s", exc)
            last_rule_violations = [
                {"rule": CALL_FAILED_CODE, "detail": "AI2 호출 실패 (§9.1)"}
            ]
            generation.rule_violations = last_rule_violations
            last_verdict = None
            break

        draft = result.text
        generation.output_text = fernet.encrypt(draft)

        # `allowed`에 payload 전문을 넘긴다 — 이번 호출에서 정당하게 준 문자열은 누출의
        # 증거가 될 수 없다(§6.4 R-1의 "payload에 정당히 포함된 문자열 제외").
        rule_violations = integrity_rules.check_all(draft, forbidden, allowed=payload.joined())
        # §6.4 R-2 — 기록만 한다. 재생성 판정에 넣지 않는다.
        alt_overlap = integrity_rules.flag_alt_overlap(draft, alt_segments)
        # 규칙 위반이 이미 있으면 checker를 부르지 않는다 — 판정 결과가 같고(재생성),
        # §6.1의 시간 예산(90s + 45s + 재생성 여유)을 아낀다. `checker_result=null` +
        # `rule_violations` 비어 있지 않음이 그 상태의 기록이다.
        verdict = (
            checker_module.CheckerVerdict(passed=True)
            if rule_violations
            else await checker_module.run(
                session,
                effective=effective,
                focal_ai1=focal_ai1,
                user1=user1,
                draft=draft,
                prohibited_inference=prohibited_inference,
                generation_id=generation.id,
            )
        )

        generation.rule_violations = [violation.as_dict() for violation in rule_violations]
        generation.alt_overlap = alt_overlap
        generation.checker_result = verdict.result
        generation.checker_skipped = verdict.skipped

        if not rule_violations and verdict.passed:
            generation.final = True
            return Ai2Outcome(
                text=draft,
                generation_id=generation.id,
                attempt=attempt,
                fallback_used=False,
                regenerated=attempt > 1,
                rule_violations=[],
                checker_result=verdict.result,
                checker_skipped=verdict.skipped,
                alt_overlap=alt_overlap,
            )

        last_rule_violations = generation.rule_violations
        last_overlap = alt_overlap
        last_verdict = verdict
        # §6.4 재생성 피드백 — **유형만** 넘긴다. span에는 금지 문자열이 들어 있을 수 있다.
        violation_types = [violation.rule for violation in rule_violations] + verdict.violation_types

    return await _fallback(
        session,
        focal_run_id=focal_run_id,
        attempt=attempt,
        text=neutral_fallback,
        rule_violations=last_rule_violations,
        alt_overlap=last_overlap,
        verdict=last_verdict,
    )


async def _fallback(
    session: AsyncSession,
    *,
    focal_run_id: uuid.UUID,
    attempt: int,
    text: str,
    rule_violations: list[dict[str, Any]],
    alt_overlap: list[dict[str, str]],
    verdict: checker_module.CheckerVerdict | None,
) -> Ai2Outcome:
    """§6.5 — 참가자별 사전 작성 fallback. 이 문안은 자산 계약에서 R-3·R-4를 이미 통과했다(NT-21)."""
    generation = _new_generation(session, focal_run_id, attempt)
    generation.output_text = fernet.encrypt(text)
    generation.rule_violations = rule_violations
    generation.alt_overlap = alt_overlap
    generation.checker_result = verdict.result if verdict else None
    generation.checker_skipped = bool(verdict.skipped) if verdict else False
    generation.fallback_used = True
    generation.final = True
    await session.flush()

    await notify(
        NotifyEvent.AI2_FALLBACK_USED,
        "AI2 neutral_fallback 표시",
        attempt=attempt,
        violations=",".join(sorted({str(item.get("rule") or item.get("type")) for item in rule_violations}))
        or None,
    )
    return Ai2Outcome(
        text=text,
        generation_id=generation.id,
        attempt=attempt,
        fallback_used=True,
        regenerated=attempt > 1,
        rule_violations=rule_violations,
        checker_result=generation.checker_result,
        checker_skipped=generation.checker_skipped,
        alt_overlap=alt_overlap,
    )
