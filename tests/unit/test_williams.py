"""NT-06 — Williams 표·순환 매핑 검증 (구현명세서 §3.3 · D-09).

§3.3이 주장하는 두 성질을 표에서 직접 확인한다.

1. 네 조건이 **각 serial position에 1회씩** 나타난다.
2. 12개 **directed first-order adjacent pair**가 전 sequence에 걸쳐 각 1회씩 나타난다.

이 성질이 깨지면 counterbalancing이 균형화 장치이기를 그친다(§3.3 — carryover 제거가 아니라
균형화). 표를 손으로 고칠 일이 생기면 이 테스트가 먼저 깨져야 한다.
"""

from __future__ import annotations

import itertools

import pytest

from app.assets.dossier_loader import CONDITIONS
from app.core.williams import BRANCH_INDICES, SEQUENCES, condition, sequence, sequence_index

PARTICIPANTS = tuple(f"P{n:02d}" for n in range(1, 13))


def test_four_sequences_of_four_conditions() -> None:
    assert sorted(SEQUENCES) == [1, 2, 3, 4]
    for index, row in SEQUENCES.items():
        assert sorted(row) == sorted(CONDITIONS), f"S{index}: 네 조건이 1회씩이어야 한다"


def test_each_condition_appears_once_per_serial_position() -> None:
    for position in range(4):
        column = sorted(row[position] for row in SEQUENCES.values())
        assert column == sorted(CONDITIONS), f"position {position + 1}: 조건 분포가 어긋난다"


def test_twelve_directed_adjacent_pairs_each_appear_once() -> None:
    pairs = [
        (row[index], row[index + 1]) for row in SEQUENCES.values() for index in range(3)
    ]
    expected = {(a, b) for a, b in itertools.permutations(CONDITIONS, 2)}
    assert len(pairs) == 12
    assert set(pairs) == expected
    assert len(set(pairs)) == len(pairs), "adjacent pair가 중복된다"


@pytest.mark.parametrize("participant_no", PARTICIPANTS)
def test_sequence_index_is_the_cyclic_mapping(participant_no: str) -> None:
    """§3.3 `(참가자 번호 − 1) mod 4 + 1`."""
    number = int(participant_no[1:])
    assert sequence_index(participant_no) == (number - 1) % 4 + 1


def test_spec_table_participant_assignment() -> None:
    """§3.3 표의 '배정 참가자' 열 그대로."""
    assigned = {index: [] for index in SEQUENCES}
    for participant_no in PARTICIPANTS:
        assigned[sequence_index(participant_no)].append(participant_no)
    assert assigned == {
        1: ["P01", "P05", "P09"],
        2: ["P02", "P06", "P10"],
        3: ["P03", "P07", "P11"],
        4: ["P04", "P08", "P12"],
    }


@pytest.mark.parametrize("participant_no", PARTICIPANTS)
def test_condition_matches_the_sequence_row(participant_no: str) -> None:
    row = sequence(participant_no)
    for branch_index in BRANCH_INDICES:
        assert condition(participant_no, branch_index) == row[branch_index - 1]


def test_every_participant_sees_all_four_conditions() -> None:
    """within-participants 설계의 최소 조건 — 12명 전원이 C1–C4를 한 번씩 본다(§0.1)."""
    for participant_no in PARTICIPANTS:
        seen = [condition(participant_no, index) for index in BRANCH_INDICES]
        assert sorted(seen) == sorted(CONDITIONS)


def test_p00_is_deterministic_too() -> None:
    """P00은 QA 전용이지만 배정 규칙 예외가 아니다 — `(0−1) mod 4 + 1 = 4`."""
    assert sequence_index("P00") == 4
    assert sequence("P00") == SEQUENCES[4]


@pytest.mark.parametrize("bad", ["P1", "p01", "13", "PXX", ""])
def test_malformed_participant_number_is_refused(bad: str) -> None:
    """배정을 추측하지 않는다 — 형식이 어긋나면 멈춘다."""
    with pytest.raises(ValueError):
        sequence_index(bad)


@pytest.mark.parametrize("bad_index", [0, 5, -1])
def test_branch_index_out_of_range(bad_index: int) -> None:
    with pytest.raises(ValueError):
        condition("P01", bad_index)
