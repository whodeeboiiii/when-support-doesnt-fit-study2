"""연구자 콘솔 R1–R4 (구현명세서 §4.12 · §2.7 · §9.1 — NT-26).

    NT-26 flag non-blocking(상태 불변)·abort만 SS90, 전 콘솔 행위 audit

이 파일이 지키는 경계 셋.

1. **flag는 기록이고 abort는 전이다**(D-07). 둘을 한 버튼으로 합치고 싶어지는 순간 세션
   운영이 판정 장치가 된다 — flag 뒤에 상태가 그대로인지를 매번 확인한다.
2. **콘솔은 인증 뒤에 있다**(§2.7). 자격 없는 요청이 뷰 하나라도 통과하면 researcher_only가
   열린다.
3. **조회도 audit이다**(§2.7 "모든 콘솔 조회"). 복호화 뷰는 `decrypt` 행까지 남는다(§2.9).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.assets import screen_copy
from app.core.state_machine import SsState
from app.models import tables
from tests import helpers
from tests.helpers import ADMIN_AUTH

CONSOLE_ENDPOINTS = (
    "/admin/participants",
    "/admin/costs",
    "/admin/console",
)


async def _audit(session, action: str | None = None) -> list[tables.AuditLog]:
    query = select(tables.AuditLog)
    if action is not None:
        query = query.where(tables.AuditLog.action == action)
    return list((await session.execute(query)).scalars().all())


async def _events(session, session_id: uuid.UUID) -> list[tables.Event]:
    result = await session.execute(
        select(tables.Event).where(tables.Event.session_id == session_id)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------- #
# 인증 (§2.7)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", CONSOLE_ENDPOINTS)
async def test_console_requires_basic_auth(client: AsyncClient, path: str) -> None:
    assert (await client.get(path)).status_code == 401


async def test_console_page_is_served_behind_auth(client: AsyncClient) -> None:
    response = await client.get("/admin/console", auth=ADMIN_AUTH)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # 콘솔은 참가자 번들과 별도 파일이다 — 데이터는 전부 /admin/* JSON에서 온다.
    assert "/admin/monitor/" in response.text


# --------------------------------------------------------------------------- #
# R1 세션 관리 (§4.12)
# --------------------------------------------------------------------------- #


async def test_r1_lists_participants_with_sequence_and_dossier_lock(
    client: AsyncClient, session
) -> None:
    body = (await client.get("/admin/participants", auth=ADMIN_AUTH)).json()
    rows = {row["participant_no"]: row for row in body["participants"]}
    assert set(rows) >= {f"P{n:02d}" for n in range(0, 13)}
    # §3.3 표 — P01은 S1(C1 C2 C4 C3).
    assert rows["P01"]["sequence"] == ["C1", "C2", "C4", "C3"]
    assert rows["P01"]["sequence_index"] == 1
    assert set(rows["P00"]["dossier"]) == {"version", "locked", "locked_at", "hash", "dummy"}
    assert [log.target for log in await _audit(session, "view")] == ["console:R1"]


async def test_r1_shows_created_sessions(client: AsyncClient) -> None:
    created = await helpers.create_session(client, "P00")
    body = (await client.get("/admin/participants", auth=ADMIN_AUTH)).json()
    p00 = next(row for row in body["participants"] if row["participant_no"] == "P00")
    assert created["session_id"] in [row["session_id"] for row in p00["sessions"]]
    assert p00["sessions"][0]["ss_state"] == SsState.CREATED.value


async def test_costs_sums_llm_calls(client: AsyncClient) -> None:
    """§2.8 — 대시보드 없이 R1에 합산만 띄운다."""
    await helpers.reach_branch_block(client, "P00")
    await helpers.complete_branch(client, 1, "reply")
    body = (await client.get("/admin/costs", auth=ADMIN_AUTH)).json()
    roles = {row["role"]: row for row in body["by_role"]}
    assert roles["main"]["calls"] >= 1
    assert body["total_calls"] == sum(row["calls"] for row in body["by_role"])


# --------------------------------------------------------------------------- #
# NT-26 flag — non-blocking
# --------------------------------------------------------------------------- #


async def test_nt26_flag_does_not_change_session_state(client: AsyncClient, session) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    before = await helpers.state(client)

    response = await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": "참가자가 checkpoint 사실 오류를 구두로 언급"},
        auth=ADMIN_AUTH,
    )
    assert response.status_code == 200

    after = await helpers.state(client)
    assert (after["ss_state"], after["screen"], after["status"]) == (
        before["ss_state"],
        before["screen"],
        before["status"],
    )
    assert response.json()["ss_state"] == before["ss_state"]


async def test_nt26_flag_reason_is_encrypted_and_audited(client: AsyncClient, session) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    reason = "위험 징후 없음 — 카메라 각도만 조정"
    await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": reason},
        auth=ADMIN_AUTH,
    )
    events = [
        event
        for event in await _events(session, uuid.UUID(created["session_id"]))
        if event.type == "researcher_flag"
    ]
    assert len(events) == 1
    payload = events[0].payload or {}
    assert reason not in str(payload), "flag 사유가 평문으로 저장됐다 (§2.9)"
    assert payload["reason_encrypted"]
    assert [log.target for log in await _audit(session, "flag")] == [
        f"session:{created['session_id']}"
    ]


async def test_flag_requires_a_reason(client: AsyncClient) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    response = await client.post(
        f"/admin/sessions/{created['session_id']}/flag", json={"reason": ""}, auth=ADMIN_AUTH
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# NT-26 abort — SS90 · §9.1
# --------------------------------------------------------------------------- #


async def test_nt26_abort_moves_to_ss90_and_participant_sees_the_notice(
    client: AsyncClient, session, monkeypatch: pytest.MonkeyPatch
) -> None:
    notifications = helpers.capture_notifications(monkeypatch)
    created, _ = await helpers.open_and_join(client, "P00")

    response = await client.post(
        f"/admin/sessions/{created['session_id']}/abort",
        json={"reason": "위험 징후 — 안전 절차 수행"},
        auth=ADMIN_AUTH,
    )
    assert response.status_code == 200
    assert response.json() == {"ss_state": SsState.RESEARCHER_ABORT.value, "status": "abort"}

    # §9.1 — 참가자 화면은 dead-end가 아니라 중단 안내로 수렴한다([정본 아님 — §4 제안]).
    state = await helpers.state(client)
    assert state["screen"] == "ABORTED"
    assert state["data"]["message"] == screen_copy.SESSION_ABORTED

    # §2.8 트리거 4.
    assert [event for event, _fields in notifications] == ["researcher_abort"]
    assert [log.target for log in await _audit(session, "abort")] == [
        f"session:{created['session_id']}"
    ]


async def test_abort_reason_is_encrypted_at_rest(client: AsyncClient, session) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    reason = "참가자 요청으로 중단"
    await client.post(
        f"/admin/sessions/{created['session_id']}/abort",
        json={"reason": reason},
        auth=ADMIN_AUTH,
    )
    row = await session.get(tables.Session, uuid.UUID(created["session_id"]))
    assert row.abort_reason is not None
    assert reason.encode("utf-8") not in row.abort_reason


async def test_aborted_session_stops_accepting_submissions(client: AsyncClient) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    await client.post(
        f"/admin/sessions/{created['session_id']}/abort",
        json={"reason": "중단"},
        auth=ADMIN_AUTH,
    )
    response = await client.post("/api/consent", json={"items": {}})
    assert response.status_code == 409


async def test_abort_is_refused_after_the_session_is_done(client: AsyncClient) -> None:
    created = await helpers.create_session(client, "P00")
    await helpers.join(client, "P00", created["access_code"])
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    for index in range(1, 5):
        await helpers.complete_branch(client, index, "no_reply")
    await helpers.advance(client, "P10")
    await client.post("/api/debrief/confirm")

    response = await client.post(
        f"/admin/sessions/{created['session_id']}/abort",
        json={"reason": "늦은 중단"},
        auth=ADMIN_AUTH,
    )
    assert response.status_code == 409


async def test_dropout_moves_to_ss91_without_notify(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.1 — 복구 불능 이탈은 연구자가 SS91로 처리한다. §2.8 표에 트리거가 없다."""
    notifications = helpers.capture_notifications(monkeypatch)
    created, _ = await helpers.open_and_join(client, "P00")
    response = await client.post(
        f"/admin/sessions/{created['session_id']}/dropout", auth=ADMIN_AUTH
    )
    assert response.json() == {"ss_state": SsState.DROPOUT.value, "status": "dropout"}
    assert notifications == []


