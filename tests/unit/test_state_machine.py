"""SS·F 상태머신 (구현명세서 §3.1 · §3.2 · §3.3 · NT-14 · NT-33).

전이 **규칙** 층만 본다 — API 층의 409는 `tests/integration/test_session_flow.py`가 확인한다.
둘을 나눠 두는 이유: 규칙이 맞아도 라우터가 안 부르면 소용없고, 라우터가 불러도 규칙이
틀리면 소용없다. 각각 따로 깨져야 한다.
"""

from __future__ import annotations

import pytest

from app.core.state_machine import (
    ALT_POSITIONS,
    F_NEXT,
    INTERRUPT_STATES,
    PAIR_POSITIONS,
    POST_FOCAL_MEASURE_SS,
    SS_NEXT,
    TERMINAL_SS,
    Disposition,
    EndType,
    FState,
    IllegalTransition,
    SsState,
    alt_exposure_allowed,
    assert_f_transition,
    assert_position,
    assert_ss_transition,
    screen_for,
)


def test_ss_chain_is_linear_and_forward_only() -> None:
    """§3.1 — "각 상태의 다음 상태는 정확히 하나다. 역방향 간선 없음"."""
    order = [
        SsState.CREATED,
        SsState.CONSENT,
        SsState.CHECKPOINT,
        SsState.REENTRY,
        SsState.FOCAL,
        SsState.FOCAL_MEASURES,
        SsState.ALT_EXPOSURE,
        SsState.PAIRWISE,
        SsState.INTERVIEW,
        SsState.DEBRIEF,
        SsState.DONE,
    ]
    assert [state for state in SS_NEXT] == order[:-1]
    for current, expected in zip(order, order[1:], strict=False):
        assert SS_NEXT[current] is expected

    # 역방향 간선 0건 — 뒤 상태에서 앞 상태로 가는 전이가 표에 없다.
    rank = {state: index for index, state in enumerate(order)}
    for current, target in SS_NEXT.items():
        assert rank[target] == rank[current] + 1


def test_ss_skipping_a_state_is_illegal() -> None:
    """NT-14 — checkpoint 없이 focal, focal 없이 대안 노출."""
    with pytest.raises(IllegalTransition):
        assert_ss_transition(SsState.CONSENT, SsState.FOCAL)
    with pytest.raises(IllegalTransition):
        assert_ss_transition(SsState.FOCAL, SsState.ALT_EXPOSURE)
    with pytest.raises(IllegalTransition):
        assert_ss_transition(SsState.CREATED, SsState.DONE)


def test_interrupts_reachable_from_any_active_state() -> None:
    """§3.1 — SS90·SS91은 진행 중 어느 상태에서도 진입 가능, 종결 상태에서는 불가."""
    for state in SS_NEXT:
        for target in INTERRUPT_STATES:
            assert_ss_transition(state, target)
    for state in TERMINAL_SS:
        for target in INTERRUPT_STATES:
            with pytest.raises(IllegalTransition):
                assert_ss_transition(state, target)


def test_f_chain_has_no_branching() -> None:
    """§3.2 — F 전이에 갈래가 없다.

    v1.0.1의 B3는 disposition에 따라 둘로 갈렸지만(reply → B4 / no_reply·end → B6), v2에서는
    User1이 필수이고(D-32) F4의 reply/end가 **둘 다 F5**로 간다. 판정 코드 금지(§0.3)의
    상태머신 층 표현이다.
    """
    for state, targets in F_NEXT.items():
        assert len(targets) <= 1, f"{state}에 갈래가 생겼다 — §3.2는 단선이다"
    assert F_NEXT[FState.CLOSED] == frozenset()


def test_f_transition_rejects_skipping_sidecar() -> None:
    """NT-14 · NT-16 — sidecar(F2) 없이 AI2(F3)로 갈 수 없다."""
    with pytest.raises(IllegalTransition):
        assert_f_transition(FState.USER1, FState.AI2)
    with pytest.raises(IllegalTransition):
        assert_f_transition(FState.AI1_PENDING, FState.DOWNSTREAM)
    assert_f_transition(FState.SIDECAR, FState.AI2)


def test_no_ai3_state_exists() -> None:
    """D-33 — AI3가 없다. F 상태 목록과 turn role 어디에도 자리가 없다."""
    assert [state.value for state in FState] == ["F0", "F1", "F2", "F3", "F4", "F5"]


