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
    await helpers.presurvey(client)
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
    """§0.2 — P0 → … → P12. 화면이 건너뛰이지 않는다. P1S는 D-44로 끼어든 자리다."""
    seen: list[str] = []

    async def note() -> str:
        state = await helpers.state(client)
        seen.append(state["screen"])
        return state["screen"]

    await helpers.open_and_join(client)
    await note()  # P1
    await helpers.consent(client)
    await note()  # P1S — 동의 직후·checkpoint 직전 (D-44)
    await helpers.presurvey(client)
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

    assert seen == ["P1", "P1S", "P2", "P3", "P4", "P7", "P8", "P9", "P10", "P11", "P12"]


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
    await helpers.presurvey(client)
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
# NT-46 — 사전 설문 경로 (§4.1S · D-44)
# --------------------------------------------------------------------------- #


def _presurvey_answers(likert: int = 4) -> list[dict[str, Any]]:
    from app.assets import presurvey

    answers: list[dict[str, Any]] = []
    for position, item in enumerate(presurvey.load().items, start=1):
        if item.type == "single_choice":
            value: Any = item.options[0].value
        elif item.type == "multi_choice":
            value = [item.options[0].value]
        else:
            value = likert
        answers.append({"position": position, "value": value})
    return answers


async def test_presurvey_sits_between_consent_and_checkpoint(client: AsyncClient) -> None:
    """§3.1 — SS01 → SS01S → SS02. 동의 직후이고 checkpoint 직전이다."""
    await helpers.open_and_join(client)
    state = await helpers.consent(client)
    assert state["screen"] == "P1S" and state["ss_state"] == "SS01S"

    state = await helpers.presurvey(client)
    assert state["screen"] == "P2" and state["ss_state"] == "SS02"


async def test_presurvey_cannot_be_skipped(client: AsyncClient) -> None:
    """NT-14 — 사전 설문을 건너뛰고 checkpoint를 확인할 수 없다."""
    await helpers.open_and_join(client)
    await helpers.consent(client)
    assert (await client.post("/api/checkpoint/confirm")).status_code == 409
    assert (
        await client.post(
            "/api/checkpoint/edit", json={"segment": "situation_summary", "text": "다른 요약"}
        )
    ).status_code == 409


async def test_presurvey_requires_every_item(client: AsyncClient, session: AsyncSession) -> None:
    """§4.1S — 전 문항 필수. 부분 제출은 400이고 **행이 남지 않는다**."""
    await helpers.open_and_join(client)
    await helpers.consent(client)

    partial = _presurvey_answers()[:-1]
    response = await client.post("/api/presurvey", json={"responses": partial})
    assert response.status_code == 400
    assert await _count(session, tables.PresurveyResponse) == 0, "거부된 제출이 저장됐다"


async def test_presurvey_rejects_values_outside_the_asset(client: AsyncClient) -> None:
    """§4.1S — 값 검증은 자산이 한다. 선택지 밖·척도 밖은 400이다."""
    await helpers.open_and_join(client)
    await helpers.consent(client)

    for bad in ("없는_선택지", 99):
        answers = _presurvey_answers()
        # 1번은 single_choice, 마지막은 likert다 — 각각에 맞는 잘못된 값을 넣는다.
        target = 0 if isinstance(bad, str) else -1
        answers[target] = {**answers[target], "value": bad}
        response = await client.post("/api/presurvey", json={"responses": answers})
        assert response.status_code == 400, f"{bad!r}가 통과했다"


