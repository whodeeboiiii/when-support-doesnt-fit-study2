"""세션 완주와 그 불변식 (구현명세서 §3 · §8.2 · NT-07·08·09·12·14·16·31·33).

한 참가자의 경로는 **SS00 → SS10**이고 그 안에 focal 1회 + 대안 3 + pairwise 3이 있다.
이 파일은 그 경로를 실제 HTTP로 밟으며 §3의 불변식을 확인한다.

여기서 보는 것과 보지 않는 것을 갈라 둔다.
- **본다**: 상태 전이, 배정 불변성, 복구, 중복 제출, 비합법 전이 거부, 대안 노출 시점.
- **보지 않는다**: AI2 payload 내용(→ `test_evidence_boundary.py`), 콘솔(→ `test_console.py`).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader, screen_copy
from app.core import assignment
from app.models import tables
from tests import helpers


async def _count(db: AsyncSession, model) -> int:  # noqa: ANN001
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


# --------------------------------------------------------------------------- #
# 완주 (§11.2 Definition of Done 1행)
# --------------------------------------------------------------------------- #


async def test_full_session_reaches_ss10(client: AsyncClient, session: AsyncSession) -> None:
    """SS00 → SS10 전 경로 — checkpoint 수정 포함, User2 reply."""
    await helpers.open_and_join(client)
    await helpers.consent(client)
    # 수정은 SS02에서만 가능하다 — confirm 전에 한다(§4.2 · NT-35).
    await helpers.edit_checkpoint(client, "situation_summary", "수정된 상황 요약입니다.")
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")

    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)
    await helpers.advance(client, "P11")
    response = await client.post("/api/debrief/confirm")
    assert response.status_code == 200
    state = response.json()
    assert state["screen"] == "DONE"
    assert state["ss_state"] == "SS10"
    assert state["status"] == "done"

    assert await _count(session, tables.FocalRun) == 1, "focal run은 참가자당 1행이다 (D-23)"
    assert await _count(session, tables.AltExposure) == 3
    assert await _count(session, tables.PairwiseView) == 3
    # 평정은 세션 수준 1세트다(branch당이 아니라).
    from app.assets import rating_items

    assert await _count(session, tables.Rating) == rating_items.load().item_count


async def test_screens_visited_in_order(client: AsyncClient) -> None:
    """§0.2 — P0 → … → P12. 화면이 건너뛰이지 않는다."""
    seen: list[str] = []

    async def note() -> str:
        state = await helpers.state(client)
        seen.append(state["screen"])
        return state["screen"]

    await helpers.open_and_join(client)
    await note()  # P1
    await helpers.consent(client)
    await note()  # P2
    await helpers.confirm_checkpoint(client)
    await note()  # P3
    await helpers.advance(client, "P3")
    await note()  # P4
    await helpers.complete_focal(client)
    await note()  # P7 (F5 종료 안내)
    await helpers.advance(client, "P7")
    await note()  # P8
    await helpers.submit_ratings(client)
    await note()  # P9
    await helpers.complete_alt_exposures(client)
    await note()  # P10
    await helpers.complete_pairwise(client)
    await note()  # P11
    await helpers.advance(client, "P11")
    await note()  # P12

    assert seen == ["P1", "P2", "P3", "P4", "P7", "P8", "P9", "P10", "P11", "P12"]


async def test_end_disposition_completes_too(client: AsyncClient, session: AsyncSession) -> None:
    """§4.7 · D-26 — `end`도 유효한 종결이다. 이후 경로가 같다(판정 없음 — §0.3)."""
    state = await helpers.complete_session(client, disposition="end", end_type="switch_ai")
    assert state["ss_state"] == "SS10"

    action = (await session.execute(select(tables.DownstreamAction))).scalars().one()
    assert action.disposition == "end"
    assert action.end_type == "switch_ai"
    # `reply`가 아니므로 User2 turn이 없다.
    roles = {row.role for row in (await session.execute(select(tables.Turn))).scalars().all()}
    assert roles == {"ai1", "user1", "ai2"}


# --------------------------------------------------------------------------- #
# NT-07 — 배정은 최초 저장 후 불변, 조건 확정은 F0 진입 1회
# --------------------------------------------------------------------------- #


async def test_condition_comes_from_assignment_not_computed(
    client: AsyncClient, session: AsyncSession
) -> None:
    """D-30 — 시스템은 배정을 **계산하지 않는다**. P00은 QA 고정값(C1)을 쓴다."""
    await helpers.reach_focal(client)
    run = (await session.execute(select(tables.FocalRun))).scalars().one()
    participant = await session.get(tables.Participant, "P00")
    assert run.condition == participant.focal_condition
    assert participant.alt_order == ["C2", "C3", "C4"]
    assert run.condition not in participant.alt_order, "alt_order에 focal이 있다"


async def test_condition_and_hash_are_immutable_across_refresh(
    client: AsyncClient, session: AsyncSession
) -> None:
    """NT-07 — 재진입·새로고침을 반복해도 조건·자극 hash가 바뀌지 않고, ai1 turn은 1건이다."""
    await helpers.reach_focal(client)
    run = (await session.execute(select(tables.FocalRun))).scalars().one()
    condition, stimulus_hash = run.condition, run.stimulus_hash

    for _ in range(3):
        await helpers.state(client)
        # 이미 지나간 화면에서 온 advance는 현재 상태를 그대로 돌려준다(§9.1).
        await helpers.advance(client, "P3")

    await session.refresh(run)
    assert (run.condition, run.stimulus_hash) == (condition, stimulus_hash)

    ai1_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(tables.Turn)
                .where(tables.Turn.role == "ai1")
            )
        ).scalar_one()
    )
    assert ai1_count == 1, "AI1 turn이 재생성됐다 (NT-07)"


async def test_stimulus_hash_matches_assembled_stimulus(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§5.4 — 저장된 hash가 조립 결과의 sha256이다(사후 대조의 근거)."""
    await helpers.reach_focal(client)
    run = (await session.execute(select(tables.FocalRun))).scalars().one()
    dossier = dossier_loader.load("P00")
    assert run.stimulus_hash == dossier.stimulus_hash(run.condition)


