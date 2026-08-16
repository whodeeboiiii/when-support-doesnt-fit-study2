"""세션(SS)·branch(B) 상태머신 (구현명세서 §3.1 · §3.2 · §3.5 · NT-14).

원칙 세 가지가 이 모듈의 모양을 정한다.

1. **상태는 서버가 소유한다**(§1.3). 클라이언트가 "다음 화면"을 주장하지 않고, 서버 상태가
   화면을 결정한다(`screen_for`).
2. **합법 전이만 허용한다**(NT-14). B4 없이 B5로 가는 요청, 사전설문 없이 checkpoint 확인,
   완료 세션의 재제출은 전부 `IllegalTransition`이다.
3. **뒤로 가지 않는다**(§1.3·§3.5). 전이 표에 역방향 간선이 없다 — 새로고침·뒤로가기는
   전이가 아니라 **복원**이다.

여기에는 판정·라우팅이 없다. B2의 3분기(reply/no_reply/end)는 참가자 선택의 기록이지 평가가
아니며, no_reply/end가 B4·B5를 건너뛰는 것은 실패 경로가 아니라 독립 trajectory다(§3.2).
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class IllegalTransition(RuntimeError):
    """상태머신이 허용하지 않는 전이 (NT-14 — API는 409로 옮긴다)."""


class SsState(StrEnum):
    """§3.1 세션 수준 상태."""

    CREATED = "SS00"
    JOINED_CONSENT = "SS01"
    PRESURVEY = "SS02"
    CHECKPOINT_REVIEW = "SS03"
    BRANCH_BLOCK = "SS04"
    CROSS_REVIEW = "SS05"
    DEBRIEF = "SS06"
    DONE = "SS07"
    RESEARCHER_ABORT = "SS90"
    DROPOUT = "SS91"


class BState(StrEnum):
    """§3.2 branch 수준 상태."""

    REENTRY = "B0"
    AI1_SHOWN = "B1"
    USER1 = "B2"
    SIDECAR = "B3"
    AI2 = "B4"
    DOWNSTREAM = "B5"
    RATINGS = "B6"
    RESET_DONE = "B7"


class Disposition(StrEnum):
    """§3.2 B2의 3분기. 셋 다 유효한 종결이다(§7.4 — 결과 변수)."""

    REPLY = "reply"
    NO_REPLY = "no_reply"
    END = "end"


#: §3.1 진행 방향. 각 상태에서 갈 수 있는 다음 상태는 정확히 하나다.
SS_NEXT: Mapping[SsState, SsState] = MappingProxyType(
    {
        SsState.CREATED: SsState.JOINED_CONSENT,
        SsState.JOINED_CONSENT: SsState.PRESURVEY,
        SsState.PRESURVEY: SsState.CHECKPOINT_REVIEW,
        SsState.CHECKPOINT_REVIEW: SsState.BRANCH_BLOCK,
        SsState.BRANCH_BLOCK: SsState.CROSS_REVIEW,
        SsState.CROSS_REVIEW: SsState.DEBRIEF,
        SsState.DEBRIEF: SsState.DONE,
    }
)

#: §3.1 — 연구자 개입으로만 도달하는 종결 상태. 진행 중 어느 상태에서도 갈 수 있다.
INTERRUPT_STATES: frozenset[SsState] = frozenset({SsState.RESEARCHER_ABORT, SsState.DROPOUT})

#: 더 이상 전이가 없는 상태 (§3.1).
TERMINAL_SS: frozenset[SsState] = frozenset({SsState.DONE}) | INTERRUPT_STATES

#: 참가자가 화면을 조작할 수 있는 상태 (§3.1 — SS90·SS91·SS07에서는 제출을 받지 않는다).
ACTIVE_SS: frozenset[SsState] = frozenset(SS_NEXT)

#: §3.2 branch 전이. B3에서만 갈래가 둘이다(reply → B4 / no_reply·end → B6).
B_NEXT: Mapping[BState, frozenset[BState]] = MappingProxyType(
    {
        BState.REENTRY: frozenset({BState.AI1_SHOWN}),
        BState.AI1_SHOWN: frozenset({BState.USER1}),
        BState.USER1: frozenset({BState.SIDECAR}),
        BState.SIDECAR: frozenset({BState.AI2, BState.RATINGS}),
        BState.AI2: frozenset({BState.DOWNSTREAM}),
        BState.DOWNSTREAM: frozenset({BState.RATINGS}),
        BState.RATINGS: frozenset({BState.RESET_DONE}),
        BState.RESET_DONE: frozenset(),
    }
)


def assert_ss_transition(current: SsState, target: SsState) -> None:
    """§3.1 전이 검증. 중단(SS90·SS91)은 진행 중 상태에서만 받는다."""
    if target in INTERRUPT_STATES:
        if current in TERMINAL_SS:
            raise IllegalTransition(f"{current}는 종결 상태다 — {target}로 보낼 수 없다")
        return
    if SS_NEXT.get(current) != target:
        raise IllegalTransition(f"세션 전이 불가: {current} → {target} (§3.1)")


def assert_b_transition(current: BState, target: BState) -> None:
    """§3.2 전이 검증 — NT-14의 "B4 없이 B5" 류를 여기서 끊는다."""
    if target not in B_NEXT.get(current, frozenset()):
        raise IllegalTransition(f"branch 전이 불가: {current} → {target} (§3.2)")


def b_state_after_sidecar(disposition: Disposition) -> BState:
    """§3.2 — reply면 AI2(B4)로, no_reply/end면 곧장 평정(B6)으로.

    **no_reply/end branch에는 AI2·downstream이 없다**(NT-17). 이 분기가 그 불변식의 원천이다.
    """
    return BState.AI2 if disposition is Disposition.REPLY else BState.RATINGS


def has_ai2(disposition: Disposition | str | None) -> bool:
    """해당 branch가 AI2·downstream 화면을 갖는가 (§3.2 · §7.3 D-22 매트릭스)."""
    return disposition == Disposition.REPLY


# --------------------------------------------------------------------------- #
# 화면 매핑 (§0.2 · §3.1 · §3.2) — 상태 → 참가자 화면 ID
# --------------------------------------------------------------------------- #

#: SS04 밖의 상태는 branch와 무관하게 화면이 하나로 정해진다.
_SS_SCREEN: Mapping[SsState, str] = MappingProxyType(
    {
        SsState.CREATED: "P0",
        SsState.JOINED_CONSENT: "P1",
        SsState.PRESURVEY: "P2",
        SsState.CHECKPOINT_REVIEW: "P3",
        SsState.CROSS_REVIEW: "P10",
        SsState.DEBRIEF: "P11",
        SsState.DONE: "DONE",
        SsState.RESEARCHER_ABORT: "ABORTED",
        SsState.DROPOUT: "ABORTED",
    }
)

#: §3.2 표의 화면 열. B7은 화면이 없다 — 다음 branch의 B0(P4)로 즉시 넘어간다.
_B_SCREEN: Mapping[BState, str] = MappingProxyType(
    {
        BState.REENTRY: "P4",
        BState.AI1_SHOWN: "P5",
        BState.USER1: "P5",
        BState.SIDECAR: "P6",
        BState.AI2: "P7",
        BState.DOWNSTREAM: "P8",
        BState.RATINGS: "P9",
        BState.RESET_DONE: "P4",
    }
)


def screen_for(ss_state: SsState, b_state: BState | None) -> str:
    """현재 상태의 참가자 화면 (§0.2 P0–P11).

    화면 선택을 클라이언트에 두지 않는 이유는 §3.5다 — 새로고침·재접속에서 서버 상태가 곧
    화면이어야 복구가 성립한다.
    """
    if ss_state is not SsState.BRANCH_BLOCK:
        return _SS_SCREEN[ss_state]
    if b_state is None:
        raise IllegalTransition("SS04인데 branch 상태가 없다 — 저장 상태가 깨졌다")
    return _B_SCREEN[b_state]
