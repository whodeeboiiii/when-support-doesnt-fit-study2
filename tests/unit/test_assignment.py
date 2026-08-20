"""배정표 계약 (구현명세서 §5.2 · §3.3 · NT-32).

**시스템은 배정을 계산하지 않는다**(D-30). 그래서 여기서 검증하는 것은 "잘 뽑는가"가 아니라
**"어긋난 표를 거부하는가"**다 — 로더가 통과시킨 표는 §5.2의 제약을 전부 만족한다는 것이
런타임 전체가 기대는 전제이기 때문이다.

생성기(`scripts/make_assignment.py`)와 로더가 **같은 검증 함수**를 쓴다. 생성이 통과시킨 표를
로더가 거부하거나 그 반대가 되면 어느 쪽이 정본인지 알 수 없어진다.
"""

from __future__ import annotations

import json
from itertools import permutations
from pathlib import Path

import pytest

from app.core import assignment
from app.core.assignment import (
    CONTRAST_PAIR,
    CONTRASTS,
    EXPECTED_N,
    FOCAL_PER_CONDITION,
    AssignmentContractError,
    AssignmentRow,
    check_constraints,
)

DUMMY_PATH = Path(assignment.DUMMY_ASSIGNMENT_PATH)


@pytest.fixture
def table() -> assignment.AssignmentTable:
    assignment.reset_cache()
    return assignment.load()


def _rows(table: assignment.AssignmentTable) -> list[AssignmentRow]:
    return list(table.rows.values())


# --------------------------------------------------------------------------- #
# NT-32 — dummy 표가 제약을 전부 만족한다
# --------------------------------------------------------------------------- #


def test_dummy_table_is_committed_and_loads(table: assignment.AssignmentTable) -> None:
    """§5.2 — dummy는 커밋 대상이고 CI가 이걸로 돈다. `is_dummy`를 감추지 않는다(NT-42)."""
    assert DUMMY_PATH.is_file()
    assert table.is_dummy is True
    assert len(table.rows) == EXPECTED_N


def test_row_count_is_exactly_24(table: assignment.AssignmentTable) -> None:
    """§0.4 — **N=24 고정, fallback 없음**(D-30)."""
    assert len(_rows(table)) == EXPECTED_N
    numbers = [row.participant_no for row in _rows(table)]
    assert len(set(numbers)) == EXPECTED_N, "참가자 번호 중복"


def test_focal_balance_six_per_condition(table: assignment.AssignmentTable) -> None:
    """§5.2 ① — focal 6명/조건."""
    counts: dict[str, int] = {}
    for row in _rows(table):
        counts[row.focal_condition] = counts.get(row.focal_condition, 0) + 1
    assert counts == {condition: FOCAL_PER_CONDITION for condition in ("C1", "C2", "C3", "C4")}


def test_alt_order_excludes_focal_and_covers_six_permutations(
    table: assignment.AssignmentTable,
) -> None:
    """§3.3 · §5.2 ② — alt_order는 focal을 **제외한** 세 조건의 순열이고, group 내 6종 각 1회."""
    by_focal: dict[str, list[tuple[str, ...]]] = {}
    for row in _rows(table):
        assert row.focal_condition not in row.alt_order, "alt_order에 focal이 들어 있다 (NT-32)"
        assert len(row.alt_order) == 3
        by_focal.setdefault(row.focal_condition, []).append(row.alt_order)

    for condition, orders in by_focal.items():
        expected = set(permutations(sorted({"C1", "C2", "C3", "C4"} - {condition})))
        assert set(orders) == expected
        assert len(orders) == len(set(orders)), f"focal {condition}: alt_order 중복"


