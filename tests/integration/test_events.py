"""beacon·이벤트 (구현명세서 §2.11 · §7.5 · §4.6 — NT-29의 전제).

NT-29는 "렌더 beacon → 제출 latency 필드 **산출 가능성**(이벤트 쌍 존재)"을 요구한다. 값을
계산하라는 요구가 아니다 — §7.5가 파생 지표의 런타임 계산을 금지하므로, 시스템이 보장할 것은
**쌍이 남는가**뿐이다.

동시에 이 통로가 무엇을 받지 않는지도 고정한다: keystroke·삭제 텍스트·수정 이력은 수집
금지다(§4.6). 그래서 이벤트 payload는 계량이고 텍스트가 아니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import tables
from tests import helpers


async def test_nt29_render_and_submit_pair_is_recorded(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")

    rendered_at = datetime.now(UTC).isoformat()
    response = await client.post(
        "/api/events",
        json={
            "type": "render_complete",
            "branch_index": 1,
            "client_ts": rendered_at,
            "payload": {"screen": "P5"},
        },
    )
    assert response.status_code == 202

    await client.post(
        "/api/events",
        json={
            "type": "submit",
            "branch_index": 1,
            "client_ts": datetime.now(UTC).isoformat(),
            "payload": {"screen": "P5", "disposition": "reply"},
        },
    )
    await client.post("/api/branch/1/user1", json={"disposition": "reply", "text": "장단점만"})

    rows = (
        await session.execute(
            select(tables.Event).where(tables.Event.branch_id.is_not(None))
        )
    ).scalars().all()
    types = [row.type for row in rows]
    assert "render_complete" in types and "submit" in types
    # 쌍의 양쪽에 client_ts와 server_ts가 모두 있어야 latency 산출이 가능하다(§2.11).
    for row in rows:
        assert row.client_ts is not None
        assert row.server_ts is not None


async def test_render_beacon_opens_b1_to_b2(client: AsyncClient) -> None:
    """§3.2 — 렌더 완료 beacon이 B1 → B2를 연다."""
    await helpers.reach_branch_block(client, "P00")
    state = await helpers.advance(client, "P4")
    assert state["b_state"] == "B1"
    await client.post("/api/events", json={"type": "render_complete", "branch_index": 1})
    assert (await helpers.state(client))["b_state"] == "B2"


async def test_lost_beacon_does_not_block_submission(client: AsyncClient) -> None:
    """§2.11 — 시간 지표가 연구 상태의 게이트가 되지 않는다."""
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")  # B1에 머문 채(beacon 없음)
    response = await client.post("/api/branch/1/user1", json={"disposition": "end"})
    assert response.status_code == 200
    assert response.json()["screen"] == "P6"


async def test_unknown_event_types_are_refused(client: AsyncClient) -> None:
    """열린 쓰기 통로를 만들지 않는다 — 유형 목록은 §2.11로 고정이다."""
    await helpers.open_and_join(client, "P00")
    assert (
        await client.post("/api/events", json={"type": "keystroke"})
    ).status_code == 400
    assert (
        await client.post("/api/events", json={"type": "text_change"})
    ).status_code == 400


async def test_event_payload_is_a_measurement_not_a_transcript(client: AsyncClient) -> None:
    """§4.6 — 자유 텍스트를 이벤트로 흘려보내는 경로를 막는다."""
    await helpers.open_and_join(client, "P00")
    oversized = {"type": "focus", "payload": {"draft": "가" * 200}}
    assert (await client.post("/api/events", json=oversized)).status_code == 400
    too_many = {"type": "focus", "payload": {str(i): i for i in range(9)}}
    assert (await client.post("/api/events", json=too_many)).status_code == 400


async def test_events_require_a_session(client: AsyncClient) -> None:
    client.cookies.clear()
    assert (await client.post("/api/events", json={"type": "focus"})).status_code == 401
