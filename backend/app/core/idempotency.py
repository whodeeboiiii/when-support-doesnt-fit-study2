"""제출 idempotency (구현명세서 §3.5 · §9.1 · NT-09).

    중복 제출: 제출 단위 idempotency key(`session_id, branch_index, step`) —
    재제출은 200 + 기존 레코드 반환 (NT-09).

**별도 테이블을 두지 않는다.** §8.1 표에 idempotency 테이블이 없고, 필요도 없다 — 키의 세
성분이 이미 저장 상태에 있기 때문이다: 세션은 `sessions.ss_state`, branch는 `branches.b_state`,
그리고 각 step의 산출물(turn·sidecar_entry·rating 행)이 그 자체로 "이미 했다"의 증거다.

그래서 판정 규칙은 이렇게 정리된다.

1. 현재 상태가 **이 step을 아직 하지 않은** 상태다 → 정상 처리.
2. 현재 상태가 **이 step을 이미 지난** 상태다 → 재제출. 200 + 저장된 레코드(§9.1 "무반응").
3. 그 밖 → 비합법 전이(NT-14) → 409.

2와 3을 가르는 것은 상태의 **순서**다. 이 모듈은 그 순서 비교만 담당한다 — DB 조회는
호출부(라우터)가 한다.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.state_machine import BState, SsState

#: §3.1·§3.2 상태의 진행 순위. 클수록 뒤 단계다. 중단 상태(SS90·SS91)는 여기 없다 —
#: 순서 비교의 대상이 아니라 제출 거부의 사유이기 때문이다.
_SS_RANK: dict[SsState, int] = {
    SsState.CREATED: 0,
    SsState.JOINED_CONSENT: 1,
    SsState.PRESURVEY: 2,
    SsState.CHECKPOINT_REVIEW: 3,
    SsState.BRANCH_BLOCK: 4,
    SsState.CROSS_REVIEW: 5,
    SsState.DEBRIEF: 6,
    SsState.DONE: 7,
}

_B_RANK: dict[BState, int] = {state: index for index, state in enumerate(BState)}


class Step(StrEnum):
    """§8.2의 제출 엔드포인트 = idempotency key의 `step` 성분."""

    CONSENT = "consent"
    PRESURVEY = "presurvey"
    CHECKPOINT = "checkpoint"
    USER1 = "user1"
    SIDECAR = "sidecar"
    AI2 = "ai2"
    DOWNSTREAM = "downstream"
    RATINGS = "ratings"
    DEBRIEF = "debrief"


def ss_is_at_least(current: SsState, required: SsState) -> bool:
    """`current`가 `required` 이상 진행했는가."""
    if current not in _SS_RANK or required not in _SS_RANK:
        return False
    return _SS_RANK[current] >= _SS_RANK[required]


def b_is_at_least(current: BState, required: BState) -> bool:
    return _B_RANK[current] >= _B_RANK[required]


def is_replay_ss(current: SsState, step_completes_at: SsState) -> bool:
    """세션 수준 step의 재제출 여부 — 이미 그 step의 결과 상태에 도달했는가."""
    return ss_is_at_least(current, step_completes_at)


def is_replay_b(current: BState, step_completes_at: BState) -> bool:
    return b_is_at_least(current, step_completes_at)
