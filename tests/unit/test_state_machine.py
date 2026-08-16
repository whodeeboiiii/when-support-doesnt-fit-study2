"""NT-14의 규칙 층 — SS·B 전이표 자체 (구현명세서 §3.1 · §3.2 · §1.3).

API 층의 거부(409)는 `tests/integration/test_session_flow.py`가 본다. 여기서는 그 근거가 되는
표를 본다 — 표에 없는 간선은 만들어지지 않았는가, 역방향 간선이 몰래 생기지 않았는가.

"연구 상태는 뒤로 돌리지 않는다"(§1.3)는 원칙은 코드 한 줄로 보이지 않는다. 전이표에 역방향
간선이 **없다**는 사실로만 보인다.
"""

from __future__ import annotations

import itertools

import pytest

from app.core.state_machine import (
    ACTIVE_SS,
    B_NEXT,
    INTERRUPT_STATES,
    SS_NEXT,
    TERMINAL_SS,
    BState,
    Disposition,
    IllegalTransition,
    SsState,
    assert_b_transition,
    assert_ss_transition,
    b_state_after_sidecar,
    has_ai2,
    screen_for,
)


def test_ss_states_match_the_spec_table() -> None:
    """§3.1 — SS00–SS07 + SS90 + SS91."""
    assert [state.value for state in SsState] == [
        "SS00",
        "SS01",
        "SS02",
        "SS03",
        "SS04",
        "SS05",
        "SS06",
        "SS07",
        "SS90",
        "SS91",
    ]


def test_b_states_match_the_spec_table() -> None:
    """§3.2 — B0–B7."""
    assert [state.value for state in BState] == [f"B{n}" for n in range(8)]


def test_ss_chain_is_linear_and_forward_only() -> None:
    assert SS_NEXT[SsState.CREATED] is SsState.JOINED_CONSENT
    assert SS_NEXT[SsState.BRANCH_BLOCK] is SsState.CROSS_REVIEW
    assert SS_NEXT[SsState.DEBRIEF] is SsState.DONE
    for current, target in SS_NEXT.items():
        assert SS_NEXT.get(target) is not current, f"역방향 간선: {target} → {current}"


@pytest.mark.parametrize(
    "current,target",
    [
        (SsState.CREATED, SsState.PRESURVEY),  # 동의를 건너뛴다
        (SsState.PRESURVEY, SsState.BRANCH_BLOCK),  # 사전설문 제출 없이 branch
        (SsState.CROSS_REVIEW, SsState.BRANCH_BLOCK),  # 뒤로
        (SsState.DONE, SsState.DEBRIEF),  # 종결 후 되돌리기
    ],
)
def test_illegal_ss_transitions(current: SsState, target: SsState) -> None:
    with pytest.raises(IllegalTransition):
        assert_ss_transition(current, target)


@pytest.mark.parametrize("state", sorted(ACTIVE_SS, key=lambda s: s.value))
@pytest.mark.parametrize("interrupt", sorted(INTERRUPT_STATES, key=lambda s: s.value))
def test_abort_and_dropout_are_reachable_from_every_active_state(
    state: SsState, interrupt: SsState
) -> None:
    """§3.1 — 연구자 개입(abort·dropout)은 진행 중 어느 상태에서도 가능해야 한다(§9.2 안전)."""
    assert_ss_transition(state, interrupt)


@pytest.mark.parametrize("terminal", sorted(TERMINAL_SS, key=lambda s: s.value))
def test_terminal_states_accept_no_further_transition(terminal: SsState) -> None:
    for interrupt in INTERRUPT_STATES:
        with pytest.raises(IllegalTransition):
            assert_ss_transition(terminal, interrupt)


def test_b_chain_matches_the_spec_table() -> None:
    """§3.2 — B3에서만 갈래가 둘이다(reply → B4, no_reply·end → B6)."""
    assert B_NEXT[BState.SIDECAR] == frozenset({BState.AI2, BState.RATINGS})
    assert B_NEXT[BState.AI2] == frozenset({BState.DOWNSTREAM})
    assert B_NEXT[BState.RESET_DONE] == frozenset()


@pytest.mark.parametrize(
    "current,target",
    [
        (BState.SIDECAR, BState.DOWNSTREAM),  # NT-14 예시 — B4 없이 B5
        (BState.REENTRY, BState.USER1),  # AI1 표시 없이 User1
        (BState.USER1, BState.AI2),  # sidecar 없이 AI2 (§0.4 sidecar 배치 동결)
        (BState.RATINGS, BState.AI2),  # 평정 뒤에 AI2
        (BState.DOWNSTREAM, BState.AI2),  # 뒤로
    ],
)
def test_illegal_b_transitions(current: BState, target: BState) -> None:
    with pytest.raises(IllegalTransition):
        assert_b_transition(current, target)


def test_no_backward_edges_in_branch_chain() -> None:
    order = list(BState)
    for current, targets in B_NEXT.items():
        for target in targets:
            assert order.index(target) > order.index(current), f"역방향: {current} → {target}"


