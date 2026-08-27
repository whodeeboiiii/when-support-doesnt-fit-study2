"""연구자 콘솔 R1–R4 (구현명세서 §4.13 · §2.7 · §9.1 — NT-26 · NT-39).

    NT-26 flag non-blocking(상태 불변)·abort만 SS90, 전 콘솔 행위 audit

이 파일이 지키는 경계 셋.

1. **flag는 기록이고 abort는 전이다**(D-07). 둘을 한 버튼으로 합치고 싶어지는 순간 세션
   운영이 판정 장치가 된다 — flag 뒤에 상태가 그대로인지를 매번 확인한다.
2. **콘솔은 인증 뒤에 있다**(§2.7). 자격 없는 요청이 뷰 하나라도 통과하면 researcher_only가
   열린다.
3. **조회도 audit이다**(§2.7 "모든 콘솔 조회"). 복호화 뷰는 `decrypt` 행까지 남는다(§2.9).
4. **연구자만 보는 것이 실제로 연구자에게만 간다**(NT-39). R3에는 조건 라벨·sidecar·
   researcher_only가 있고, 참가자 P11에는 **없다**.
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


async def test_r1_lists_participants_with_assignment_and_dossier_lock(
    client: AsyncClient, session
) -> None:
    """§4.13 R1 — 배정표 행(focal·대안 순서·pair 순서·좌우·A-level) + dossier lock."""
    from app.core import assignment

    table = assignment.load()
    body = (await client.get("/admin/participants", auth=ADMIN_AUTH)).json()
    rows = {row["participant_no"]: row for row in body["participants"]}
    assert set(rows) >= set(table.participant_numbers) | {"P00"}

    sample = rows[table.participant_numbers[0]]
    entry = sample["assignment"]
    assert entry["focal_condition"] in {"C1", "C2", "C3", "C4"}
    assert entry["focal_condition"] not in entry["alt_order"]
    assert sorted(entry["pair_order"]) == ["scope", "sequence", "stopping"]
    assert set(entry["pair_sides"]) == {"sequence", "scope", "stopping"}
    assert entry["a_level"] in {"A0", "A1", "A2"}

    # NT-42 — dummy 상태를 감추지 않는다.
    assert body["assignment"]["is_dummy"] is True
    assert body["assignment"]["n"] == 24
    assert rows["P00"]["dossier"]["dummy"] is False

    assert [log.target for log in await _audit(session, "view")] == ["console:R1"]


async def test_r1_assignment_view_is_read_only(client: AsyncClient) -> None:
    """§8.2 · §1.4 — 배정표는 읽기만. 쓰기 경로가 없다(D-30)."""
    body = (await client.get("/admin/assignment", auth=ADMIN_AUTH)).json()
    assert len(body["rows"]) == 24
    assert body["is_dummy"] is True
    assert "strata" in body

    from app.main import create_app

    routes = [row for row in helpers.route_table(create_app()) if row[0] == "/admin/assignment"]
    assert routes == [("/admin/assignment", ("GET",))]


async def test_r1_shows_created_sessions(client: AsyncClient) -> None:
    created = await helpers.create_session(client, "P00")
    body = (await client.get("/admin/participants", auth=ADMIN_AUTH)).json()
    p00 = next(row for row in body["participants"] if row["participant_no"] == "P00")
    assert created["session_id"] in [row["session_id"] for row in p00["sessions"]]
    assert p00["sessions"][0]["ss_state"] == SsState.CREATED.value


async def test_costs_sums_llm_calls(client: AsyncClient) -> None:
    """§2.8 — 대시보드 없이 R1에 합산만 띄운다."""
    await helpers.reach_focal(client, "P00")
    await helpers.complete_focal(client)
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
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)
    await helpers.advance(client, "P11")
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
    # §2.7 v2 — checkpoint 수정 diff + 경보를 R2가 보여야 한다.
    await helpers.edit_checkpoint(client, "trouble_cue", "그렇게까지는 아니었어")
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    await helpers.complete_focal(client)

    body = await _monitor(client, created["session_id"])
    assert body["session"]["ss_state"] == SsState.FOCAL.value
    assert body["session"]["screen"] == "P7"

    focal = body["focal"]
    assert focal["condition"] == "C1"  # P00 QA 고정값
    assert focal["ai2_state"] == "clean"
    assert focal["checkpoint_edited"] is True
    # §6.4 R-2 — overlap은 위반 목록이 아니라 별도 열이다.
    assert focal["alt_overlap"] == []

    # §2.7·§3.4 — 수정 diff + **경보**(trouble_cue는 자극 전제 segment다).
    assert body["checkpoint"]["alert"] is True
    edit = body["checkpoint"]["edits"][0]
    assert edit["segment"] == "trouble_cue" and edit["alert"] is True
    assert edit["original"] and edit["edited"], "diff가 복호화되지 않았다"

    roles = [turn["role"] for turn in body["transcript"]]
    assert roles == ["ai1", "user1", "ai2", "user2"]
    assert all(turn["text"] for turn in body["transcript"]), "복호화된 transcript가 비어 있다"

    # §2.7·§2.9 — 조회 1회 = view + decrypt.
    assert f"session:{created['session_id']}" in [log.target for log in await _audit(session, "view")]
    assert [log.target for log in await _audit(session, "decrypt")] == [
        f"session:{created['session_id']}:transcript"
    ]


async def test_r2_monitor_reports_fallback_as_pipeline_state(client: AsyncClient, llm) -> None:
    """§4.13 — 생성 중/재생성/fallback 표시. fallback은 눈에 띄어야 한다(§2.8 알림과 같은 사건)."""
    from app.llm.fake_llm import fixture_token

    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    # 두 시도 모두 규칙 위반 → §6.5 neutral_fallback.
    await client.post(
        "/api/focal/user1", json={"text": f"비교만 해줘 {fixture_token('too_long')}"}
    )
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    body = await _monitor(client, created["session_id"])
    assert body["focal"]["ai2_state"] == "fallback"
    assert body["focal"]["attempts"] >= 2


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


async def test_r3_contrastive_view_shows_everything_the_interview_needs(
    client: AsyncClient, session
) -> None:
    """§4.13 R3 — ① focal trajectory ② 평정·MC ③ 대안 순서 ④ 세 pair ⑤ researcher_only ⑥ flag."""
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post(
        "/api/focal/sidecar",
        json={
            "has_more": True,
            "free_text": "사실 이직은 이미 정했다",
            "provenance": "preexisting",
            "reason": "말하기 번거로웠다",
        },
    )
    await client.post("/api/focal/ai2")
    await helpers.advance(client, "P6")
    await client.post(
        "/api/focal/downstream",
        json={"disposition": "end", "end_type": "seek_human", "reason": "사람에게 묻고 싶다"},
    )
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)

    body = (await client.get(f"/admin/review/{created['session_id']}", auth=ADMIN_AUTH)).json()

    # ① focal trajectory — **조건 라벨이 붙는다**(참가자 화면과 다른 점).
    trajectory = body["trajectory"]
    assert trajectory["condition"] == "C1"
    assert trajectory["ai1"] and trajectory["user1"] == "비교만 해줘"
    assert trajectory["ai2"] and trajectory["ai2_state"] == "clean"
    # sidecar가 보인다(§4.13 — 참가자에게는 재표시 없음).
    assert trajectory["sidecar"]["free_text"] == "사실 이직은 이미 정했다"
    assert trajectory["sidecar"]["provenance"] == "preexisting"
    assert trajectory["sidecar"]["reason_text"] == "말하기 번거로웠다"
    assert trajectory["downstream"]["end_type"] == "seek_human"
    assert trajectory["downstream"]["reason_text"] == "사람에게 묻고 싶다"
    # §8.4 — generation 경로가 그대로 보인다(NT-15).
    assert trajectory["generation_path"] and trajectory["generation_path"][-1]["final"] is True

    # ② 평정·MC
    from app.assets import rating_items

    assert len(body["ratings"]) == rating_items.load().item_count
    assert {row["scope"] for row in body["ratings"]} == {"focal", "mc"}

    # ③ 대안 노출 순서
    assert [row["position"] for row in body["alt_exposures"]] == [1, 2, 3]
    assert all(row["ai1"] for row in body["alt_exposures"])

    # ④ 세 pair — 좌우·조건 라벨·focal 포함 여부·응답값
    assert len(body["pairs"]) == 3
    for pair in body["pairs"]:
        assert pair["left"]["condition"] and pair["right"]["condition"]
        assert pair["responses"], "문항 응답이 비어 있다"
        assert all(row["text"] for row in pair["responses"])
    assert any(pair["focal_included"] for pair in body["pairs"])

    # ⑤ researcher_only + evidence_code
    assert body["researcher_only"]["retrospective_stance"]
    assert body["evidence_code"]["permitted_operation"]

    assert [log.target for log in await _audit(session, "decrypt")] == [
        f"session:{created['session_id']}:review"
    ]


async def test_nt39_participant_p11_has_none_of_the_researcher_payload(
    client: AsyncClient,
) -> None:
    """NT-39 — R3에 있는 것이 참가자 P11에는 **없다**.

    조건 라벨·sidecar·researcher_only·문항 응답값이 참가자 화면으로 새면 그 자체가 §1.2
    위반이고, 인터뷰 중 참가자가 그 값을 보면 응답이 오염된다.
    """
    import json

    from app.assets.dossier_private import load_researcher_only

    await helpers.reach_focal(client, "P00")
    await helpers.complete_focal(client, has_more=True)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)

    state = await helpers.state(client)
    assert state["screen"] == "P11"
    text = json.dumps(state, ensure_ascii=False)

    for label in ("C1", "C2", "C3", "C4"):
        assert f'"{label}"' not in text
    assert "사실 한 가지 더 있었어" not in text, "sidecar가 참가자 화면에 재표시됐다"
    assert "focal_included" not in text and "focal_side" not in text
    for value in load_researcher_only("P00").values():
        assert str(value)[:20] not in text
    # 문항·응답값도 재표시하지 않는다(§4.11).
    assert "responses" not in text and "item_id" not in text


async def test_r3_review_lists_flags_with_reasons(client: AsyncClient) -> None:
    created, _ = await helpers.open_and_join(client, "P00")
    await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": "checkpoint 수정이 자극 전제를 건드림 — 계속 진행 판단(§3.4)"},
        auth=ADMIN_AUTH,
    )
    body = (await client.get(f"/admin/review/{created['session_id']}", auth=ADMIN_AUTH)).json()
    assert body["flags"][0]["payload"]["reason"].startswith("checkpoint 수정이")


# --------------------------------------------------------------------------- #
# R4 dossier 뷰어 (§4.12 · §5.2)
# --------------------------------------------------------------------------- #


async def test_r4_viewer_shows_layers_segments_assembled_stimuli_and_assignment(
    client: AsyncClient, session
) -> None:
    """§4.13 R4 — 3층 + evidence code + R/U/Q segment + 조립 4자극 + fallback + QC + 배정."""
    body = (await client.get("/admin/dossier/P00", auth=ADMIN_AUTH)).json()

    assert [row["condition"] for row in body["stimuli"]] == ["C1", "C2", "C3", "C4"]
    assert all(row["text"] and row["hash"] for row in body["stimuli"])
    # §5.4 질문 수 계약이 화면에서도 보인다(NT-22).
    questions = {row["condition"]: row["meta"]["questions"] for row in body["stimuli"]}
    assert questions == {"C1": 0, "C2": 1, "C3": 0, "C4": 1}
    # 조립 레시피가 보인다 — 네 전문을 저장하지 않는다는 사실이 화면에 드러난다(D-35).
    recipes = {row["condition"]: row["recipe"] for row in body["stimuli"]}
    assert recipes == {"C1": ["r"], "C2": ["r", "q"], "C3": ["r", "u"], "C4": ["r", "u", "q"]}

    assert set(body["segments"]) == {"r", "u", "q"}
    assert body["ai_visible"]["situation_summary"]
    assert body["ai_visible"]["provenance"]
    assert body["evidence_code"]["prohibited_inference"]
    assert body["neutral_fallback"]
    assert set(body["qc"]) >= {"r_identity", "u_identity", "q_identity", "reviewer"}
    assert body["researcher_only"]["retrospective_stance"]
    assert body["content_hash"] and "locked" in body
    # P00은 배정표에 없다(QA 합성 — §5.1).
    assert body["assignment"] is None

    assert [log.target for log in await _audit(session, "view")] == ["dossier:P00"]


async def test_r4_shows_the_assignment_row_for_real_participants(client: AsyncClient) -> None:
    """§4.13 R4 — 배정표 행이 함께 보인다(읽기 전용)."""
    from app.core import assignment

    participant_no = assignment.load().participant_numbers[0]
    body = (await client.get(f"/admin/dossier/{participant_no}", auth=ADMIN_AUTH)).json()
    assert body["assignment"]["focal_condition"] in {"C1", "C2", "C3", "C4"}
    assert len(body["assignment"]["alt_order"]) == 3


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
    """§5.3 — 자산 수정은 파일·2인 판정·lock 절차를 지난다. 콘솔에는 쓰기 경로가 없다."""
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
        # §9.1.1 [파일럿 확정 2026-08-26] — 연구자 되돌리기.
        ("/admin/sessions/{session_id}/rewind", ("POST",)),
        ("/admin/monitor/{session_id}", ("GET",)),
        ("/admin/review/{session_id}", ("GET",)),
        ("/admin/dossier/{participant_no}", ("GET",)),
        ("/admin/costs", ("GET",)),
        # §8.2 v2가 명시한 신설 — `GET /admin/assignment`.
        ("/admin/assignment", ("GET",)),
        # §4.13 R1 화면용 목록과 콘솔 페이지 — §8.2 표에는 없다(PROGRESS 확인 필요).
        ("/admin/participants", ("GET",)),
        ("/admin/console", ("GET",)),
    }


# --------------------------------------------------------------------------- #
# rewind — 연구자 되돌리기 (§9.1.1 [파일럿 확정 2026-08-26])
# --------------------------------------------------------------------------- #


async def _rewind(client: AsyncClient, session_id: Any, **body: Any):
    return await client.post(
        f"/admin/sessions/{session_id}/rewind", json=body, auth=ADMIN_AUTH
    )


async def _reach_pairwise(client: AsyncClient, session) -> str:
    """SS07 pair 1까지 진행한 세션 id."""
    await helpers.reach_focal(client)
    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    row = (await session.execute(select(tables.Session))).scalars().one()
    return str(row.id)


async def test_rewind_discards_only_the_targeted_pairs(
    client: AsyncClient, session
) -> None:
    """§9.1.1 — P10 position 2로 되돌리면 2·3만 지워지고 1은 남는다."""
    session_id = await _reach_pairwise(client, session)
    await helpers.complete_pairwise(client)  # 세 pair 전부 제출 → SS08

    response = await _rewind(client, session_id, screen="P10", position=2, reason="참가자 오조작")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ss_state"] == SsState.PAIRWISE.value and body["pair_index"] == 2

    views = {
        view.position: view
        for view in (await session.execute(select(tables.PairwiseView))).scalars().all()
    }
    assert views[1].submitted_at is not None, "되돌리지 않은 pair 1은 그대로여야 한다"
    assert views[2].submitted_at is None and views[3].submitted_at is None

    remaining = (await session.execute(select(tables.PairwiseResponse))).scalars().all()
    assert {row.pairwise_view_id for row in remaining} == {views[1].id}


async def test_rewind_lets_the_participant_answer_again(
    client: AsyncClient, session
) -> None:
    """되돌리기의 목적 — 재제출이 UNIQUE 충돌 없이 다시 된다(§3.5 idempotency = 상태)."""
    session_id = await _reach_pairwise(client, session)
    await helpers.complete_pairwise(client, value=3)
    await _rewind(client, session_id, screen="P10", position=1, reason="처음부터 다시")

    state = await helpers.state(client)
    assert state["screen"] == "P10" and state["pair_index"] == 1
    after = await helpers.complete_pairwise(client, value=6)
    assert after["ss_state"] == SsState.INTERVIEW.value

    values = {
        row.value
        for row in (await session.execute(select(tables.PairwiseResponse))).scalars().all()
    }
    assert values == {6}, "재제출 값만 남아야 한다"


async def test_rewind_keeps_the_same_stimuli_and_order(
    client: AsyncClient, session
) -> None:
    """NT-08 — 되돌려도 재추첨하지 않는다: 좌우·조건·문항 순서가 같다."""
    session_id = await _reach_pairwise(client, session)
    before = await helpers.state(client)
    await helpers.complete_pairwise(client)
    await _rewind(client, session_id, screen="P10", position=1, reason="다시")
    after = await helpers.state(client)

    assert [side["ai1"] for side in after["data"]["sides"]] == [
        side["ai1"] for side in before["data"]["sides"]
    ]
    assert [item["text"] for item in after["data"]["items"]] == [
        item["text"] for item in before["data"]["items"]
    ]


async def test_rewind_to_ratings_clears_them_and_resets_alt_exposures(
    client: AsyncClient, session
) -> None:
    """P8로 되돌리면 `ratings`가 지워지고 대안 노출을 다시 걷는다 — 노출 행 자체는 남는다."""
    session_id = await _reach_pairwise(client, session)
    exposures_before = {
        row.position: row.stimulus_hash
        for row in (await session.execute(select(tables.AltExposure))).scalars().all()
    }

    response = await _rewind(client, session_id, screen="P8", reason="평정 오조작")
    assert response.status_code == 200, response.text
    assert response.json()["ss_state"] == SsState.FOCAL_MEASURES.value

    assert (await session.execute(select(tables.Rating))).scalars().all() == []
    rows = (await session.execute(select(tables.AltExposure))).scalars().all()
    assert {row.position: row.stimulus_hash for row in rows} == exposures_before
    assert all(row.advanced_at is None for row in rows)


async def test_rewind_never_touches_the_generation_audit(
    client: AsyncClient, session
) -> None:
    """§6.6 — `generations`·`llm_calls`는 되돌리기의 대상이 아니다."""
    session_id = await _reach_pairwise(client, session)
    before = len((await session.execute(select(tables.Generation))).scalars().all())
    assert before > 0
    await _rewind(client, session_id, screen="P8", reason="평정 오조작")
    after = len((await session.execute(select(tables.Generation))).scalars().all())
    assert after == before


async def test_rewind_records_snapshot_audit_and_encrypted_reason(
    client: AsyncClient, session
) -> None:
    """§9.1.1 — 지운 값은 events 스냅샷, 행위는 audit, 사유는 🔒."""
    session_id = await _reach_pairwise(client, session)
    await helpers.complete_pairwise(client, value=5)
    await _rewind(client, session_id, screen="P10", position=1, reason="참가자가 잘못 눌렀다")

    events = (
        (await session.execute(select(tables.Event).where(tables.Event.type == "rewind")))
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["from"]["ss_state"] == SsState.INTERVIEW.value
    assert payload["to"]["pair_index"] == 1
    assert len(payload["discarded"]["pairwise"]) == 3
    assert payload["discarded"]["pairwise"][0]["responses"][0]["value"] == 5

    from app.security import fernet

    assert "참가자가 잘못 눌렀다" not in str(payload), "사유가 평문으로 남았다"
    assert fernet.decrypt(payload["reason_encrypted"].encode("ascii")) == "참가자가 잘못 눌렀다"
    assert len(await _audit(session, "rewind")) == 1


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ({"screen": "P11", "reason": "x"}, "전진 방향"),
        ({"screen": "P4", "reason": "x"}, "되돌릴 수 없는 화면"),
        ({"screen": "P10", "position": 9, "reason": "x"}, "position 범위 밖"),
        ({"screen": "P10", "reason": "x"}, "position 누락"),
    ],
)
async def test_rewind_rejects_illegal_targets(
    client: AsyncClient, session, body: dict[str, Any], why: str
) -> None:
    """§9.1.1 — 되돌리기로 앞으로 밀거나 금지 구간에 손댈 수 없다."""
    session_id = await _reach_pairwise(client, session)
    response = await _rewind(client, session_id, **body)
    assert response.status_code == 409, f"{why}: {response.text}"


async def test_rewind_is_blocked_before_focal_measures_and_after_debrief(
    client: AsyncClient, session
) -> None:
    """focal은 abort의 영역이고(§9.1.1 금지 ①), 디브리핑 이후 재측정은 오염이다(금지 ②)."""
    await helpers.reach_focal(client)
    row = (await session.execute(select(tables.Session))).scalars().one()
    assert (await _rewind(client, str(row.id), screen="P8", reason="x")).status_code == 409

    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)
    await helpers.advance(client, "P11")
    await client.post("/api/debrief/confirm")
    assert (await _rewind(client, str(row.id), screen="P8", reason="x")).status_code == 409


async def test_rewind_requires_admin_auth(client: AsyncClient, session) -> None:
    """§2.7 — 되돌리기는 콘솔 뒤에 있다."""
    session_id = await _reach_pairwise(client, session)
    response = await client.post(
        f"/admin/sessions/{session_id}/rewind", json={"screen": "P8", "reason": "x"}
    )
    assert response.status_code == 401
