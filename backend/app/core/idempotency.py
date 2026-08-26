"""제출 idempotency (구현명세서 §3.5 · §9.1 · NT-09).

    중복 제출: idempotency key = `(session_id, step[, index])` — 재제출은 200 + 기존 레코드.

**별도 테이블을 두지 않는다.** §8.1 표에 idempotency 테이블이 없고, 필요도 없다 — 키의 세
성분이 이미 저장 상태에 있기 때문이다: 세션은 `sessions.ss_state`, focal은 `sessions.f_state`,
위치는 `alt_index`·`pair_index`, 그리고 각 step의 산출물(turn·sidecar_entry·rating 행)이 그
자체로 "이미 했다"의 증거다.

판정 규칙은 이렇게 정리된다.

1. 현재 상태가 **이 step을 아직 하지 않은** 상태다 → 정상 처리.
2. 현재 상태가 **이 step을 이미 지난** 상태다 → 재제출. 200 + 저장된 레코드(§9.1 "무반응").
3. 그 밖 → 비합법 전이(NT-14) → 409.

2와 3을 가르는 것은 상태의 **순서**다. 이 모듈은 그 순서 비교만 담당한다 — DB 조회는
호출부(라우터)가 한다.

`[, index]` 성분(§8.2 — 대안 노출·pairwise)은 순위 비교로 풀리지 않는다. 같은 SS 안에서
position만 다르기 때문이다. 그래서 위치 단계는 `is_replay_position()`이 따로 본다.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.state_machine import SS_RANK, FState, SsState

#: §3.1·§3.2 상태의 진행 순위. 클수록 뒤 단계다. 중단 상태(SS90·SS91)는 여기 없다 —
#: 순서 비교의 대상이 아니라 제출 거부의 사유이기 때문이다.
#: 표는 `state_machine.SS_RANK` 하나다 — rewind 방향 검증(§9.1.1)도 같은 표를 봐야 한다.
_SS_RANK = SS_RANK

_F_RANK: dict[FState, int] = {state: index for index, state in enumerate(FState)}


class Step(StrEnum):
    """§8.2의 제출 엔드포인트 = idempotency key의 `step` 성분."""

    CONSENT = "consent"
    CHECKPOINT_EDIT = "checkpoint_edit"
    CHECKPOINT_CONFIRM = "checkpoint_confirm"
    USER1 = "user1"
    SIDECAR = "sidecar"
    AI2 = "ai2"
    DOWNSTREAM = "downstream"
    RATINGS = "ratings"
    ALT_ADVANCE = "alt_advance"
    PAIRWISE = "pairwise"
    DEBRIEF = "debrief"


def ss_is_at_least(current: SsState, required: SsState) -> bool:
    """`current`가 `required` 이상 진행했는가."""
    if current not in _SS_RANK or required not in _SS_RANK:
        return False
    return _SS_RANK[current] >= _SS_RANK[required]


def f_is_at_least(current: FState, required: FState) -> bool:
    return _F_RANK[current] >= _F_RANK[required]


def is_replay_ss(current: SsState, step_completes_at: SsState) -> bool:
    """세션 수준 step의 재제출 여부 — 이미 그 step의 결과 상태에 도달했는가."""
    return ss_is_at_least(current, step_completes_at)


def is_replay_f(current: FState, step_completes_at: FState) -> bool:
    return f_is_at_least(current, step_completes_at)


def is_replay_position(
    current_ss: SsState, current_index: int | None, submitted: int, *, step_ss: SsState
) -> bool:
    """§3.3 위치 단계(P9·P10)의 재제출 판정 (NT-09 · NT-33).

    두 경우가 재제출이다.
    ① 세션이 이미 그 단계를 지나갔다 — 세 위치를 다 끝냈다는 뜻이다.
    ② 같은 단계 안에서 진행 위치가 이미 요청된 position보다 앞서 있다.

    ②가 없으면 새로고침 직후의 중복 클릭이 "위치 불일치" 409로 튄다. 반대로 **뒤의**
    position 요청은 재제출이 아니라 건너뛰기이므로 여기서 True를 주지 않는다 —
    `assert_position()`이 409로 끊는다.
    """
    if not ss_is_at_least(current_ss, step_ss):
        return False
    if current_ss is not step_ss:
        return True
    return current_index is not None and current_index > submitted
