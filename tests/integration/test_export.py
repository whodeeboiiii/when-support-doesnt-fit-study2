"""분석 export (구현명세서 §7.7 · 부록 B · §2.9 · NT-30 개정).

세 가지를 본다.
1. **비식별·자유 텍스트 분리** — 기본 실행의 어떤 파일에도 참가자·연구자가 쓴 문장이 없다.
   `--include-text`를 준 실행만 `free_text.csv`를 만든다.
2. **v2 파일 구성** — trajectory · checkpoint_edits · ratings · pairwise · alt_exposure ·
   generation_integrity · events · dossier_provenance (부록 H.2).
3. **삭제된 열이 돌아오지 않는다** — `sequence_index`·`branch_index`·`normalization_*`·
   `presurvey_*`·`first_opportunity`·`carryover_sensitive`(부록 B 삭제 목록).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis import export_trajectory
from app.models import tables
from tests import helpers

#: 세션에 심어 두고 기본 export에 새지 않는지 보는 문장들.
USER1_TEXT = "장기 계획 말고 두 선택지 비교만 해줘"
SIDECAR_TEXT = "사실은 이직 쪽으로 이미 기울어 있었다"
REASON_TEXT = "다시 설명하기가 번거로웠다"
EDIT_TEXT = "실제로는 3년이 아니라 5년 계획을 제시했다"
END_REASON = "지금은 여기까지면 충분하다"


@pytest.fixture
async def exported(client: AsyncClient, session: AsyncSession):
    """자유 텍스트를 전부 심은 완주 세션 1건."""
    await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.edit_checkpoint(client, "problematic_ai_response", EDIT_TEXT)
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")

    await client.post("/api/focal/user1", json={"text": USER1_TEXT})
    await client.post(
        "/api/focal/sidecar",
        json={
            "has_more": True,
            "free_text": SIDECAR_TEXT,
            "provenance": "preexisting",
            "reason": REASON_TEXT,
        },
    )
    await client.post("/api/focal/ai2")
    await helpers.advance(client, "P6")
    await client.post(
        "/api/focal/downstream",
        json={"disposition": "end", "end_type": "seek_human", "reason": END_REASON},
    )
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)
    return session


def _all_text(tables_: export_trajectory.ExportTables, *, include_free_text: bool) -> str:
    files = tables_.as_files()
    if not include_free_text:
        files.pop(export_trajectory.FREE_TEXT_FILE, None)
    return "\n".join(
        str(value) for rows in files.values() for row in rows for value in row.values()
    )


# --------------------------------------------------------------------------- #
# NT-30 — 비식별 · 자유 텍스트 opt-in 분리
# --------------------------------------------------------------------------- #


async def test_default_export_has_no_free_text(exported: AsyncSession) -> None:
    """§2.9 — 기본 출력에는 참가자·연구자가 쓴 문장이 **한 글자도** 없다."""
    result = await export_trajectory.collect(exported, actor="tester")
    text = _all_text(result, include_free_text=False)
    for secret in (USER1_TEXT, SIDECAR_TEXT, REASON_TEXT, EDIT_TEXT, END_REASON):
        assert secret not in text, f"기본 export에 자유 텍스트가 있다: {secret[:12]}…"
    assert result.free_text == [], "--include-text 없이 free_text가 채워졌다"


async def test_include_text_creates_a_separate_file(exported: AsyncSession) -> None:
    """NT-30 — `--include-text`만 `free_text.csv`를 만든다. 열이 아니라 **파일** 분리다."""
    result = await export_trajectory.collect(exported, actor="tester", include_text=True)
    assert export_trajectory.FREE_TEXT_FILE in result.as_files()

    fields = {row["field"] for row in result.free_text}
    assert {"user1", "sidecar_text", "sidecar_reason", "end_reason"} <= fields
    assert any("checkpoint_edit" in field for field in fields), "수정 원문·수정본이 빠졌다"

    # 다른 파일들은 여전히 깨끗하다.
    text = _all_text(result, include_free_text=False)
    assert SIDECAR_TEXT not in text


async def test_lengths_are_exported_without_the_text(exported: AsyncSession) -> None:
    """§7.4 — 텍스트 **길이**는 행동 측정이라 기본 실행에도 나간다(그래서 복호화가 필요하다)."""
    result = await export_trajectory.collect(exported, actor="tester")
    row = result.trajectory[0]
    assert row["user1_chars"] == len(USER1_TEXT)
    assert row["sidecar_text_chars"] == len(SIDECAR_TEXT)
    assert row["end_reason_chars"] == len(END_REASON)


async def test_no_identifiers_in_any_file(exported: AsyncSession) -> None:
    """§2.9 — 접속 코드·user_agent·viewport는 어떤 파일에도 나가지 않는다."""
    result = await export_trajectory.collect(exported, actor="tester", include_text=True)
    text = _all_text(result, include_free_text=True)
    for banned in ("user_agent", "access_code", "Mozilla", "viewport", "reason_encrypted"):
        assert banned not in text


async def test_export_records_audit_regardless_of_flag(exported: AsyncSession) -> None:
    """§2.9 — 실행 1회당 `export`·`decrypt` 각 1행. 열지 않은 척할 수 있으면 audit이 아니다."""
    await export_trajectory.collect(exported, actor="tester")
    rows = (await exported.execute(select(tables.AuditLog))).scalars().all()
    actions = [row.action for row in rows if row.actor == "tester"]
    assert actions.count("export") == 1
    assert actions.count("decrypt") == 1


# --------------------------------------------------------------------------- #
# 파일 구성 (부록 H.2)
# --------------------------------------------------------------------------- #


async def test_all_seven_default_files_exist(exported: AsyncSession) -> None:
    """부록 H.2 — trajectory·checkpoint_edits·ratings·pairwise·alt_exposure·integrity·events."""
    files = await export_trajectory.collect(exported, actor="tester")
    names = set(files.as_files())
    assert names == {
        export_trajectory.TRAJECTORY_FILE,
        export_trajectory.CHECKPOINT_EDITS_FILE,
        export_trajectory.RATINGS_FILE,
        export_trajectory.PAIRWISE_FILE,
        export_trajectory.ALT_EXPOSURE_FILE,
        export_trajectory.INTEGRITY_FILE,
        export_trajectory.EVENTS_FILE,
        export_trajectory.PROVENANCE_FILE,
    }


async def test_trajectory_is_one_row_per_participant(exported: AsyncSession) -> None:
    """D-23 — focal between이므로 참가자 1행이다(v1.0.1의 participant × condition 4행이 아니다)."""
    result = await export_trajectory.collect(exported, actor="tester")
    assert len(result.trajectory) == 1
    row = result.trajectory[0]
    assert row["focal_condition"] in {"C1", "C2", "C3", "C4"}
    assert row["downstream_disposition"] == "end"
    assert row["downstream_end_type"] == "seek_human"


async def test_pairwise_carries_focal_included(exported: AsyncSession) -> None:
    """§7.5 · 초안 §7.12 — focal-status sensitivity의 입력이다."""
    result = await export_trajectory.collect(exported, actor="tester")
    assert len(result.pairwise) == 3
    for row in result.pairwise:
        assert row["contrast"] in {"sequence", "scope", "stopping"}
        assert row["focal_included"] in {True, False}
        assert row["left_condition"] != row["right_condition"]
    # P00은 focal C1 — scope(C1 vs C3)에만 focal이 포함된다.
    included = {row["contrast"] for row in result.pairwise if row["focal_included"]}
    assert included == {"scope"}


async def test_checkpoint_edits_carry_lengths_not_sentences(
    exported: AsyncSession,
) -> None:
    """§7.7 — 수정의 성격은 사후 코딩이다. 기본 export는 **길이·segment**만 준다."""
    result = await export_trajectory.collect(exported, actor="tester")
    assert len(result.checkpoint_edits) == 1
    row = result.checkpoint_edits[0]
    assert row["segment"] == "problematic_ai_response"
    # trouble_cue·problematic_ai_response는 자극 전제 segment다(§3.4).
    assert row["alert_segment"] is True
    assert row["edited_chars"] == len(EDIT_TEXT)
    assert "original" not in row or not isinstance(row.get("original"), str)


async def test_alt_exposure_records_the_assigned_order(exported: AsyncSession) -> None:
    """§4.9 — 순서·조건·시각. 배정표대로다."""
    result = await export_trajectory.collect(exported, actor="tester")
    assert [row["position"] for row in result.alt_exposure] == [1, 2, 3]
    assert len({row["condition"] for row in result.alt_exposure}) == 3


async def test_generation_integrity_has_machine_columns(exported: AsyncSession) -> None:
    """§7.7 — AI2 행동 코딩의 **기계 열**(길이·질문 수·fallback). 내용 코딩은 사람이 한다."""
    result = await export_trajectory.collect(exported, actor="tester")
    assert result.integrity
    row = result.integrity[0]
    for column in ("output_chars", "output_questions", "fallback_used", "alt_overlap"):
        assert column in row


async def test_provenance_table_reports_composition(exported: AsyncSession) -> None:
    """§7.7 — provenance 구성비(초안 §7.3 hierarchy, 논문 보고용). 자산에서 산출한다."""
    result = await export_trajectory.collect(exported, actor="tester")
    assert result.provenance
    row = next(entry for entry in result.provenance if entry["participant_no"] == "P00")
    assert row["verbatim_log"] + row["participant_quote"] + row["researcher_paraphrase"] == 5
    assert abs(sum(row[f"{key}_ratio"] for key in
                   ("verbatim_log", "participant_quote", "researcher_paraphrase")) - 1.0) < 0.01


# --------------------------------------------------------------------------- #
# 부록 B — 삭제된 열이 돌아오지 않는다
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "removed",
    [
        "sequence_index",
        "branch_index",
        "normalization_applied",
        "matched_pattern_id",
        "referent_id",
        "first_opportunity",
        "carryover_sensitive",
        "response_latency",
    ],
)
async def test_removed_columns_are_gone(exported: AsyncSession, removed: str) -> None:
    """부록 B 삭제 목록 — 4-branch·normalization·presurvey 계보의 열."""
    result = await export_trajectory.collect(exported, actor="tester")
    for rows in result.as_files().values():
        for row in rows:
            assert removed not in row, f"{removed}가 export에 남아 있다"


async def test_no_aggregate_rating_column(exported: AsyncSession) -> None:
    """§0.4 · §7.1 — 합산 열은 만들지 않는다."""
    result = await export_trajectory.collect(exported, actor="tester")
    row = result.trajectory[0]
    for banned in ("rating_total", "rating_sum", "regrounding_score", "overall_preference"):
        assert banned not in row


async def test_latency_is_opt_in(exported: AsyncSession) -> None:
    """§2.11 — `response_latency`는 기본 미산출. `--latency`를 준 실행만 열을 만든다."""
    default = await export_trajectory.collect(exported, actor="tester")
    assert not any(key.startswith("latency_") for key in default.trajectory[0])

    with_latency = await export_trajectory.collect(exported, actor="tester", latency=True)
    assert any(key.startswith("latency_") for key in with_latency.trajectory[0])


# --------------------------------------------------------------------------- #
# 파일 쓰기
# --------------------------------------------------------------------------- #


async def test_write_csv_creates_files_even_when_empty(tmp_path: Path) -> None:
    """빈 표도 파일로 남긴다 — 파일이 없는 것과 데이터가 없는 것은 다르다."""
    target = tmp_path / "empty.csv"
    export_trajectory.write_csv(target, [])
    assert target.is_file()
    assert target.read_text(encoding="utf-8-sig").strip() == ""


async def test_write_csv_unions_columns_across_rows(tmp_path: Path) -> None:
    """열이 행마다 다른 표(`pairwise.csv`)를 온전히 쓴다.

    문항은 contrast마다 다르므로 pairwise 행끼리 열이 다르다. 첫 행 기준으로 열을 잡으면
    두 번째 contrast의 응답이 통째로 사라지거나 쓰기가 터진다 — 실제로 그렇게 터졌다.
    """
    import csv as csv_module

    target = tmp_path / "pairwise.csv"
    export_trajectory.write_csv(
        target,
        [
            {"contrast": "sequence", "item_seq_1": 4},
            {"contrast": "scope", "item_sco_1": 5, "item_sco_2": 6},
        ],
    )
    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv_module.DictReader(handle))
    assert set(rows[0]) == {"contrast", "item_seq_1", "item_sco_1", "item_sco_2"}
    assert rows[0]["item_seq_1"] == "4" and rows[0]["item_sco_1"] == ""
    assert rows[1]["item_sco_2"] == "6"


async def test_written_files_round_trip(exported: AsyncSession, tmp_path: Path) -> None:
    """§7.7 — 실제로 파일까지 쓴다. `collect()`만 보면 쓰기 단계의 결함을 놓친다."""
    import csv as csv_module

    result = await export_trajectory.collect(exported, actor="tester")
    for name, rows in result.as_files().items():
        export_trajectory.write_csv(tmp_path / name, rows)
        with (tmp_path / name).open(encoding="utf-8-sig", newline="") as handle:
            written = list(csv_module.DictReader(handle))
        assert len(written) == len(rows), f"{name}: {len(written)}행 vs {len(rows)}행"

    # pairwise는 세 contrast의 문항 열이 모두 살아 있어야 한다.
    with (tmp_path / export_trajectory.PAIRWISE_FILE).open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        header = next(csv_module.reader(handle))
    assert any(name.startswith("item_SEQ") for name in header)
    assert any(name.startswith("item_SCO") for name in header)
    assert any(name.startswith("item_STO") for name in header)