# --------------------------------------------------------------------------- #
# NT-08 — 새로고침·재접속 복구
# --------------------------------------------------------------------------- #


async def test_reconnect_restores_saved_position(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§3.5 — 쿠키를 지우고 다시 접속해도 저장 지점에서 복원된다. 재생성 0건."""
    created, _ = await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    await client.post("/api/focal/user1", json={"text": "장기 계획 말고 비교만 해줘"})

    before = await helpers.state(client)
    client.cookies.clear()
    restored = await helpers.join(client, "P00", created["access_code"])

    assert restored["restored"] is True
    assert restored["screen"] == before["screen"] == "P5"
    assert restored["f_state"] == "F2"
    # User1 turn이 하나뿐 — 재접속이 재제출이 되지 않는다.
    assert await _count(session, tables.Turn) == 2  # ai1 + user1


async def test_ai2_is_not_regenerated_on_refresh(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """NT-08 — 저장된 산출물이 있으면 그대로 재서빙한다(재생성 0건)."""
    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    first = await client.post("/api/focal/ai2")
    assert first.status_code == 200

    calls_before = llm.call_count("ai2_generation")
    for _ in range(3):
        replay = await client.post("/api/focal/ai2")
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
    assert llm.call_count("ai2_generation") == calls_before

    finals = int(
        (
            await session.execute(
                select(func.count())
                .select_from(tables.Generation)
                .where(tables.Generation.final.is_(True))
            )
        ).scalar_one()
    )
    assert finals == 1, "final 생성물은 세션당 1행이다"


# --------------------------------------------------------------------------- #
# NT-09 — 중복 제출 idempotency
# --------------------------------------------------------------------------- #


async def test_duplicate_submissions_are_idempotent(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§9.1 — 재제출은 200 + 기존 레코드. 행이 늘지 않는다."""
    await helpers.reach_focal(client)

    # 세션 수준 — 동의·checkpoint 확인
    assert (await client.post("/api/consent", json={"items": {}})).status_code == 200

    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    for _ in range(2):
        response = await client.post("/api/focal/user1", json={"text": "다른 내용"})
        assert response.status_code == 200
        assert response.json()["replayed"] is True
    assert await _count(session, tables.Turn) == 2  # ai1 + user1 — 두 번째 user1이 없다

    await client.post("/api/focal/sidecar", json={"has_more": False})
    for _ in range(2):
        response = await client.post("/api/focal/sidecar", json={"has_more": True})
        assert response.status_code == 200
        assert response.json()["replayed"] is True
    assert await _count(session, tables.SidecarEntry) == 1


async def test_duplicate_pairwise_submission_is_idempotent(
    client: AsyncClient, session: AsyncSession
) -> None:
    """NT-09 — 위치 단계도 재제출을 흡수한다(§8.2 idempotency key의 index 성분)."""
    await helpers.reach_focal(client)
    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)

    state = await helpers.state(client)
    count = len(state["data"]["items"])
    payload = {"items": [{"position": index, "value": 4} for index in range(1, count + 1)]}
    assert (await client.post("/api/pairwise/1", json=payload)).status_code == 200

    replay = await client.post("/api/pairwise/1", json=payload)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert await _count(session, tables.PairwiseResponse) == count


