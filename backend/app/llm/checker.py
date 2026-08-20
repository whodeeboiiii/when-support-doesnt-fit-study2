"""LLM integrity checker (구현명세서 §6.4 · 부록 A.2 v2 · §9.1).

규칙 계층(§6.4 R-계열)이 못 잡는 셋만 본다 — unsupported_inference · expansion ·
correction_ignored. 질문 수·길이·문자열 누출은 결정론 규칙이 전담하므로 checker에 중복
위임하지 않는다(부록 A.2 주).

**checker 실패는 참가자 경로를 끊지 않는다**(§9.1): 타임아웃·파싱 실패는 `checker_skipped`로
기록하고 규칙 계층만으로 판정한다. 판정 불능을 위반으로 취급하면 정상 생성물이 fallback으로
떨어지고, 그건 조작 자체를 바꾼다(§6.6은 fallback을 예외 경로로 설계했다).

⚠ checker payload도 allowlist 대상이다(NT-02). 조립은 `llm/context.py`가 하고 이 모듈은
호출·판정 해석만 한다. checkpoint는 **참가자 수정본**이다(D-25) — 원문이 아니다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.dossier_loader import EffectiveAiVisible
from app.llm import context, prompts
from app.llm.gateway.calls import CallFailed, call_model
from app.notify.discord import NotifyEvent, notify

logger = logging.getLogger(__name__)

#: 부록 A.2가 정의한 위반 유형. 목록 밖의 유형은 판정 형식 위반으로 본다.
VIOLATION_TYPES: frozenset[str] = frozenset(
    {"unsupported_inference", "expansion", "correction_ignored"}
)


@dataclass(frozen=True, slots=True)
class CheckerVerdict:
    """§8.1 `generations.checker_result`·`checker_skipped`에 그대로 들어가는 값."""

    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    #: §8.4 "checker 판정 전문". 실패 시 None.
    result: dict[str, Any] | None = None
    skipped: bool = False

    @property
    def violation_types(self) -> list[str]:
        return [str(item.get("type", "")) for item in self.violations]


def parse_verdict(data: dict[str, Any] | None) -> CheckerVerdict:
    """부록 A.2 출력 형식 → 판정. 형식이 어긋나면 파싱 실패로 본다(§9.1).

    `pass` 필드와 `violations` 배열이 어긋나면(예: violations가 있는데 pass=true)
    **violations를 권위로** 삼는다 — 위반 목록이 판정의 근거이고 pass는 요약이다.
    """
    if not isinstance(data, dict):
        raise ValueError("checker 응답이 JSON 객체가 아니다")
    if "violations" not in data or not isinstance(data["violations"], list):
        raise ValueError("checker 응답에 violations 배열이 없다")

    violations: list[dict[str, Any]] = []
    for item in data["violations"]:
        if not isinstance(item, dict) or "type" not in item:
            raise ValueError("violations 항목에 type이 없다")
        if item["type"] not in VIOLATION_TYPES:
            raise ValueError(f"알 수 없는 위반 유형: {item['type']!r}")
        violations.append(
            {
                "type": str(item["type"]),
                "span": str(item.get("span", "")),
                "rationale": str(item.get("rationale", "")),
            }
        )
    return CheckerVerdict(passed=not violations, violations=violations, result=data)


async def run(
    session: AsyncSession,
    *,
    effective: EffectiveAiVisible,
    focal_ai1: str,
    user1: str,
    draft: str,
    prohibited_inference: Sequence[str] = (),
    generation_id: uuid.UUID | None = None,
) -> CheckerVerdict:
    """checker 1회. 실패는 예외로 올리지 않고 `skipped` 판정으로 흡수한다(§9.1).

    입력은 §6.4가 허용한 다섯이다: effective checkpoint · focal AI1 · User1 · 초안 ·
    prohibited_inference (NT-02). 시그니처가 그 목록이다.
    """
    payload = context.build_checker_payload(
        effective, focal_ai1, user1, draft, prohibited_inference
    )
    try:
        result = await call_model(
            session,
            prompt_key=prompts.CHECKER_PROMPT_KEY,
            system=payload.system,
            user=payload.user,
            generation_id=generation_id,
        )
        return parse_verdict(result.data)
    except (CallFailed, ValueError) as exc:
        logger.warning("checker 판정 불가 — 규칙 계층만으로 진행한다: %s", exc)
        await notify(
            NotifyEvent.CHECKER_SKIPPED,
            "integrity checker 판정 불가 — 규칙 계층만으로 진행",
            reason=type(exc).__name__,
        )
        # 판정 불능은 통과로 취급한다. 위반으로 취급하면 정상 생성물이 fallback으로 떨어진다.
        return CheckerVerdict(passed=True, violations=[], result=None, skipped=True)
