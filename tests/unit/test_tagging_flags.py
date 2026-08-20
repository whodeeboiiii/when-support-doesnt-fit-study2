"""사후 태깅 플래그 (구현명세서 §7.6 · 부록 B).

핵심은 **모르는 것을 모른다고 말하는가**다. `carryover_sensitive`는 사람의 코딩 없이는
산출할 수 없고, 그때 열은 빈 칸이어야 한다 — False로 채우면 "이전 branch에서 표현되지
않았다"는 판정을 시스템이 몰래 내린 것이 된다(§7.2 "부재≠정보 없음"과 같은 규율).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis import tagging_flags


def test_first_opportunity_is_branch_one() -> None:
    """§7.6 — 네 branch가 같은 사건을 반복하므로 첫 표현 기회는 branch 1이다."""
    assert tagging_flags.flags_for("P01", 1).first_opportunity is True
    assert [tagging_flags.flags_for("P01", b).first_opportunity for b in (2, 3, 4)] == [
        False,
        False,
        False,
    ]


def test_carryover_is_blank_without_coding() -> None:
    flags = tagging_flags.flags_for("P01", 3)
    assert flags.carryover_sensitive is None
    assert flags.carryover_source == tagging_flags.UNCODED
    assert flags.as_row()["carryover_sensitive"] == ""


def test_carryover_uses_earlier_branches_only() -> None:
    coding = {("P01", 1): False, ("P01", 2): True, ("P01", 3): False, ("P01", 4): False}
    assert tagging_flags.flags_for("P01", 1, coding).carryover_sensitive is False
    assert tagging_flags.flags_for("P01", 2, coding).carryover_sensitive is False
    # branch 2에서 표현됐으므로 3·4는 carryover 민감 관측이다.
    assert tagging_flags.flags_for("P01", 3, coding).carryover_sensitive is True
    assert tagging_flags.flags_for("P01", 4, coding).carryover_sensitive is True


def test_partial_coding_leaves_the_flag_blank() -> None:
    """이전 branch 중 하나라도 코딩이 없으면 판정하지 않는다."""
    coding = {("P01", 1): False}  # branch 2가 비어 있다
    assert tagging_flags.flags_for("P01", 3, coding).carryover_sensitive is None
    assert tagging_flags.flags_for("P01", 2, coding).carryover_sensitive is False


def test_sensitivity_subsets(tmp_path: Path) -> None:
    """§7.6 — first-branch only / 첫 2 branch 서브셋 플래그."""
    subsets = [
        (
            tagging_flags.flags_for("P02", index).subset_first_branch_only,
            tagging_flags.flags_for("P02", index).subset_first_two_branches,
        )
        for index in (1, 2, 3, 4)
    ]
    assert subsets == [(True, True), (False, True), (False, False), (False, False)]


def test_load_coding_parses_a_csv(tmp_path: Path) -> None:
    path = tmp_path / "coding.csv"
    path.write_text(
        "participant_no,branch_index,focal_content_expressed\np01,1,yes\nP01,2,0\n",
        encoding="utf-8",
    )
    assert tagging_flags.load_coding(path) == {("P01", 1): True, ("P01", 2): False}


def test_load_coding_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("participant_no,branch_index\nP01,1\n", encoding="utf-8")
    with pytest.raises(tagging_flags.CodingInputError, match="필수 열"):
        tagging_flags.load_coding(path)


def test_load_coding_rejects_unreadable_values(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "participant_no,branch_index,focal_content_expressed\nP01,1,아마도\n", encoding="utf-8"
    )
    with pytest.raises(tagging_flags.CodingInputError):
        tagging_flags.load_coding(path)


def test_annotate_adds_every_flag_column() -> None:
    rows = [{"participant_no": "P03", "branch_index": 2, "value": 1}]
    annotated = tagging_flags.annotate(rows)
    assert set(tagging_flags.FLAG_COLUMNS) <= set(annotated[0])
    assert annotated[0]["value"] == 1, "원래 열을 잃지 않는다"
