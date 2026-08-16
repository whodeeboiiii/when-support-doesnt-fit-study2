"""AI2 생성 파이프라인 (구현명세서 §6.1 · §6.5 · §6.6 · §9.1 · §8.4).

    [2] payload 조립(allowlist §6.2) → [3] AI2 생성(MAIN) → [4] 규칙 검사(§6.5 R-계열)
    → [5] LLM checker(VALIDATOR) → 위반 시 재생성 1회 → 재위반 시 neutral_fallback

([1] normalization은 §8.3의 시간 순서대로 **User1 제출 시점**에 이미 끝나 있다 — 이 함수는
정규화본을 받는다.)

**사다리의 끝은 언제나 표시 가능한 텍스트다**(§9.1 dead-end 금지). 호출 실패·위반·재위반·
checker 불능 — 어느 경로로 가도 참가자 화면에는 {정상 | 재생성 통과 | neutral_fallback} 중
하나가 뜬다. 세 경로는 참가자에게 구분되지 않지만(§4.7) `generations`·`llm_calls`만으로
사후 복원된다(§8.4 · NT-15).

기록 규약 (§8.1 `generations`)
- 모델을 부른 시도마다 1행. `attempt`는 1(최초)·2(재생성)다.
- 표시된 텍스트를 가진 행이 `final=True`이고 branch당 정확히 1행이다.
- fallback은 **별도 행**이다(마지막 시도 번호를 그대로 쓰고 `fallback_used=True`). 위반한
  초안의 원문을 fallback 문안으로 덮어쓰지 않기 위해서다 — 초안이 남아야 integrity 보고가
  "무엇이 왜 기각됐는지"를 말할 수 있다(초안 §7.9).

⚠ 이 모듈은 `dossier_private`를 import하지 않는다(NT-04). R-1의 대조 문자열은 호출부가
`ForbiddenText`로 넘긴다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.dossier_loader import AiVisible
from app.llm import checker as checker_module
from app.llm import context, integrity_rules, prompts
from app.llm.gateway.calls import CallFailed, call_model
from app.llm.integrity_rules import ForbiddenText
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


def _new_generation(session: AsyncSession, branch_id: uuid.UUID, attempt: int) -> Generation:
    row = Generation(
        branch_id=branch_id,
        attempt=attempt,
        rule_violations=[],
        checker_skipped=False,
        fallback_used=False,
        final=False,
    )
    session.add(row)
    return row


async def run(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    ai_visible: AiVisible,
    user1_normalized: str,
    neutral_fallback: str,
    prohibited_inference: Sequence[str] = (),
    forbidden: Sequence[ForbiddenText] = (),
) -> Ai2Outcome:
    """한 branch의 AI2 1턴. 인자 목록이 곧 §6.2 allowlist다.

    `forbidden`은 **판정용 대조 문자열**이지 payload가 아니다 — 어떤 프롬프트에도 실리지
    않는다(§6.5 R-1·R-2).
    """
    violation_types: list[str] = []
    last_rule_violations: list[dict[str, Any]] = []
    last_verdict: checker_module.CheckerVerdict | None = None
    attempt = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        generation = _new_generation(session, branch_id, attempt)
        await session.flush()  # llm_calls.generation_id가 이 id를 참조한다(§8.1)

        payload = context.build_ai2_payload(
            ai_visible, user1_normalized, violation_types=violation_types
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
        # 증거가 될 수 없다(참가자가 두 branch에서 같은 말을 반복하는 경우 — §6.5 주석).
        rule_violations = integrity_rules.check_all(draft, forbidden, allowed=payload.joined())
        # 규칙 위반이 이미 있으면 checker를 부르지 않는다 — 판정 결과가 같고(재생성),
        # §6.1의 시간 예산(90s + 45s + 재생성 여유)을 아낀다. `checker_result=null` +
        # `rule_violations` 비어 있지 않음이 그 상태의 기록이다.
        verdict = (
            checker_module.CheckerVerdict(passed=True)
            if rule_violations
            else await checker_module.run(
                session,
                ai_visible=ai_visible,
                user1_normalized=user1_normalized,
                draft=draft,
                prohibited_inference=prohibited_inference,
                generation_id=generation.id,
            )
        )

        generation.rule_violations = [violation.as_dict() for violation in rule_violations]
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
            )

        last_rule_violations = generation.rule_violations
        last_verdict = verdict
        # §6.5 재생성 피드백 — **유형만** 넘긴다. span에는 금지 문자열이 들어 있을 수 있다.
        violation_types = [violation.rule for violation in rule_violations] + verdict.violation_types

    return await _fallback(
        session,
        branch_id=branch_id,
        attempt=attempt,
        text=neutral_fallback,
        rule_violations=last_rule_violations,
        verdict=last_verdict,
    )


async def _fallback(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    attempt: int,
    text: str,
    rule_violations: list[dict[str, Any]],
    verdict: checker_module.CheckerVerdict | None,
) -> Ai2Outcome:
    """§6.6 — 참가자별 사전 작성 fallback. 이 문안은 자산 계약에서 R-3·R-4를 이미 통과했다(NT-21)."""
    generation = _new_generation(session, branch_id, attempt)
    generation.output_text = fernet.encrypt(text)
    generation.rule_violations = rule_violations
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
    )