# --------------------------------------------------------------------------- #
# NT-14 — 비합법 전이는 409
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/focal/user1", {"text": "아직 focal이 아니다"}),
        ("post", "/api/focal/sidecar", {"has_more": False}),
        ("post", "/api/focal/ai2", None),
        ("post", "/api/focal/downstream", {"disposition": "reply", "text": "x"}),
        ("post", "/api/ratings", {"items": []}),
        ("post", "/api/pairwise/1", {"items": []}),
    ],
)
async def test_submitting_out_of_order_is_rejected(
    client: AsyncClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    """§3 — 앞 단계를 건너뛴 제출은 전부 409다."""
    await helpers.open_and_join(client)  # SS01에 머문다
    response = await getattr(client, method)(path, json=body)
    assert response.status_code == 409, f"{path}: {response.status_code}"


async def test_ai2_before_sidecar_is_rejected(client: AsyncClient, llm) -> None:
    """NT-16 — sidecar 제출 전 AI2 호출 0건. 상태로 강제된다(§3.2 · §8.3)."""
    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})

    response = await client.post("/api/focal/ai2")
    assert response.status_code == 409
    assert llm.call_count("ai2_generation") == 0, "sidecar 전에 모델을 불렀다 (NT-16)"


async def test_user1_requires_text(client: AsyncClient) -> None:
    """NT-40 — 빈 텍스트 400. **no_reply/end 경로가 없다**(D-32)."""
    await helpers.reach_focal(client)
    for body in ({"text": ""}, {"text": "   "}):
        response = await client.post("/api/focal/user1", json=body)
        assert response.status_code == 400
        assert screen_copy.USER1_EMPTY in response.text


async def test_no_reply_endpoint_does_not_exist(client: AsyncClient) -> None:
    """NT-40 — 엔드포인트·상태 어디에도 no_reply가 없다.

    "disposition" 인자를 User1에 실어 보내도 무시된다(모델이 그 필드를 모른다).
    """
    from app.main import create_app

    paths = {path for path, _ in helpers.route_table(create_app())}
    assert not any("no_reply" in path for path in paths)
    assert "/api/focal/user1" in paths
    # 구 4-branch 경로가 남아 있지 않다.
    assert not any("/branch/" in path for path in paths)


# --------------------------------------------------------------------------- #
# NT-33 — position 건너뛰기 불가
# --------------------------------------------------------------------------- #


async def test_pairwise_position_cannot_be_skipped(client: AsyncClient) -> None:
    """§3.3 — 서버가 `pair_index`를 소유한다. 3번을 먼저 제출할 수 없다."""
    await helpers.reach_focal(client)
    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)

    state = await helpers.state(client)
    assert state["pair_index"] == 1
    count = len(state["data"]["items"])
    payload = {"items": [{"position": index, "value": 4} for index in range(1, count + 1)]}
    response = await client.post("/api/pairwise/3", json=payload)
    assert response.status_code == 409


async def test_alt_and_pair_order_follow_the_assignment(
    client: AsyncClient, session: AsyncSession
) -> None:
    """NT-33 — 대안 노출·pair 제시가 배정표 순서와 일치한다."""
    await helpers.complete_session(client)
    participant = await session.get(tables.Participant, "P00")

    exposures = (
        (await session.execute(select(tables.AltExposure).order_by(tables.AltExposure.position)))
        .scalars()
        .all()
    )
    assert [row.condition for row in exposures] == list(participant.alt_order)
    assert [row.position for row in exposures] == [1, 2, 3]

    views = (
        (await session.execute(select(tables.PairwiseView).order_by(tables.PairwiseView.position)))
        .scalars()
        .all()
    )
    assert [row.contrast for row in views] == list(participant.pair_order)
    for view in views:
        expected = participant.pair_sides[view.contrast]
        assert [view.left_condition, view.right_condition] == list(expected)


