"""DEV_MODE 개발용 초기화 API (`app/api/dev.py`).

명세서의 연구 API가 아니라 시연 도구이므로 NT 번호를 붙이지 않는다. 대신 **도구가 연구
규율을 우회하지 않는다**는 것을 여기서 고정한다.

- 배포 구성에서는 경로가 **존재하지 않는다**(권한 거부가 아니라 미등록).
- 초기화는 참가자 산출물만 지운다 — `audit_logs`는 남는다(§2.7).
- 자동 접속이 없다 — 초기화 후에도 P0(§4.0)부터 정상 경로다.
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import tables
from tests import helpers


async def _count(db: AsyncSession, model) -> int:  # noqa: ANN001
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


def test_dev_routes_are_absent_outside_dev_mode() -> None:
    """배포 구성(DEV_MODE=false)에서는 `/api/dev/*`가 라우트 표에 없다."""
    from app.core.config import get_settings
    from app.main import create_app

    os.environ["DEV_MODE"] = "false"
    get_settings.cache_clear()
    try:
        paths = [path for path, _ in helpers.route_table(create_app())]
        assert not [path for path in paths if path.startswith("/api/dev")]
    finally:
        os.environ["DEV_MODE"] = "true"
        get_settings.cache_clear()

    # DEV_MODE로 돌아오면 다시 열린다 — 조건은 설정 하나뿐이다.
    paths = [path for path, _ in helpers.route_table(create_app())]
    assert "/api/dev/reset" in paths


async def test_status_reports_current_sessions(client: AsyncClient) -> None:
    await helpers.reach_branch_block(client, "P00")
    response = await client.get("/api/dev/status")
    assert response.status_code == 200
    body = response.json()
    assert body["dev_mode"] is True
    assert body["default_participant"] == "P00"
    assert [row["ss_state"] for row in body["sessions"]] == ["SS04"]


async def test_reset_wipes_progress_and_issues_a_new_code(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.complete_branch(client, 1, "reply")
    assert await _count(session, tables.Rating) > 0

    response = await client.post("/api/dev/reset", json={"participant_no": "P00"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["access_code"]) == 6

    for model in (
        tables.Branch,
        tables.Turn,
        tables.Rating,
        tables.SidecarEntry,
        tables.Generation,
        tables.LlmCall,
        tables.DownstreamAction,
        tables.PresurveyResponse,
        tables.Event,
    ):
        assert await _count(session, model) == 0, f"{model.__tablename__}가 남았다"
    # 세션은 지우고 **새로 하나** 만든다(코드 발급 대상이 필요하다).
    assert await _count(session, tables.Session) == 1
    fresh = (await session.execute(select(tables.Session))).scalars().one()
    assert fresh.ss_state == "SS00"

    # 초기화 전 쿠키로는 아무것도 할 수 없다.
    assert (await client.get("/api/state")).status_code == 401

    state = await helpers.join(client, "P00", body["access_code"])
    assert state["screen"] == "P1" and state["ss_state"] == "SS01"
    assert state["restored"] is False


async def test_reset_does_not_auto_join(client: AsyncClient) -> None:
    """초기화는 로그인 뒷문이 아니다 — 접속은 P0에서 사람이 한다."""
    await helpers.open_and_join(client, "P00")
    await client.post("/api/dev/reset", json={"participant_no": "P00"})
    assert (await client.get("/api/state")).status_code == 401


async def test_reset_keeps_the_audit_trail(client: AsyncClient, session: AsyncSession) -> None:
    """§2.7 — 접근 이력은 초기화 대상이 아니다. 지울 수 있으면 증거가 아니다."""
    await helpers.open_and_join(client, "P00")
    before = await _count(session, tables.AuditLog)
    await client.post("/api/dev/reset", json={"participant_no": "P00"})
    after = await _count(session, tables.AuditLog)
    assert after == before + 1, "개발용 발급도 code_issue로 남는다"

    rows = (await session.execute(select(tables.AuditLog))).scalars().all()
    dev_rows = [row for row in rows if row.actor == "dev_mode"]
    assert [row.action for row in dev_rows] == ["code_issue"]


async def test_reset_only_touches_the_named_participant(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.create_session(client, "P01")

    await client.post("/api/dev/reset", json={"participant_no": "P01"})

    remaining = (await session.execute(select(tables.Session))).scalars().all()
    assert sorted(row.participant_no for row in remaining) == ["P00", "P01"]
    # P00의 진행은 그대로다.
    p00 = next(row for row in remaining if row.participant_no == "P00")
    assert p00.ss_state == "SS04"
    assert await _count(session, tables.PresurveyResponse) > 0


@pytest.mark.parametrize("participant_no", ["P99", "XX", ""])
async def test_reset_refuses_unknown_participant(
    client: AsyncClient, participant_no: str
) -> None:
    response = await client.post("/api/dev/reset", json={"participant_no": participant_no})
    assert response.status_code == 400