def test_disposition_has_no_no_reply() -> None:
    """D-32 — no_reply 분기 폐기. v1.0.1의 3분기가 2종으로 줄었다."""
    assert {item.value for item in Disposition} == {"reply", "end"}
    assert "no_reply" not in {item.value for item in Disposition}


def test_end_types_are_six_codes() -> None:
    """§4.7 — 이탈 유형 6코드(D-26)."""
    assert {item.value for item in EndType} == {
        "stop_here",
        "new_chat",
        "switch_ai",
        "seek_human",
        "no_further_need",
        "other",
    }


# --------------------------------------------------------------------------- #
# §3.3 위치 인덱스 (NT-33)
# --------------------------------------------------------------------------- #


def test_position_must_match_server_index() -> None:
    """NT-33 — position 건너뛰기 불가."""
    assert_position(2, 2, limit=ALT_POSITIONS, label="alt")
    with pytest.raises(IllegalTransition):
        assert_position(1, 2, limit=ALT_POSITIONS, label="alt")  # 건너뛰기
    with pytest.raises(IllegalTransition):
        assert_position(2, 1, limit=PAIR_POSITIONS, label="pair")  # 되돌아가기
    with pytest.raises(IllegalTransition):
        assert_position(1, 0, limit=PAIR_POSITIONS, label="pair")  # 범위 밖
    with pytest.raises(IllegalTransition):
        assert_position(3, 4, limit=PAIR_POSITIONS, label="pair")


# --------------------------------------------------------------------------- #
# NT-31 — 대안 노출 허용 구간
# --------------------------------------------------------------------------- #


def test_alt_exposure_allowed_only_after_focal_measures() -> None:
    """§1.2 · NT-31 — focal 측정(SS05) **완료** 전에는 대안 자극이 허용되지 않는다.

    SS05 자체가 포함되지 않는 것이 핵심이다 — 평정 화면은 아직 제출 전이고, 그 화면에
    대안이 실리면 평정이 오염된다.
    """
    forbidden = [
        SsState.CREATED,
        SsState.CONSENT,
        SsState.CHECKPOINT,
        SsState.REENTRY,
        SsState.FOCAL,
        SsState.FOCAL_MEASURES,
    ]
    for state in forbidden:
        assert not alt_exposure_allowed(state), f"{state}에서 대안이 허용됐다 (NT-31)"
    for state in POST_FOCAL_MEASURE_SS:
        assert alt_exposure_allowed(state)


# --------------------------------------------------------------------------- #
# 화면 매핑 (§0.2 P0–P12)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("ss_state", "f_state", "screen"),
    [
        (SsState.CREATED, None, "P0"),
        (SsState.CONSENT, None, "P1"),
        (SsState.CHECKPOINT, None, "P2"),
        (SsState.REENTRY, None, "P3"),
        (SsState.FOCAL, FState.AI1_PENDING, "P4"),
        (SsState.FOCAL, FState.USER1, "P4"),
        (SsState.FOCAL, FState.SIDECAR, "P5"),
        (SsState.FOCAL, FState.AI2, "P6"),
        (SsState.FOCAL, FState.DOWNSTREAM, "P7"),
        (SsState.FOCAL, FState.CLOSED, "P7"),
        (SsState.FOCAL_MEASURES, None, "P8"),
        (SsState.ALT_EXPOSURE, None, "P9"),
        (SsState.PAIRWISE, None, "P10"),
        (SsState.INTERVIEW, None, "P11"),
        (SsState.DEBRIEF, None, "P12"),
        (SsState.DONE, None, "DONE"),
        (SsState.RESEARCHER_ABORT, None, "ABORTED"),
        (SsState.DROPOUT, None, "ABORTED"),
    ],
)
def test_screen_mapping(ss_state: SsState, f_state: FState | None, screen: str) -> None:
    """§0.2 — 상태 → 화면. 13종(P0–P12) 전부 매핑된다."""
    assert screen_for(ss_state, f_state) == screen


def test_focal_without_f_state_is_broken_storage() -> None:
    """SS04인데 F 상태가 없으면 저장 상태가 깨진 것이다 — 조용히 그리지 않는다."""
    with pytest.raises(IllegalTransition):
        screen_for(SsState.FOCAL, None)


def test_all_screens_p0_to_p12_are_reachable() -> None:
    """§0.2 — 화면 13종이 전부 어떤 상태에서든 나온다(빠진 화면이 없다)."""
    reachable = {screen_for(SsState.FOCAL, f_state) for f_state in FState}
    reachable |= {
        screen_for(state, None) for state in SsState if state is not SsState.FOCAL
    }
    assert {f"P{index}" for index in range(13)} <= reachable