# --------------------------------------------------------------------------- #
# NT-31 — focal 측정 전 대안 자극 0회
# --------------------------------------------------------------------------- #


async def test_no_alternative_stimulus_before_focal_measures(client: AsyncClient) -> None:
    """§1.2 — focal 측정(SS05) 완료 전 `GET /state`에 non-focal 자극 문자열이 0회.

    P00은 focal이 C1(= `r`)이므로 대안은 `u`·`q`를 포함한다. 그 두 segment가 payload
    어디에도 없으면 대안 자극이 실릴 방법이 없다.
    """
    import json

    dossier = dossier_loader.load("P00")
    await helpers.open_and_join(client)

    async def payload_text() -> str:
        return json.dumps(await helpers.state(client), ensure_ascii=False)

    checkpoints = []
    checkpoints.append(await payload_text())  # P1
    await helpers.consent(client)
    checkpoints.append(await payload_text())  # P2
    await helpers.confirm_checkpoint(client)
    checkpoints.append(await payload_text())  # P3
    await helpers.advance(client, "P3")
    checkpoints.append(await payload_text())  # P4
    await helpers.complete_focal(client)
    checkpoints.append(await payload_text())  # P7
    await helpers.advance(client, "P7")
    checkpoints.append(await payload_text())  # P8 — 평정. 아직 제출 전이다.

    non_focal = [dossier.stimulus.u, dossier.stimulus.q]
    for index, text in enumerate(checkpoints):
        for segment in non_focal:
            assert segment not in text, f"checkpoint {index}: 대안 segment가 payload에 있다 (NT-31)"
        for condition in ("C2", "C3", "C4"):
            assert dossier.assemble(condition) not in text

    # 평정 제출 후에야 대안이 나온다.
    await helpers.submit_ratings(client)
    after = await payload_text()
    assert any(segment in after for segment in non_focal), "대안 노출이 시작되지 않았다"


async def test_state_payload_never_carries_condition_labels(client: AsyncClient) -> None:
    """§1.2 — 조건 라벨(C1–C4)·배정표가 참가자 payload에 실리지 않는다."""
    import json

    await helpers.reach_focal(client)
    states = [await helpers.state(client)]
    await helpers.complete_focal(client)
    states.append(await helpers.state(client))
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    states.append(await helpers.state(client))
    await helpers.complete_alt_exposures(client)
    states.append(await helpers.state(client))

    for state in states:
        text = json.dumps(state, ensure_ascii=False)
        for label in ("C1", "C2", "C3", "C4"):
            assert f'"{label}"' not in text
        for banned in ("focal_condition", "alt_order", "pair_sides", "a_level"):
            assert banned not in text


# --------------------------------------------------------------------------- #
# NT-12 — 참가자당 완료 세션 1개
# --------------------------------------------------------------------------- #


async def test_second_session_is_blocked_for_real_participants(client: AsyncClient) -> None:
    """§2.5 — 진행 중이거나 완료된 세션이 있으면 새 세션을 만들지 않는다. P00은 예외."""
    table = assignment.load()
    participant_no = table.participant_numbers[0]

    await helpers.create_session(client, participant_no)
    response = await client.post(
        "/admin/sessions", json={"participant_no": participant_no}, auth=helpers.ADMIN_AUTH
    )
    assert response.status_code == 409

    # P00은 QA 전용이라 무제한이다(§2.5).
    await helpers.create_session(client, "P00")
    await helpers.create_session(client, "P00")


async def test_participant_outside_the_assignment_cannot_start(client: AsyncClient) -> None:
    """§5.1 — 배정표의 행이 곧 참가자 목록이다. 없는 번호로 세션을 열지 않는다."""
    table = assignment.load()
    outside = next(
        no for no in (f"P{n:02d}" for n in range(25, 31)) if not table.has(no)
    )
    response = await client.post(
        "/admin/sessions", json={"participant_no": outside}, auth=helpers.ADMIN_AUTH
    )
    assert response.status_code == 409
    assert "배정표" in response.text
