"""§8.1 테이블이 실제로 쓸 수 있는 모양인지.

상태 전이 규칙은 `test_session_flow.py`, 생성 기록 규칙은 `test_ai2_pipeline.py`의 몫이다.
여기서는 **저장 자리**만 본다 — 16개 테이블에 각각 1행을 넣어 타입·FK·암호화 필드가
SQLite(DEV_MODE)와 Postgres 공통 정의로 성립하는지 확인한다.

동시에 **없어야 하는 것**을 고정한다: 합산 열, `acceptance` 계열 이름, researcher_only
테이블, 그리고 v1.0.1에서 삭제된 세 테이블(`branches`·`normalizations`·
`presurvey_responses`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base, tables
from app.security import fernet


async def test_full_row_roundtrip(session: AsyncSession) -> None:
    now = datetime.now(UTC)

    participant = tables.Participant(
        participant_no="P00",
        # §8.1 — 배정표 행을 복사한 값이다(D-30). `sequence_index`는 v2에 없다.
        focal_condition="C1",
        alt_order=["C2", "C3", "C4"],
        pair_order=["sequence", "scope", "stopping"],
        pair_sides={"sequence": ["C2", "C4"], "scope": ["C1", "C3"], "stopping": ["C3", "C4"]},
        assignment_version="assignment_dummy",
        a_level="A2",
        mismatch_locus="trajectory_timing",
        dossier_version="p00_qa_v2",
        is_test=True,
    )
    study_session = tables.Session(
        participant_no="P00",
        access_code_hash="0" * 64,
        code_expires_at=now,
        ss_state="SS04",
        f_state="F3",
        alt_index=None,
        pair_index=None,
        joined_at=now,
        consent_items={"recording": True, "alternative_exposure": True},
        consent_version="irb_v0",
        status="active",
        abort_reason=None,
    )
    session.add_all([participant, study_session])
    await session.flush()

    run = tables.FocalRun(
        session_id=study_session.id,
        condition="C1",
        stimulus_hash="a" * 64,
        started_at=now,
        checkpoint_edited=True,
        edited_segments=["trouble_cue"],
    )
    session.add(run)
    await session.flush()

    generation = tables.Generation(
        focal_run_id=run.id,
        attempt=1,
        output_text=fernet.encrypt("AI2 출력"),
        rule_violations=[],
        alt_overlap=[{"condition": "C3", "segment": "u"}],
        checker_result={"violations": [], "pass": True},
        checker_skipped=False,
        fallback_used=False,
        final=True,
    )
    session.add(generation)
    await session.flush()

    view = tables.PairwiseView(
        session_id=study_session.id,
        position=1,
        contrast="scope",
        left_condition="C1",
        right_condition="C3",
        focal_included=True,
        focal_side="left",
        rendered_at=now,
    )
    session.add(view)
    await session.flush()

    session.add_all(
        [
            tables.CheckpointEdit(
                session_id=study_session.id,
                segment="trouble_cue",
                original=fernet.encrypt("원래 표현"),
                edited=fernet.encrypt("고친 표현"),
                edited_at=now,
            ),
            tables.Turn(
                focal_run_id=run.id,
                role="user1",
                text=fernet.encrypt("장기 계획 말고 비교만"),
                submitted_at=now,
            ),
            tables.Turn(
                focal_run_id=run.id,
                role="ai2",
                text=fernet.encrypt("AI2 출력"),
                rendered_at=now,
                generation_id=generation.id,
            ),
            tables.Turn(
                focal_run_id=run.id,
                role="user2",
                text=fernet.encrypt("알겠어"),
                submitted_at=now,
            ),
            tables.SidecarEntry(
                focal_run_id=run.id,
                has_more=True,
                provenance="preexisting",
                free_text=fernet.encrypt("전달하지 않은 생각"),
                reason_text=fernet.encrypt("번거로워서"),
            ),
            tables.Rating(
                session_id=study_session.id,
                scope="mc",
                construct="manipulation_check",
                item_id="mc_recognition",
                value=6,
                display_order=8,
            ),
            tables.DownstreamAction(
                focal_run_id=run.id,
                disposition="end",
                end_type="stop_here",
                reason_text=fernet.encrypt("여기까지면 충분해서"),
                display_order=["stop_here", "new_chat", "switch_ai"],
                selected_at=now,
            ),
            tables.AltExposure(
                session_id=study_session.id,
                position=1,
                condition="C2",
                stimulus_hash="e" * 64,
                rendered_at=now,
                advanced_at=now,
            ),
            tables.PairwiseResponse(
                pairwise_view_id=view.id, item_id="sco_1", value=5, display_order=1
            ),
            tables.LlmCall(
                generation_id=generation.id,
                role="main",
                request_id=str(uuid.uuid4()),
                model_requested="anthropic/claude-opus-4.8",
                provider_reported_model="anthropic/claude-opus-4.8",
                prompt_hash="b" * 64,
                params={"temperature": 0.4},
                prompt_tokens=100,
                completion_tokens=50,
                cost=0.01,
                latency_ms=1200,
                status="ok",
            ),
            tables.Event(
                session_id=study_session.id,
                type="render_complete",
                payload={"screen": "P4"},
                client_ts=now,
            ),
            tables.AuditLog(actor="researcher-1", action="view", target="session:x"),
            tables.StudyVersion(
                spec_version="v2.0",
                prompt_hash="c" * 64,
                model_strings={"main": "anthropic/claude-opus-4.8"},
                assets_hash={"P00": "d" * 64},
                frozen_at=None,
            ),
        ]
    )
    await session.flush()

    # 암호화 필드는 평문으로 남지 않는다 (§2.9 · NT-28의 전제).
    stored = (await session.execute(select(tables.SidecarEntry))).scalars().one()
    assert stored.free_text is not None
    assert "전달하지 않은" not in stored.free_text.decode("latin-1")
    assert fernet.decrypt(stored.free_text) == "전달하지 않은 생각"

    edit = (await session.execute(select(tables.CheckpointEdit))).scalars().one()
    assert fernet.decrypt(edit.original) == "원래 표현"

    # AI3는 없다 — role에 그 값이 들어갈 자리가 없다(D-33).
    roles = {row.role for row in (await session.execute(select(tables.Turn))).scalars().all()}
    assert roles == {"user1", "ai2", "user2"}


async def test_focal_run_is_unique_per_session(session: AsyncSession) -> None:
    """§8.1 — `focal_runs.session_id`는 UNIQUE다(참가자당 1행 — D-23)."""
    assert tables.FocalRun.__table__.columns["session_id"].unique is True


async def test_alt_and_pairwise_positions_are_unique(session: AsyncSession) -> None:
    """§8.1 — UNIQUE(session_id, position). 같은 위치를 두 번 열 수 없다."""
    for table in (tables.AltExposure.__table__, tables.PairwiseView.__table__):
        constraints = [
            sorted(column.name for column in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]
        assert ["position", "session_id"] in constraints, table.name


async def test_ratings_have_no_total_score_column() -> None:
    """§0.4·§7.1 동결 — 합산하지 않는다. 합산을 담을 컬럼이 없다."""
    columns = set(tables.Rating.__table__.columns.keys())
    assert not {"total", "score", "sum", "regrounding_score"} & columns


async def test_pairwise_has_no_overall_index_column() -> None:
    """§0.3 · §7.5 — overall preference index를 산출하지 않는다."""
    columns = set(tables.PairwiseResponse.__table__.columns.keys())
    assert not {"overall", "index", "preference", "rank"} & columns


def test_no_acceptance_or_branch_named_columns() -> None:
    """§1.5 — `acceptance` 계열 금지(승계) + "branch"는 v2에서 쓰지 않는다(§1.5-5)."""
    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if "acceptance" in column.name.lower() or "branch" in column.name.lower()
    ]
    assert offenders == []


def test_deleted_tables_are_gone() -> None:
    """§8.1 — `branches`·`normalizations` 삭제(D-34 · D-23).

    `presurvey_responses`는 D-31로 삭제됐다가 **D-44로 복원**됐다 — 그래서 삭제 목록이
    아니라 아래 존재 검사 쪽에 있다.
    """
    names = set(Base.metadata.tables)
    assert not {"branches", "normalizations"} & names
    # 신설 5종은 있다.
    assert {
        "checkpoint_edits",
        "focal_runs",
        "alt_exposures",
        "pairwise_views",
        "pairwise_responses",
    } <= names


def test_presurvey_table_is_restored_without_an_aggregate_column() -> None:
    """§8.1 · D-44 — (item_id, value, display_order)뿐이다. **합산 열 없음**(§7.1)."""
    assert "presurvey_responses" in set(Base.metadata.tables)
    columns = set(tables.PresurveyResponse.__table__.columns.keys())
    assert {"session_id", "item_id", "value", "display_order"} <= columns
    for banned in ("total", "score", "sum", "reverse_scored"):
        assert banned not in columns, f"사전설문에 합산·파생 열: {banned}"


def test_turns_has_no_normalized_column() -> None:
    """D-34 — normalization 폐기. `text_normalized`가 없다."""
    assert "text_normalized" not in tables.Turn.__table__.columns


def test_researcher_only_layer_has_no_table() -> None:
    """§5.3·§8.1 — researcher_only는 DB에 존재하지 않는다(자산 파일 전용)."""
    assert not [name for name in Base.metadata.tables if "researcher" in name]