# --------------------------------------------------------------------------- #
# R2 모니터 (§4.12)
# --------------------------------------------------------------------------- #


async def _monitor(client: AsyncClient, session_id: str) -> dict[str, Any]:
    response = await client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)
    assert response.status_code == 200, response.text
    return response.json()


async def test_r2_monitor_shows_state_transcript_and_pipeline_state(
    client: AsyncClient, session
) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    await helpers.complete_branch(client, 1, "reply")

    body = await _monitor(client, created["session_id"])
    assert body["session"]["ss_state"] == SsState.BRANCH_BLOCK.value
    assert body["session"]["screen"] == "P4"

    first = body["branches"][0]
    assert first["condition"] == "C4"  # P00 → S4의 branch 1 (§3.3)
    assert first["disposition"] == "reply"
    assert first["ai2_state"] == "clean"

    roles = [(turn["branch_index"], turn["role"]) for turn in body["transcript"]]
    assert roles == [(1, "ai1"), (1, "user1"), (1, "ai2")]
    assert all(turn["text"] for turn in body["transcript"]), "복호화된 transcript가 비어 있다"

    # §2.7·§2.9 — 조회 1회 = view + decrypt.
    assert f"session:{created['session_id']}" in [log.target for log in await _audit(session, "view")]
    assert [log.target for log in await _audit(session, "decrypt")] == [
        f"session:{created['session_id']}:transcript"
    ]