def test_sidecar_routing_is_the_only_disposition_branch() -> None:
    """§3.2 · NT-17 — no_reply/end는 AI2·downstream을 건너뛴다(실패가 아니라 다른 trajectory)."""
    assert b_state_after_sidecar(Disposition.REPLY) is BState.AI2
    assert b_state_after_sidecar(Disposition.NO_REPLY) is BState.RATINGS
    assert b_state_after_sidecar(Disposition.END) is BState.RATINGS
    assert has_ai2(Disposition.REPLY) is True
    assert has_ai2(Disposition.NO_REPLY) is False
    assert has_ai2(None) is False


def test_every_branch_path_ends_at_ratings() -> None:
    """D-22 — 세 종결 유형 전부 B6(12문항 2블록)를 지나 B7에서 끝난다."""
    for disposition in Disposition:
        state = b_state_after_sidecar(disposition)
        visited = [state]
        while B_NEXT[state]:
            assert len(B_NEXT[state]) == 1, f"{state} 이후에 갈래가 생겼다"
            state = next(iter(B_NEXT[state]))
            visited.append(state)
        assert BState.RATINGS in visited
        assert visited[-1] is BState.RESET_DONE


@pytest.mark.parametrize(
    "ss_state,b_state,expected",
    [
        (SsState.CREATED, None, "P0"),
        (SsState.JOINED_CONSENT, None, "P1"),
        (SsState.PRESURVEY, None, "P2"),
        (SsState.CHECKPOINT_REVIEW, None, "P3"),
        (SsState.BRANCH_BLOCK, BState.REENTRY, "P4"),
        (SsState.BRANCH_BLOCK, BState.AI1_SHOWN, "P5"),
        (SsState.BRANCH_BLOCK, BState.USER1, "P5"),
        (SsState.BRANCH_BLOCK, BState.SIDECAR, "P6"),
        (SsState.BRANCH_BLOCK, BState.AI2, "P7"),
        (SsState.BRANCH_BLOCK, BState.DOWNSTREAM, "P8"),
        (SsState.BRANCH_BLOCK, BState.RATINGS, "P9"),
        (SsState.CROSS_REVIEW, None, "P10"),
        (SsState.DEBRIEF, None, "P11"),
        (SsState.RESEARCHER_ABORT, None, "ABORTED"),
        (SsState.DROPOUT, None, "ABORTED"),
    ],
)
def test_screen_mapping(ss_state: SsState, b_state: BState | None, expected: str) -> None:
    """§3.1·§3.2 표의 화면 열."""
    assert screen_for(ss_state, b_state) == expected


def test_screen_ids_are_within_the_reserved_range() -> None:
    """§1.5-8 ID 예약 — 참가자 화면은 P0–P11 12종뿐이다(§0.2)."""
    screens = {screen_for(SsState.BRANCH_BLOCK, b) for b in BState}
    screens |= {
        screen_for(state, None) for state in SsState if state is not SsState.BRANCH_BLOCK
    }
    participant_screens = {name for name in screens if name.startswith("P")}
    assert participant_screens <= {f"P{n}" for n in range(12)}


def test_ss04_without_branch_state_is_a_broken_record() -> None:
    with pytest.raises(IllegalTransition):
        screen_for(SsState.BRANCH_BLOCK, None)


def test_state_ids_do_not_collide_with_condition_ids() -> None:
    """§1.5-8 — C1–C4는 실험 조건 전용이다. 상태 ID가 그 공간을 침범하지 않는다."""
    all_states = {state.value for state in SsState} | {state.value for state in BState}
    assert not all_states & {"C1", "C2", "C3", "C4"}


def test_no_acceptance_or_routing_vocabulary_in_the_state_machine() -> None:
    """§1.5-10 · §0.3 — 판정·라우팅·eligible 개념은 이 시스템에 없다."""
    import inspect

    from app.core import state_machine

    source = inspect.getsource(state_machine).lower()
    for banned in ("acceptance", "eligible", "routing", "route_to"):
        assert banned not in source, f"금지 어휘: {banned}"


def test_state_machine_has_no_disposition_dependent_rating_variants() -> None:
    """D-22 — 종결 유형별 축소형 문항은 없다. 분기 함수는 sidecar 다음 상태 하나뿐이다."""
    from app.assets import rating_items

    assert rating_items.ITEM_COUNT == 12
    assert len(rating_items.items_in_block(rating_items.BLOCK_ANCHOR)) == 2
    assert len(rating_items.items_in_block(rating_items.BLOCK_INTERACTION)) == 10


def test_all_b_states_have_a_screen() -> None:
    for b_state in BState:
        assert screen_for(SsState.BRANCH_BLOCK, b_state).startswith("P")


def test_transition_tables_cover_every_state() -> None:
    """표에 빠진 상태가 생기면 KeyError가 아니라 여기서 잡힌다."""
    assert set(B_NEXT) == set(BState)
    assert set(SS_NEXT) | TERMINAL_SS == set(SsState)
    assert not set(itertools.chain.from_iterable(B_NEXT.values())) - set(BState)