async def test_presurvey_stores_item_ids_not_positions(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§8.1 · NT-05 — 위치로 받아 **문항 ID로** 저장한다. 환원은 서버에서만 일어난다."""
    from app.assets import presurvey

    await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.presurvey(client)

    rows = (await session.execute(select(tables.PresurveyResponse))).scalars().all()
    asset = presurvey.load()
    assert {row.item_id for row in rows} == {item.item_id for item in asset.items}
    assert sorted(row.display_order for row in rows) == list(range(1, asset.item_count + 1))
    # 복수 선택은 리스트 그대로 남는다(§8.1 value=jsonb).
    stored = {row.item_id: row.value for row in rows}
    multi = [item for item in asset.items if item.type == "multi_choice"]
    assert multi, "복수 선택 문항이 없다 — 이 검사가 공허하게 통과한다"
    for item in multi:
        assert isinstance(stored[item.item_id], list)


async def test_duplicate_presurvey_submission_is_idempotent(
    client: AsyncClient, session: AsyncSession
) -> None:
    """NT-09 — 재제출은 200 + 저장 상태. 행이 늘지 않는다(§9.1 중복 제출)."""
    from app.assets import presurvey

    await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.presurvey(client)
    count = await _count(session, tables.PresurveyResponse)
    assert count == presurvey.load().item_count

    for _ in range(2):
        response = await client.post("/api/presurvey", json={"responses": _presurvey_answers(7)})
        assert response.status_code == 200
        assert response.json()["screen"] == "P2"
    assert await _count(session, tables.PresurveyResponse) == count, "재제출이 행을 늘렸다"


async def test_presurvey_payload_carries_no_item_ids(client: AsyncClient) -> None:
    """NT-05 — 참가자 payload에 문항 ID·`reverse`·section·`_note`가 없다."""
    import json

    from app.assets import presurvey

    await helpers.open_and_join(client)
    state = await helpers.consent(client)
    serialized = json.dumps(state, ensure_ascii=False)

    for item in presurvey.load().items:
        assert item.item_id not in serialized, f"문항 ID 누출: {item.item_id}"
        assert item.text in serialized, "문항 문면이 내려가지 않았다"
    for meta in ("reverse", "_note", "section", "ddi_excerpt"):
        assert meta not in serialized, f"연구자 메타 누출: {meta}"


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
    checkpoints.append(await payload_text())  # P1S
    await helpers.presurvey(client)
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


# --------------------------------------------------------------------------- #
# P7 채팅 맥락 — §4.7 지시문은 "본 것"을 가리킨다
# --------------------------------------------------------------------------- #


async def test_p7_carries_the_same_transcript_as_p6(client: AsyncClient, llm) -> None:
    """P7이 P6와 **같은** 채팅 맥락을 내려야 한다.

    §4.7 지시문은 "AI의 답변을 보셨습니다. 실제 상황이라면 지금 어떻게 하시겠어요?"다 —
    무엇에 대한 판단인지가 화면에 남아 있어야 성립한다. AI2 말풍선만 남기면 참가자는
    직전 화면에서 본 대화를 기억에 의존해 답하게 된다.
    """
    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": "장기 계획 말고 비교만 해줘"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    p6 = (await client.get("/api/state")).json()
    assert p6["screen"] == "P6"
    await helpers.advance(client, "P6")
    p7 = (await client.get("/api/state")).json()
    assert p7["screen"] == "P7"

    for field in ("checkpoint", "ai1", "user1", "ai2"):
        assert p7["data"].get(field), f"P7에 {field}가 없다"
        assert p7["data"][field] == p6["data"][field], f"{field}가 P6와 다르다"

    assert p7["data"]["instruction"] == (
        "AI의 답변을 보셨습니다. 실제 상황이라면 지금 어떻게 하시겠어요?"
    )


async def test_p7_shows_user2_after_reply(client: AsyncClient, llm) -> None:
    """답장을 보냈으면 그 답장도 기록의 일부다 — AI 응답은 여전히 없다(D-33)."""
    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")
    await helpers.advance(client, "P6")
    await client.post(
        "/api/focal/downstream", json={"disposition": "reply", "text": "그럼 안정성 쪽으로"}
    )

    data = (await client.get("/api/state")).json()["data"]
    assert data["submitted"] is True
    assert data["user2"] == "그럼 안정성 쪽으로"
    assert data["ai2"], "AI2도 계속 보여야 한다"
    assert "ai3" not in data


# --------------------------------------------------------------------------- #
# P10 버튼 · P11 사후 인터뷰 화면 (§4.10 · §4.11 [파일럿 확정 2026-08-26])
# --------------------------------------------------------------------------- #


async def _reach_interview(client: AsyncClient, user1: str = "비교만 해줘") -> dict[str, Any]:
    await helpers.reach_focal(client, "P00")
    await helpers.complete_focal(client, user1=user1)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)
    return await helpers.state(client)


async def test_p10_button_directs_the_per_pair_interview(client: AsyncClient) -> None:
    """§4.10 — pair마다 이 화면에서 인터뷰한다. 버튼이 그 순서를 지시하는 유일한 장치다."""
    await helpers.reach_focal(client, "P00")
    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)

    state = await helpers.state(client)
    assert state["screen"] == "P10"
    assert state["data"]["button"] == screen_copy.PAIRWISE_SUBMIT_BUTTON
    assert "연구자" in state["data"]["button"], "인터뷰 시점을 지시하지 않는 문안이다"


async def test_p11_shows_scenario_focal_conversation_and_three_alternatives(
    client: AsyncClient,
) -> None:
    """§4.11 — 처음 상황 → focal 대화(AI1·User1·AI2) → 나머지 세 응답 나열."""
    state = await _reach_interview(client, user1="장기 계획 말고 비교만")
    assert state["screen"] == "P11"
    data = state["data"]

    dossier = dossier_loader.load("P00")
    effective = dossier.ai_visible
    scenario_turns = [turn["text"] for turn in data["scenario"]["turns"]]
    assert scenario_turns == [
        effective.original_request,
        effective.problematic_ai_response,
        effective.trouble_cue,
    ]

    roles = [turn["role"] for turn in data["focal_turns"]]
    assert roles == ["ai", "user", "ai"], "focal AI1 → User1 → AI2 순서여야 한다"
    assert data["focal_turns"][1]["text"] == "장기 계획 말고 비교만", "참가자 본인 답장 재표시"
    assert data["focal_turns"][2]["text"], "AI2가 비어 있다"

    assert [item["label"] for item in data["alternatives"]] == [
        screen_copy.ALT_EXPOSURE_LABEL.format(position=position) for position in (1, 2, 3)
    ]


async def test_p11_alternatives_are_the_three_non_focal_conditions(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§4.11 — 나열되는 셋은 대안 노출과 같은 자극이고 focal은 그 안에 없다(초안 §7.10)."""
    state = await _reach_interview(client)
    dossier = dossier_loader.load("P00")
    run = (await session.execute(select(tables.FocalRun))).scalars().one()

    shown = [item["ai1"] for item in state["data"]["alternatives"]]
    exposures = (
        (await session.execute(select(tables.AltExposure).order_by(tables.AltExposure.position)))
        .scalars()
        .all()
    )
    # 화면에 나가는 것은 표시본이다 — 조립 자극 + (C3·C4) 무대지시(D-40).
    assert shown == [dossier.presented(row.condition) for row in exposures]
    assert dossier.presented(run.condition) not in shown, "focal이 '나머지 셋'에 섞였다"


async def test_p11_no_longer_carries_the_pairwise_layout(client: AsyncClient) -> None:
    """구판(세 pair 좌우 재배치)은 폐기됐다 — 되살아나면 §4.10과 중복 측정이 된다."""
    state = await _reach_interview(client)
    assert "pairs" not in state["data"]
    assert "sides" not in str(state["data"])


# --------------------------------------------------------------------------- #
# NT-43 — AI1 무대지시가 화면에 실린다 (§4.4 · D-40)
# --------------------------------------------------------------------------- #


async def test_p4_carries_the_uptake_note_for_a_c3_focal(client: AsyncClient) -> None:
    """D-40 — uptake가 있는 조건의 AI1은 "(그 후 …)"까지가 참가자가 보는 문면이다.

    P05는 dummy 배정표에서 focal C3다. u가 "…해 보겠습니다"로 끝나므로 무대지시가 없으면
    참가자는 "왜 해준다고만 하고 안 하지?"를 묻게 된다(P08 세션의 실제 반응).
    """
    state = await helpers.reach_focal(client, "P05")
    dossier = dossier_loader.load("P05")

    assert state["screen"] == "P4"
    assert state["data"]["ai1"] == dossier.presented("C3")
    # P05는 A2 — 무대지시가 "(그 후 …)" 쪽이다(D-47). 문면은 dossier가 고른다.
    assert dossier.uptake_note
    assert state["data"]["ai1"].endswith(dossier.uptake_note)


async def test_uptake_note_field_ships_regardless_of_condition(client: AsyncClient) -> None:
    """§1.2 · NT-31 — `ai1_note`는 **조건과 무관하게 항상** 내려간다.

    회색으로 그릴 자리를 클라이언트가 찾으려면 문면이 필요한데(NT-13 — 번들에 박지 않는다),
    그 필드가 조건에 따라 있고 없으면 **필드의 유무가 조건 단서**가 된다. C1 세션에서도
    같은 값이 내려가고, 다만 본문에 그 문자열이 없을 뿐이다.
    """
    state = await helpers.reach_focal(client, "P00")  # QA = focal C1
    dossier = dossier_loader.load("P00")

    assert state["data"]["ai1_note"] == dossier.uptake_note
    assert dossier.uptake_note not in state["data"]["ai1"]
    assert state["data"]["ai1"] == dossier.assemble("C1")


async def test_stored_ai1_turn_matches_what_was_shown(
    client: AsyncClient, session: AsyncSession
) -> None:
    """D-40 — `turns.ai1` 기록 = 화면 문면 = AI2 payload. 세 곳이 갈라지면 기록이 무의미하다."""
    from app.security import fernet

    state = await helpers.reach_focal(client, "P05")
    turn = (
        (await session.execute(select(tables.Turn).where(tables.Turn.role == "ai1")))
        .scalars()
        .one()
    )
    assert fernet.decrypt(turn.text) == state["data"]["ai1"]


async def test_pairwise_sides_carry_the_note_only_where_it_belongs(
    client: AsyncClient,
) -> None:
    """§4.10 — 두 열 중 u를 가진 쪽에만 무대지시가 붙는다(Scope = C1 vs C3)."""
    await helpers.reach_focal(client, "P00")
    await helpers.complete_focal(client)
    await helpers.advance(client, "P7")
    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)

    state = await helpers.state(client)
    dossier = dossier_loader.load("P00")
    assert state["screen"] == "P10"

    assert state["data"]["ai1_note"] == dossier.uptake_note
    texts = [side["ai1"] for side in state["data"]["sides"]]
    # 첫 pair는 정본 순서상 sequence(C2 vs C4) — C4 쪽 하나에만 붙는다(D-41).
    assert sum(dossier.uptake_note in text for text in texts) == 1
    assert set(texts) == {dossier.presented("C2"), dossier.presented("C4")}