async def test_r2_monitor_reports_fallback_as_pipeline_state(client: AsyncClient, llm) -> None:
    """§4.12 — 생성 중/재생성/fallback 표시. fallback은 눈에 띄어야 한다(§2.8 알림과 같은 사건)."""
    from app.llm.fake_llm import FIXTURE_TOKEN

    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    await helpers.advance(client, "P4")
    await client.post(
        "/api/branch/1/user1",
        json={
            "disposition": "reply",
            # 두 시도 모두 규칙 위반 → §6.6 neutral_fallback.
            "text": f"장단점만 정리해줘 {FIXTURE_TOKEN.format(name='too_long')}",
        },
    )
    await client.post("/api/branch/1/sidecar", json={"choice": "none"})
    await client.post("/api/branch/1/ai2")

    body = await _monitor(client, created["session_id"])
    assert body["branches"][0]["ai2_state"] == "fallback"
    assert body["branches"][0]["attempts"] >= 2


async def test_r2_monitor_shows_flag_reason_in_the_event_stream(client: AsyncClient) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    reason = "참가자가 잠시 자리를 비움"
    await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": reason},
        auth=ADMIN_AUTH,
    )
    body = await _monitor(client, created["session_id"])
    flags = [event for event in body["events"] if event["type"] == "researcher_flag"]
    assert flags and flags[0]["payload"]["reason"] == reason
    assert "reason_encrypted" not in flags[0]["payload"]


async def test_monitor_404s_on_unknown_session(client: AsyncClient) -> None:
    response = await client.get(f"/admin/monitor/{uuid.uuid4()}", auth=ADMIN_AUTH)
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# R3 review (§4.12)
# --------------------------------------------------------------------------- #


async def test_r3_review_shows_four_columns_with_sidecar_ratings_and_private_layer(
    client: AsyncClient, session
) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    await helpers.advance(client, "P4")
    await client.post(
        "/api/branch/1/user1", json={"disposition": "reply", "text": "장단점만 정리해줘"}
    )
    await client.post(
        "/api/branch/1/sidecar",
        json={"choice": "has", "free_text": "사실 이직은 이미 정했다", "relevance": 6},
    )
    await client.post("/api/branch/1/ai2")
    await helpers.advance(client, "P7")
    await client.post("/api/branch/1/downstream", json={"code": "pause"})
    await client.post("/api/branch/1/ratings", json=helpers.ratings_payload())
    for index in range(2, 5):
        await helpers.complete_branch(client, index, "no_reply")

    body = (await client.get(f"/admin/review/{created['session_id']}", auth=ADMIN_AUTH)).json()
    assert [row["index"] for row in body["branches"]] == [1, 2, 3, 4]

    first = body["branches"][0]
    assert first["ai1"] and first["user1"] == "장단점만 정리해줘"
    assert first["ai2"] and first["downstream_code"] == "pause"
    # P10과 다른 점 ①: sidecar가 보인다(§4.12 — 참가자 화면은 PH-02로 비표시).
    assert first["sidecar"]["free_text"] == "사실 이직은 이미 정했다"
    assert len(first["ratings"]) == 12
    # 다른 점 ②: 조건 라벨이 붙는다.
    assert first["condition"] == "C4"
    # §4.12 — researcher_only 요약(인터뷰 참조용).
    assert body["researcher_only"]["retrospective_stance"]

    assert [log.target for log in await _audit(session, "decrypt")] == [
        f"session:{created['session_id']}:review"
    ]


async def test_r3_review_lists_flags_with_reasons(client: AsyncClient) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": "checkpoint 사실 오류 언급 — 자산 미반영(D-08)"},
        auth=ADMIN_AUTH,
    )
    body = (await client.get(f"/admin/review/{created['session_id']}", auth=ADMIN_AUTH)).json()
    assert body["flags"][0]["payload"]["reason"].startswith("checkpoint 사실 오류")


# --------------------------------------------------------------------------- #
# R4 dossier 뷰어 (§4.12 · §5.2)
# --------------------------------------------------------------------------- #


