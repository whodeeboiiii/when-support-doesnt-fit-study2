"""세션(SS)·focal(F) 상태머신 (구현명세서 §3.1 · §3.2 · §3.3 · §3.5 · NT-14).

v1.0.1의 4-branch 루프(B0–B7 × 4회 + reset)가 **focal 1회 + 대안 노출 3 + pairwise 3**으로
전면 재작성됐다(D-23). "branch"라는 말은 v2.0에서 쓰지 않는다(§1.5-5).

원칙 셋이 이 모듈의 모양을 정한다.

1. **상태는 서버가 소유한다**(§1.3). 클라이언트가 "다음 화면"을 주장하지 않고, 서버 상태가
   화면을 결정한다(`screen_for`).
2. **합법 전이만 허용한다**(NT-14). sidecar 없이 AI2, focal 측정 없이 대안 노출, position
   건너뛰기(NT-33)는 전부 `IllegalTransition`이다.
3. **뒤로 가지 않는다**(§1.3·§3.5). 전이 표에 역방향 간선이 없다 — 새로고침·뒤로가기는
   전이가 아니라 **복원**이다.

여기에는 판정·라우팅이 없다(§0.3·CLAUDE.md 절대 규칙 8). F4의 `reply`/`end`는 참가자 선택의
기록이지 평가가 아니고, 둘 다 같은 다음 상태(F5)로 간다 — v1.0.1의 `has_ai2`·
`b_state_after_sidecar` 같은 분기 함수가 v2.0에 없는 이유다(D-32: User1 필수, no_reply 폐기).
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class IllegalTransition(RuntimeError):
    """상태머신이 허용하지 않는 전이 (NT-14 — API는 409로 옮긴다)."""


class SsState(StrEnum):
    """§3.1 세션 수준 상태 — 각 상태의 다음 상태는 정확히 하나다."""

    CREATED = "SS00"
    CONSENT = "SS01"
    #: 사전설문 (v1.0.1 §4.2 — D-44로 복원). 번호가 `SS01S`인 이유는 §0.2의 SS02–SS10을
    #: 밀지 않기 위해서다 — 한 화면을 끼우자고 상태·화면 ID 전체를 재번호하면 명세서·콘솔·
    #: rewind 대상(P8–P11)·문서가 전부 갈라진다. 진행 순위는 `SS_NEXT` 사슬이 정한다.
    PRESURVEY = "SS01S"
    CHECKPOINT = "SS02"
    REENTRY = "SS03"
    FOCAL = "SS04"
    FOCAL_MEASURES = "SS05"
    ALT_EXPOSURE = "SS06"
    PAIRWISE = "SS07"
    INTERVIEW = "SS08"
    DEBRIEF = "SS09"
    DONE = "SS10"
    RESEARCHER_ABORT = "SS90"
    DROPOUT = "SS91"


class FState(StrEnum):
    """§3.2 focal 수준 상태 — branch 루프의 대체물. 참가자당 1회만 돈다."""

    AI1_PENDING = "F0"
    USER1 = "F1"
    SIDECAR = "F2"
    AI2 = "F3"
    DOWNSTREAM = "F4"
    CLOSED = "F5"


class Disposition(StrEnum):
    """§4.7·§7.4 — AI2 이후의 enacted choice 2종 (D-26).

    v1.0.1의 3분기(reply/no_reply/end)와 다르다: no_reply는 폐기됐고(D-32 — User1 필수),
    여기의 `end`는 **AI2를 본 뒤의** 종료다. 둘 다 F5로 가므로 이 값은 분기가 아니라
    기록이다(§0.3 판정 코드 금지).
    """

    REPLY = "reply"
    END = "end"


#: §4.7 이탈 유형 6코드 [**영문 코드 고정**] — 라벨은 [PI 승인 2026-08-24](PH-09 해소).
class EndType(StrEnum):
    STOP_HERE = "stop_here"
    NEW_CHAT = "new_chat"
    SWITCH_AI = "switch_ai"
    SEEK_HUMAN = "seek_human"
    NO_FURTHER_NEED = "no_further_need"
    OTHER = "other"


#: §3.3 — 대안 노출·pairwise의 위치는 1–3이다.
ALT_POSITIONS = 3
PAIR_POSITIONS = 3

#: §3.1 진행 방향. 각 상태에서 갈 수 있는 다음 상태는 정확히 하나다. 역방향 간선 없음.
SS_NEXT: Mapping[SsState, SsState] = MappingProxyType(
    {
        SsState.CREATED: SsState.CONSENT,
        SsState.CONSENT: SsState.PRESURVEY,
        SsState.PRESURVEY: SsState.CHECKPOINT,
        SsState.CHECKPOINT: SsState.REENTRY,
        SsState.REENTRY: SsState.FOCAL,
        SsState.FOCAL: SsState.FOCAL_MEASURES,
        SsState.FOCAL_MEASURES: SsState.ALT_EXPOSURE,
        SsState.ALT_EXPOSURE: SsState.PAIRWISE,
        SsState.PAIRWISE: SsState.INTERVIEW,
        SsState.INTERVIEW: SsState.DEBRIEF,
        SsState.DEBRIEF: SsState.DONE,
    }
)

#: §3.1 — 연구자 개입으로만 도달하는 종결 상태. 진행 중 어느 상태에서도 갈 수 있다.
INTERRUPT_STATES: frozenset[SsState] = frozenset({SsState.RESEARCHER_ABORT, SsState.DROPOUT})

#: 더 이상 전이가 없는 상태 (§3.1).
TERMINAL_SS: frozenset[SsState] = frozenset({SsState.DONE}) | INTERRUPT_STATES

#: 참가자가 화면을 조작할 수 있는 상태 (§3.1 — SS10·SS90·SS91에서는 제출을 받지 않는다).
ACTIVE_SS: frozenset[SsState] = frozenset(SS_NEXT)

#: §3.1·§1.2 — **focal 측정(SS05) 완료 이후**의 상태. 대안 AI1이 payload에 실릴 수 있는
#: 유일한 구간이다(NT-31). 이 집합이 그 불변식의 단일 판정 지점이다.
POST_FOCAL_MEASURE_SS: frozenset[SsState] = frozenset(
    {SsState.ALT_EXPOSURE, SsState.PAIRWISE, SsState.INTERVIEW, SsState.DEBRIEF, SsState.DONE}
)

def _build_ss_rank() -> Mapping[SsState, int]:
    """§3.1 진행 순위. `SS_NEXT` 사슬을 걸어서 만든다 — 표를 손으로 또 적으면 갈라진다."""
    order: dict[SsState, int] = {}
    state, rank = SsState.CREATED, 0
    while True:
        order[state] = rank
        following = SS_NEXT.get(state)
        if following is None:
            return MappingProxyType(order)
        state, rank = following, rank + 1


#: 상태의 진행 순위(클수록 뒤). idempotency 판정(§3.5)과 rewind 방향 검증(§9.1.1)이 함께 쓴다.
SS_RANK: Mapping[SsState, int] = _build_ss_rank()

#: §9.1.1 rewind — **연구자 개입**이다. 참가자에게는 여전히 역방향 간선이 없다(§1.3·§3.5).
#:
#: focal(SS04)이 없는 이유: AI1 노출·User1·AI2는 1회성이라 되돌려도 복구되지 않는다 —
#: 그 경우의 정당한 처리는 abort다. SS09 이후가 없는 이유: 디브리핑이 설계를 공개한 뒤의
#: 재측정은 오염이다.
REWIND_TARGETS: Mapping[str, SsState] = MappingProxyType(
    {
        "P8": SsState.FOCAL_MEASURES,
        "P9": SsState.ALT_EXPOSURE,
        "P10": SsState.PAIRWISE,
        "P11": SsState.INTERVIEW,
    }
)

#: rewind 요청을 **받을 수 있는** 현재 상태. 대상 집합과 같다(둘 다 SS05–SS08).
REWINDABLE_FROM: frozenset[SsState] = frozenset(REWIND_TARGETS.values())

#: position을 함께 받는 대상 — 그 상태 안에서 위치까지 지정해야 되돌릴 지점이 정해진다.
REWIND_POSITION_LIMIT: Mapping[SsState, int] = MappingProxyType(
    {SsState.ALT_EXPOSURE: ALT_POSITIONS, SsState.PAIRWISE: PAIR_POSITIONS}
)


#: §3.2 focal 전이. **갈래가 없다** — F4의 reply/end는 둘 다 F5로 간다(§0.3 · D-32).
F_NEXT: Mapping[FState, frozenset[FState]] = MappingProxyType(
    {
        FState.AI1_PENDING: frozenset({FState.USER1}),
        FState.USER1: frozenset({FState.SIDECAR}),
        FState.SIDECAR: frozenset({FState.AI2}),
        FState.AI2: frozenset({FState.DOWNSTREAM}),
        FState.DOWNSTREAM: frozenset({FState.CLOSED}),
        FState.CLOSED: frozenset(),
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


def assert_f_transition(current: FState, target: FState) -> None:
    """§3.2 전이 검증 — NT-14의 "sidecar 없이 AI2" 류를 여기서 끊는다."""
    if target not in F_NEXT.get(current, frozenset()):
        raise IllegalTransition(f"focal 전이 불가: {current} → {target} (§3.2)")


def assert_position(current_index: int | None, submitted: int, *, limit: int, label: str) -> None:
    """§3.3 · NT-33 — position 건너뛰기 불가.

    `alt_index`·`pair_index`는 서버가 소유하는 진행 위치다. 클라이언트가 2를 건너뛰고 3을
    제출하면 409다 — 노출·평정이 배정표 순서대로 일어났다는 것이 데이터의 전제이기 때문이다.
    """
    if not 1 <= submitted <= limit:
        raise IllegalTransition(f"{label} 위치 범위 밖: {submitted} (1–{limit})")
    if current_index != submitted:
        raise IllegalTransition(
            f"{label} 위치 불일치: 서버 {current_index} vs 요청 {submitted} (§3.3 · NT-33)"
        )


def assert_rewind(
    current: SsState,
    target_screen: str,
    position: int | None,
    current_position: int | None = None,
) -> tuple[SsState, int | None]:
    """§9.1.1 — 연구자 되돌리기의 대상 검증. 반환 = (목표 상태, 확정된 position).

    **전진은 rewind가 아니다.** 같은 상태 안에서는 position이 현재 위치보다 뒤면 거부한다 —
    되돌리기 API로 참가자를 앞으로 밀 수 있으면 그건 상태머신을 우회하는 두 번째 경로다.
    """
    if current not in REWINDABLE_FROM:
        raise IllegalTransition(
            f"{current}에서는 되돌릴 수 없다 — SS05–SS08만 가능하다 "
            "(focal은 abort, 디브리핑 이후는 오염 — §9.1.1)"
        )
    target = REWIND_TARGETS.get(target_screen)
    if target is None:
        raise IllegalTransition(
            f"되돌릴 수 없는 화면: {target_screen} (가능: {sorted(REWIND_TARGETS)} — §9.1.1)"
        )
    if SS_RANK[target] > SS_RANK[current]:
        raise IllegalTransition(f"전진 방향이다: {current} → {target} (§9.1.1)")

    limit = REWIND_POSITION_LIMIT.get(target)
    if limit is None:
        return target, None
    if position is None:
        raise IllegalTransition(f"{target_screen}은 position이 필요하다 (1–{limit})")
    if not 1 <= position <= limit:
        raise IllegalTransition(f"position 범위 밖: {position} (1–{limit})")
    if target is current and current_position is not None and position > current_position:
        raise IllegalTransition(
            f"전진 방향이다: {target_screen} {current_position} → {position} (§9.1.1)"
        )
    return target, position


# --------------------------------------------------------------------------- #
# 화면 매핑 (§0.2 · §3.1 · §3.2) — 상태 → 참가자 화면 ID (P0–P12)
# --------------------------------------------------------------------------- #

#: SS04 밖의 상태는 focal 상태와 무관하게 화면이 하나로 정해진다.
_SS_SCREEN: Mapping[SsState, str] = MappingProxyType(
    {
        SsState.CREATED: "P0",
        SsState.CONSENT: "P1",
        SsState.PRESURVEY: "P1S",
        SsState.CHECKPOINT: "P2",
        SsState.REENTRY: "P3",
        SsState.FOCAL_MEASURES: "P8",
        SsState.ALT_EXPOSURE: "P9",
        SsState.PAIRWISE: "P10",
        SsState.INTERVIEW: "P11",
        SsState.DEBRIEF: "P12",
        SsState.DONE: "DONE",
        SsState.RESEARCHER_ABORT: "ABORTED",
        SsState.DROPOUT: "ABORTED",
    }
)

#: §3.2 표의 화면 열. F5는 P7의 종료 안내에 머물다 `advance`로 SS05(P8)로 넘어간다.
_F_SCREEN: Mapping[FState, str] = MappingProxyType(
    {
        FState.AI1_PENDING: "P4",
        FState.USER1: "P4",
        FState.SIDECAR: "P5",
        FState.AI2: "P6",
        FState.DOWNSTREAM: "P7",
        FState.CLOSED: "P7",
    }
)


def screen_for(ss_state: SsState, f_state: FState | None) -> str:
    """현재 상태의 참가자 화면 (§0.2 P0–P12).

    화면 선택을 클라이언트에 두지 않는 이유는 §3.5다 — 새로고침·재접속에서 서버 상태가 곧
    화면이어야 복구가 성립한다.
    """
    if ss_state is not SsState.FOCAL:
        return _SS_SCREEN[ss_state]
    if f_state is None:
        raise IllegalTransition("SS04인데 focal 상태가 없다 — 저장 상태가 깨졌다")
    return _F_SCREEN[f_state]


def alt_exposure_allowed(ss_state: SsState) -> bool:
    """§1.2·NT-31 — 대안 AI1을 payload에 실어도 되는가.

    focal 측정(SS05) **완료** 후여야 한다. SS05 자체는 아직 제출 전이므로 포함하지 않는다.
    이 함수가 그 판정의 단일 지점이고, 화면 조립기·콘솔이 같은 함수를 쓴다.
    """
    return ss_state in POST_FOCAL_MEASURE_SS
