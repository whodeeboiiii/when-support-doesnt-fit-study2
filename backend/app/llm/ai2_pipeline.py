"""AI2 생성 파이프라인 — **NS2 이음매** (구현명세서 §6 · §9.1 · §11.1).

NS3이 이 파일의 내용을 갈아끼운다: §6.4 normalization → §6.2 payload 조립 → MAIN 호출 →
§6.5 규칙·checker → 위반 시 재생성 1회 → §6.6 neutral fallback.

NS2에서 이 자리를 비워 두지 않는 이유는 §9.1의 **dead-end 금지**다. 화면·상태머신이 먼저
서면 P7(B4)에 도달하는 경로가 생기고, 그 경로에는 반드시 유효한 다음 상태가 있어야 한다.
그래서 NS2 판은 사다리의 **종착지**(참가자별 neutral_fallback)를 그대로 쓴다 —
"임시로 아무 텍스트"가 아니라 명세가 정한 실패 경로의 착지점이다.

그 결과 NS2 시연에서 P7에 뜨는 문안은 dossier `derivation.neutral_fallback`이고,
`generations.fallback_used=true`로 기록되며 §2.8 알림이 발화한다. 감사 기록이 실제 일어난
일을 그대로 말한다 — 정상 생성인 척하는 자리는 만들지 않는다.

⚠ 이 모듈은 `dossier_private`를 import하지 않는다(NT-04). NS3에서 payload 조립기를 여기
붙일 때도 마찬가지다 — 허용 입력은 §6.2의 3종뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.assets import dossier_loader
from app.notify.discord import NotifyEvent, notify


@dataclass(frozen=True, slots=True)
class Ai2Outcome:
    """§8.1 `generations` 1행이 되는 값 (§8.4 audit 재구성의 단위)."""

    text: str
    attempt: int
    fallback_used: bool
    rule_violations: list[dict[str, Any]] = field(default_factory=list)
    checker_result: dict[str, Any] | None = None
    checker_skipped: bool = False


async def generate(*, participant_no: str, user1_text: str) -> Ai2Outcome:
    """해당 branch의 AI2 1턴을 만든다.

    NS2 판: 호출하지 않고 곧장 참가자별 neutral_fallback으로 수렴한다.
    `<TODO: NS3 — §6.1 파이프라인(normalization·MAIN 호출·integrity·재생성) 구현>`

    `user1_text`를 인자로 받아 두는 것은 NS3에서 시그니처가 바뀌지 않게 하기 위해서다.
    NS2에서는 **쓰지 않는다** — 즉 이 스프린트에서 참가자 텍스트가 LLM 경로로 나가는 일은
    한 번도 없다.
    """
    dossier = dossier_loader.load(participant_no)
    await notify(
        NotifyEvent.AI2_FALLBACK_USED,
        "AI2 파이프라인 미구현(NS2) — neutral_fallback 표시",
        participant_no=participant_no,
    )
    return Ai2Outcome(
        text=dossier.derivation.neutral_fallback,
        attempt=1,
        fallback_used=True,
        rule_violations=[],
        checker_result=None,
        checker_skipped=True,
    )