async def test_r4_dossier_viewer_shows_three_layers_stimuli_and_lock(
    client: AsyncClient, session
) -> None:
    body = (await client.get("/admin/dossier/P00", auth=ADMIN_AUTH)).json()
    assert [row["condition"] for row in body["stimuli"]] == ["C1", "C2", "C3", "C4"]
    assert all(row["text"] and row["hash"] for row in body["stimuli"])
    # §5.3 질문 수 계약이 화면에서도 보인다(NT-22).
    questions = {row["condition"]: row["meta"]["questions"] for row in body["stimuli"]}
    assert questions == {"C1": 0, "C2": 1, "C3": 0, "C4": 1}

    assert body["ai_visible"]["situation_summary"]
    assert body["derivation"]["neutral_fallback"]
    assert body["derivation"]["referent_map"]
    assert body["researcher_only"]["retrospective_stance"]
    assert body["content_hash"] and "locked" in body
    assert [log.target for log in await _audit(session, "view")] == ["dossier:P00"]


async def test_r4_rejects_unknown_participant(client: AsyncClient) -> None:
    assert (await client.get("/admin/dossier/P99", auth=ADMIN_AUTH)).status_code == 404


async def test_nt26_every_console_action_leaves_an_audit_row(
    client: AsyncClient, session
) -> None:
    """§2.7 — "모든 콘솔 조회·flag·abort·dossier 열람"이 audit에 남는다.

    엔드포인트를 하나씩 부르며 audit 행이 **매번 늘었는지** 본다. 목록을 눈으로 관리하는
    대신 호출로 확인해야 새 엔드포인트가 조용히 감사 밖에 서는 일이 없다.
    """
    created, _ = await helpers.open_and_join(client, "P00")
    session_id = created["session_id"]

    calls = [
        ("R1 목록", client.get("/admin/participants", auth=ADMIN_AUTH)),
        ("비용", client.get("/admin/costs", auth=ADMIN_AUTH)),
        ("콘솔 페이지", client.get("/admin/console", auth=ADMIN_AUTH)),
        ("모니터", client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)),
        ("review", client.get(f"/admin/review/{session_id}", auth=ADMIN_AUTH)),
        ("dossier", client.get("/admin/dossier/P00", auth=ADMIN_AUTH)),
        ("코드 재발급", client.post(f"/admin/sessions/{session_id}/code", auth=ADMIN_AUTH)),
        (
            "flag",
            client.post(
                f"/admin/sessions/{session_id}/flag", json={"reason": "감사 확인"}, auth=ADMIN_AUTH
            ),
        ),
        (
            "abort",
            client.post(
                f"/admin/sessions/{session_id}/abort", json={"reason": "감사 확인"}, auth=ADMIN_AUTH
            ),
        ),
    ]
    previous = len(await _audit(session))
    for label, awaitable in calls:
        response = await awaitable
        assert response.status_code == 200, f"{label}: {response.text}"
        current = len(await _audit(session))
        assert current > previous, f"{label}: audit 기록 없음 (§2.7)"
        previous = current


async def test_console_has_no_write_path_into_dossier_assets(client: AsyncClient) -> None:
    """§5.2 — 자산 수정은 파일·2인 판정·lock 절차를 지난다. 콘솔에는 쓰기 경로가 없다."""
    from app.main import create_app

    routes = helpers.route_table(create_app())
    dossier_routes = [row for row in routes if row[0].startswith("/admin/dossier")]
    assert dossier_routes == [("/admin/dossier/{participant_no}", ("GET",))]


async def test_admin_surface_matches_the_spec_api_table() -> None:
    """§8.2 연구자 API 표 — 표에 없는 쓰기 경로가 생기면 여기서 걸린다."""
    from app.main import create_app

    admin_routes = {
        (path, methods)
        for path, methods in helpers.route_table(create_app())
        if path.startswith("/admin")
    }
    assert admin_routes == {
        ("/admin/sessions", ("POST",)),
        ("/admin/sessions/{session_id}/code", ("POST",)),
        ("/admin/sessions/{session_id}/flag", ("POST",)),
        ("/admin/sessions/{session_id}/abort", ("POST",)),
        ("/admin/sessions/{session_id}/dropout", ("POST",)),
        ("/admin/monitor/{session_id}", ("GET",)),
        ("/admin/review/{session_id}", ("GET",)),
        ("/admin/dossier/{participant_no}", ("GET",)),
        ("/admin/costs", ("GET",)),
        # §4.12 R1 화면용 목록과 콘솔 페이지 — §8.2 표에는 없다(PROGRESS 확인 필요).
        ("/admin/participants", ("GET",)),
        ("/admin/console", ("GET",)),
    }
