"""§8.1 테이블이 실제로 쓸 수 있는 모양인지 (NS1 스캐폴드 확인).

상태 전이 규칙은 NS2, 생성 기록 규칙은 NS3의 몫이다. 여기서는 **저장 자리**만 본다 —
14개 테이블에 각각 1행을 넣어 타입·FK·암호화 필드가 SQLite(DEV_MODE)와 Postgres 공통 정의로
성립하는지 확인한다. 여기서 막히면 NS2가 첫날부터 스키마를 고치게 된다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import tables
from app.security import fernet


async def test_full_row_roundtrip(session: AsyncSession) -> None:
    now = datetime.now(UTC)

    participant = tables.Participant(
        participant_no="P00", sequence_index=4, dossier_version="p00_qa_v1", is_test=True
    )
    study_session = tables.Session(
        participant_no="P00",
        access_code_hash="0" * 64,
        code_expires_at=now,
        ss_state="SS04",
        branch_index=1,
        joined_at=now,
        consent_items={"recording": True, "overseas_transfer": True},
        consent_version="irb_v0",
        status="active",
        abort_reason=None,
    )
    session.add_all([participant, study_session])
    await session.flush()

    branch = tables.Branch(
        session_id=study_session.id,
        branch_index=1,
        condition="C1",
        stimulus_hash="a" * 64,
        started_at=now,
        b_state="B4",
        user1_disposition="reply",
    )
    session.add(branch)
    await session.flush()

    generation = tables.Generation(
        branch_id=branch.id,
        attempt=1,
        output_text=fernet.encrypt("AI2 출력"),
        rule_violations=[],
        checker_result={"violations": [], "pass": True},
        checker_skipped=False,
        fallback_used=False,
        final=True,
    )
    session.add(generation)
    await session.flush()

    session.add_all(
        [
            tables.Turn(
                branch_id=branch.id,
                role="user1",
                text=fernet.encrypt("장기 계획 말고 장단점만"),
                text_normalized=fernet.encrypt("장기 계획 말고 장단점만"),
                submitted_at=now,
            ),
            tables.Turn(
                branch_id=branch.id,
                role="ai2",
                text=fernet.encrypt("AI2 출력"),
                rendered_at=now,
                generation_id=generation.id,
            ),
            tables.Normalization(
                branch_id=branch.id, applied=True, matched_pattern_id="NP-01", referent_id="r1"
            ),
            tables.SidecarEntry(
                branch_id=branch.id,
                choice="has",
                free_text=fernet.encrypt("전달하지 않은 생각"),
                relevance_1_7=5,
                reason_text=fernet.encrypt("번거로워서"),
            ),
            tables.Rating(
                branch_id=branch.id, item_id="recognition", value=6, block=1, display_order=2
            ),
            tables.DownstreamAction(
                branch_id=branch.id,
                code="continue_reply",
                display_order=["pause", "continue_reply", "end"],
                selected_at=now,
            ),
            tables.PresurveyResponse(
                session_id=study_session.id, item_id="ai_use_freq", value="weekly", display_order=1
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
                branch_id=branch.id,
                type="render_complete",
                payload={"screen": "P5"},
                client_ts=now,
            ),
            tables.AuditLog(actor="researcher-1", action="view", target="session:x"),
            tables.StudyVersion(
                spec_version="v1.0.1",
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

    assert len((await session.execute(select(tables.Turn))).scalars().all()) == 2


async def test_ratings_have_no_total_score_column() -> None:
    """§0.4·§7.3 동결 — 12문항을 단일 점수로 합산하지 않는다. 합산을 담을 컬럼이 없다."""
    columns = set(tables.Rating.__table__.columns.keys())
    assert not {"total", "score", "sum", "regrounding_score"} & columns


def test_no_acceptance_named_columns() -> None:
    """§1.5-10 — `acceptance` 계열 변수명 금지. 스키마에도 적용한다."""
    from app.models import Base

    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if "acceptance" in column.name.lower()
    ]
    assert offenders == []


def test_researcher_only_layer_has_no_table() -> None:
    """§5.2·§8.1 — researcher_only는 DB에 존재하지 않는다(자산 파일 전용)."""
    from app.models import Base

    assert not [name for name in Base.metadata.tables if "researcher" in name]