def test_pair_order_six_permutations_four_times_each(
    table: assignment.AssignmentTable,
) -> None:
    """§5.2 ③ — pair_order 6순열이 focal group마다 1:1 → 전체 각 4회."""
    counts: dict[tuple[str, ...], int] = {}
    for row in _rows(table):
        assert sorted(row.pair_order) == sorted(CONTRASTS)
        counts[row.pair_order] = counts.get(row.pair_order, 0) + 1
    assert len(counts) == 6
    assert set(counts.values()) == {EXPECTED_N // 6}


def test_side_balance_twelve_twelve(table: assignment.AssignmentTable) -> None:
    """§5.2 ④ — contrast별 전체 12/12, focal group 내 3/3."""
    for contrast in CONTRASTS:
        first = sorted(CONTRAST_PAIR[contrast])[0]
        left_total = sum(1 for row in _rows(table) if row.sides(contrast)[0] == first)
        assert left_total == EXPECTED_N // 2, f"{contrast} 좌우 균형: {left_total}/24"

        by_focal: dict[str, int] = {}
        sizes: dict[str, int] = {}
        for row in _rows(table):
            sizes[row.focal_condition] = sizes.get(row.focal_condition, 0) + 1
            if row.sides(contrast)[0] == first:
                by_focal[row.focal_condition] = by_focal.get(row.focal_condition, 0) + 1
        for condition, size in sizes.items():
            assert by_focal.get(condition, 0) == size // 2


def test_pair_sides_only_use_the_contrast_conditions(
    table: assignment.AssignmentTable,
) -> None:
    """§0.4 — Sequence(C2 vs C4)·Scope(C1 vs C3)·Stopping(C3 vs C4)만 존재한다(§1.5-6)."""
    for row in _rows(table):
        for contrast in CONTRASTS:
            assert frozenset(row.sides(contrast)) == CONTRAST_PAIR[contrast]


def test_strata_spread_is_reported(table: assignment.AssignmentTable) -> None:
    """§5.2 ⑤ — 편중은 **경고**이지 오류가 아니다. 산출은 되어야 한다."""
    report = assignment.strata_spread(_rows(table))
    assert set(report) == {"a_level", "warnings"}
    for entry in report["a_level"].values():
        assert set(entry) == {"counts", "n", "max_diff"}


def test_constraints_checked_flags_are_true(table: assignment.AssignmentTable) -> None:
    """§5.2 스키마 — 생성기가 남긴 자기 보고. 로더의 검증과 별개로 파일에 남아 있어야 한다."""
    checked = dict(table.constraints_checked)
    for key in ("focal_balance", "alt_order_latin", "pair_order_4x", "side_balance"):
        assert checked.get(key) is True, f"{key}가 참이 아니다"


# --------------------------------------------------------------------------- #
# 거부 — 어긋난 표는 기동을 끊는다
# --------------------------------------------------------------------------- #


def _document() -> dict:
    return json.loads(DUMMY_PATH.read_text(encoding="utf-8"))


def _parse(document: dict) -> assignment.AssignmentTable:
    return assignment.parse(document, source_path=DUMMY_PATH, is_dummy=True)


def test_rejects_focal_in_alt_order() -> None:
    """§3.3 — "배정표 행의 alt_order가 focal을 포함하면 로더가 기동을 끊는다"(NT-32)."""
    document = _document()
    row = document["rows"][0]
    row["alt_order"] = [row["focal_condition"], *row["alt_order"][:2]]
    with pytest.raises(AssignmentContractError, match="alt_order"):
        _parse(document)


def test_rejects_wrong_row_count() -> None:
    """N=24 고정 — 23행도 25행도 받지 않는다(D-30)."""
    document = _document()
    document["rows"] = document["rows"][:-1]
    with pytest.raises(AssignmentContractError, match="행 수"):
        _parse(document)


def test_rejects_duplicate_participant() -> None:
    document = _document()
    document["rows"][1] = dict(document["rows"][0])
    with pytest.raises(AssignmentContractError, match="중복"):
        _parse(document)


def test_rejects_broken_focal_balance() -> None:
    """조건당 6명이 아니면 거부 — 한 행의 focal만 바꿔도 걸린다."""
    document = _document()
    victim = next(row for row in document["rows"] if row["focal_condition"] == "C1")
    victim["focal_condition"] = "C2"
    # alt_order도 함께 깨지므로 사유가 둘 이상이다 — 어느 쪽이든 거부면 계약은 지켜진다.
    with pytest.raises(AssignmentContractError):
        _parse(document)


def test_rejects_wrong_contrast_pair() -> None:
    """§0.4 — Scope는 C1 vs C3다. 다른 쌍을 넣으면 거부."""
    document = _document()
    document["rows"][0]["pair_sides"]["scope"] = ["C1", "C4"]
    with pytest.raises(AssignmentContractError, match="scope"):
        _parse(document)


def test_rejects_unknown_contrast_in_pair_order() -> None:
    """§1.5-6 — 세 contrast만 존재한다. 네 번째 pair를 만들 수 없다."""
    document = _document()
    document["rows"][0]["pair_order"] = ["sequence", "scope", "recognition"]
    with pytest.raises(AssignmentContractError, match="pair_order"):
        _parse(document)


# --------------------------------------------------------------------------- #
# 생성기 self-test (§10.1)
# --------------------------------------------------------------------------- #


def test_generator_self_test_passes() -> None:
    """§10.1 — "임의 strata 분포 20종에 대해 제약 전수 통과"(NT-32).

    A0가 1건뿐인 극단 분포까지 포함한다. strata 편중은 **경고**이므로 통과 기준이 아니다.
    """
    import sys

    sys.path.insert(0, str(Path(assignment.REPO_ROOT)))
    from scripts.make_assignment import self_test

    assert self_test() == 0


def test_generator_and_loader_share_the_check() -> None:
    """생성기와 로더가 같은 함수를 쓴다 — 갈라지면 어느 쪽이 정본인지 알 수 없다."""
    from scripts import make_assignment

    assert make_assignment.check_constraints is check_constraints
