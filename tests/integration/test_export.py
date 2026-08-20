"""분석 export (구현명세서 §7.6 · 부록 B · §2.9 — NT-30).

    NT-30 export 비식별 — 자유 텍스트 열 opt-in 분리, 태깅 플래그 열 존재

검사의 축은 **기본 실행이 무엇을 내보내지 않는가**다. "옵션을 켜면 텍스트가 나온다"는 쉬운
쪽이고, 지켜야 하는 건 "옵션을 켜지 않으면 어디에도 문장이 없다" 쪽이다. 그래서 참가자·
연구자가 쓴 문자열을 sentinel로 심고 기본 출력 전 파일을 통째로 훑는다.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from analysis import export_trajectory, tagging_flags
from app.models import tables
from tests import helpers
from tests.helpers import ADMIN_AUTH

USER1_TEXT = "참가자자유기술센티넬알파 장단점만 정리해줘"
SIDECAR_TEXT = "사이드카자유기술센티넬베타"
SIDECAR_REASON = "미전송사유센티넬감마"
FLAG_REASON = "연구자플래그사유센티넬델타"

ACTOR = "test-researcher"


async def _run_session(client: AsyncClient) -> str:
    """P00 한 세션: branch 1 reply(사이드카 있음) + 나머지 3 branch."""
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")

    await helpers.advance(client, "P4")
    await client.post("/api/branch/1/user1", json={"disposition": "reply", "text": USER1_TEXT})
    await client.post(
        "/api/branch/1/sidecar",
        json={
            "choice": "has",
            "free_text": SIDECAR_TEXT,
            "relevance": 5,
            "reason": SIDECAR_REASON,
        },
    )
    await client.post("/api/branch/1/ai2")
    await helpers.advance(client, "P7")
    await client.post("/api/branch/1/downstream", json={"code": "correct_reformulate"})
    await client.post("/api/branch/1/ratings", json=helpers.ratings_payload())

    await helpers.complete_branch(client, 2, "no_reply")
    await helpers.complete_branch(client, 3, "end")
    await helpers.complete_branch(client, 4, "reply")

    await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": FLAG_REASON},
        auth=ADMIN_AUTH,
    )
    return created["session_id"]


def _all_text(files: dict[str, list[dict[str, Any]]]) -> str:
    return "\n".join(
        str(value) for rows in files.values() for row in rows for value in row.values()
    )


async def test_nt30_default_export_carries_no_free_text(client: AsyncClient, session) -> None:
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)

    files = exported.as_files()
    assert export_trajectory.FREE_TEXT_FILE not in files, "기본 실행이 자유 텍스트 파일을 만들었다"
    blob = _all_text(files)
    for sentinel in (USER1_TEXT, SIDECAR_TEXT, SIDECAR_REASON, FLAG_REASON):
        assert sentinel not in blob, f"기본 export에 자유 텍스트가 있다: {sentinel[:12]}"


async def test_nt30_text_export_is_opt_in_and_lands_in_its_own_file(
    client: AsyncClient, session
) -> None:
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR, include_text=True)

    files = exported.as_files()
    assert export_trajectory.FREE_TEXT_FILE in files
    # 텍스트는 분리 파일에만 있다 — 다른 파일은 기본 실행과 같아야 한다.
    others = {name: rows for name, rows in files.items() if name != export_trajectory.FREE_TEXT_FILE}
    blob = _all_text(others)
    for sentinel in (USER1_TEXT, SIDECAR_TEXT, SIDECAR_REASON, FLAG_REASON):
        assert sentinel not in blob

    # branch마다 같은 필드명이 나오므로 (branch, field)로 읽는다.
    fields = {(row["branch_index"], row["field"]): row["text"] for row in exported.free_text}
    assert fields[(1, "user1_raw")] == USER1_TEXT
    assert fields[(1, "sidecar_text")] == SIDECAR_TEXT
    assert fields[(1, "sidecar_reason")] == SIDECAR_REASON
    assert fields[("", "researcher_flag.reason")] == FLAG_REASON
    assert fields[(1, "ai2_final_text")]


async def test_nt30_tagging_flag_columns_exist_on_every_row(
    client: AsyncClient, session
) -> None:
    """§7.6 — first-opportunity·carryover는 export가 **열로** 제공한다."""
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)

    assert len(exported.trajectory) == 4
    for row in exported.trajectory:
        assert set(tagging_flags.FLAG_COLUMNS) <= set(row)
    by_branch = {row["branch_index"]: row for row in exported.trajectory}
    assert by_branch[1]["first_opportunity"] is True
    assert by_branch[3]["first_opportunity"] is False
    # 코딩 입력이 없으면 carryover는 **빈 칸**이다 — False가 아니다(§7.2 부재≠정보 없음).
    assert by_branch[2]["carryover_sensitive"] == ""
    assert by_branch[2]["carryover_source"] == tagging_flags.UNCODED


async def test_carryover_flag_uses_the_coding_input(client: AsyncClient, session, tmp_path: Path) -> None:
    await _run_session(client)
    coding = tmp_path / "coding.csv"
    coding.write_text(
        "participant_no,branch_index,focal_content_expressed\n"
        "P00,1,true\nP00,2,false\nP00,3,false\nP00,4,false\n",
        encoding="utf-8",
    )
    exported = await export_trajectory.collect(session, actor=ACTOR, coding_path=coding)
    by_branch = {row["branch_index"]: row for row in exported.trajectory}
    assert by_branch[1]["carryover_sensitive"] is False  # 이전 branch가 없다
    assert by_branch[2]["carryover_sensitive"] is True  # branch 1에서 이미 표현됐다
    assert by_branch[4]["carryover_source"] == tagging_flags.CODED


async def test_trajectory_row_matches_the_data_dictionary(client: AsyncClient, session) -> None:
    """부록 B — 한 행이 한 participant × branch trajectory다."""
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)
    row = next(row for row in exported.trajectory if row["branch_index"] == 1)

    assert row["participant_no"] == "P00"
    assert row["condition"] == "C4"  # P00 → S4 (§3.3)
    assert row["user1_disposition"] == "reply"
    assert row["user1_chars"] == len(USER1_TEXT)
    assert row["sidecar_choice"] == "has" and row["sidecar_relevance"] == 5
    assert row["sidecar_text_chars"] == len(SIDECAR_TEXT)
    assert row["downstream_action"] == "correct_reformulate"
    assert row["ai2_present"] is True and row["fallback_used"] is False
    assert row["actionability"] in (0, 1, 2) and row["mismatch_locus"]
    # §7.3 12문항이 열로 있고 **합산 열은 없다**(§0.4).
    rating_columns = [key for key in row if key.startswith("rating_")]
    assert len(rating_columns) == 12
    assert not any(key in row for key in ("rating_total", "regrounding_score", "sum"))


async def test_no_reply_branch_has_no_ai2_or_downstream_columns_filled(
    client: AsyncClient, session
) -> None:
    """NT-17이 저장에서도 성립하는지 export 관점으로 본다."""
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)
    row = next(row for row in exported.trajectory if row["branch_index"] == 2)
    assert row["user1_disposition"] == "no_reply"
    assert row["ai2_present"] is False
    assert row["downstream_action"] == ""
    assert len([key for key in row if key.startswith("rating_")]) == 12


async def test_ratings_long_file_keeps_block_and_display_order(
    client: AsyncClient, session
) -> None:
    """§4.9·D-22 — 제시 순서와 블록이 분석에 남아야 한다(NT-18의 저장 층)."""
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)
    branch1 = [row for row in exported.ratings if row["branch_index"] == 1]
    assert len(branch1) == 12
    assert {row["block"] for row in branch1} == {1, 2}
    assert sorted(row["display_order"] for row in branch1) == list(range(1, 13))


async def test_integrity_file_reconstructs_the_generation_path(
    client: AsyncClient, session
) -> None:
    """§8.4·NT-15의 export판 — attempt·final·fallback·checker 판정이 함께 나간다."""
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)
    rows = [row for row in exported.integrity if row["branch_index"] == 1]
    assert rows and sum(1 for row in rows if row["final"]) == 1
    assert set(rows[0]) >= {
        "attempt",
        "final",
        "fallback_used",
        "checker_skipped",
        "rule_violations",
        "checker_result",
    }


async def test_events_file_supports_latency_without_computing_it(
    client: AsyncClient, session
) -> None:
    """§2.11·NT-29 — 파생 지표는 분석 시점 계산. export는 이벤트 쌍만 넘긴다."""
    await _run_session(client)
    exported = await export_trajectory.collect(session, actor=ACTOR)
    columns = set(exported.events[0])
    assert {"client_ts", "server_ts", "type"} <= columns
    assert not any("latency" in column for column in columns)
    # 브라우저 지문은 분석 파일로 나가지 않는다.
    assert "user_agent" not in _all_text({"events": exported.events})


async def test_export_records_audit_rows(client: AsyncClient, session) -> None:
    """§2.9 — export는 복호화 지점 ②다. 실행 1회당 export·decrypt 각 1행."""
    await _run_session(client)
    await export_trajectory.collect(session, actor=ACTOR)
    logs = list((await session.execute(select(tables.AuditLog))).scalars().all())
    actions = [log.action for log in logs if log.actor == ACTOR]
    assert actions.count("export") == 1
    assert actions.count("decrypt") == 1


async def test_write_csv_emits_headers_even_for_empty_tables(tmp_path: Path) -> None:
    """빈 표도 파일로 남긴다 — 파일이 없는 것과 데이터가 없는 것은 다르다."""
    path = tmp_path / "empty.csv"
    export_trajectory.write_csv(path, [])
    assert path.is_file() and path.read_text(encoding="utf-8-sig").strip() == ""

    export_trajectory.write_csv(path, [{"a": 1, "b": "x"}])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "1", "b": "x"}]
