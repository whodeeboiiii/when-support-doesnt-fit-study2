"""세션 전 경로와 상태 불변식 (구현명세서 §3 · §4 · §8.2 · §9.1).

부록 C 대응: **NT-07 · NT-08 · NT-09 · NT-12 · NT-14 · NT-17 · NT-18 · NT-27**.

§11.3 Definition of Done의 첫 줄 — "P00 세션이 한 URL에서 SS00→SS07 전 경로(3종 종결 유형
포함)를 완료할 수 있다" — 이 파일의 첫 테스트다. 나머지는 그 경로 위에서 불변식을 흔든다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader, rating_items
from app.core.williams import condition as williams_condition
from app.models import tables
from tests import helpers


async def _session_row(db: AsyncSession, participant_no: str = "P00") -> tables.Session:
    result = await db.execute(
        select(tables.Session).where(tables.Session.participant_no == participant_no)
    )
    return result.scalars().one()


async def _count(db: AsyncSession, model) -> int:  # noqa: ANN001
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# --------------------------------------------------------------------------- #
# 전 경로 (§11.3)
# --------------------------------------------------------------------------- #


async def test_full_walkthrough_ss00_to_ss07(client: AsyncClient, session: AsyncSession) -> None:
    """SS00 → SS07. 종결 유형 3종을 부록 D.1 조합(reply×2·no_reply×1·end×1)으로 섞는다."""
    state = await helpers.reach_branch_block(client, "P00")
    assert state["screen"] == "P4"
    assert state["ss_state"] == "SS04"

    dispositions = ["reply", "reply", "no_reply", "end"]
    for branch_index, disposition in enumerate(dispositions, start=1):
        state = await helpers.complete_branch(client, branch_index, disposition)

    assert state["screen"] == "P10", "네 branch가 끝나면 cross-branch review다 (§3.1 SS05)"
    trajectories = state["data"]["branches"]
    assert len(trajectories) == 4
    assert [row["disposition"] for row in trajectories] == dispositions

    state = await helpers.advance(client, "P10")
    assert state["screen"] == "P11"

    response = await client.post("/api/debrief/confirm")
    assert response.status_code == 200
    final = response.json()
    assert final["screen"] == "DONE"
    assert final["ss_state"] == "SS07"
    assert final["status"] == "done"

    # 저장물 — branch 4개, 평정 48행, AI2·downstream은 reply branch만(§3.2 · NT-17).
    assert await _count(session, tables.Branch) == 4
    assert await _count(session, tables.Rating) == 4 * rating_items.ITEM_COUNT
    assert await _count(session, tables.SidecarEntry) == 4
    assert await _count(session, tables.Generation) == 2
    assert await _count(session, tables.DownstreamAction) == 2


async def test_cross_review_never_names_conditions(client: AsyncClient) -> None:
    """§4.10 — branch 번호로만 라벨링, construct label 비공개."""
    await helpers.reach_branch_block(client, "P00")
    for branch_index in range(1, 5):
        state = await helpers.complete_branch(client, branch_index, "end")
    serialized = str(state["data"])
    for banned in ("C1", "C2", "C3", "C4", "uptake", "elicitation"):
        assert banned not in serialized


# --------------------------------------------------------------------------- #
# NT-07 — condition·stimulus_hash 최초 저장 후 불변
# --------------------------------------------------------------------------- #


async def test_nt07_condition_and_stimulus_are_fixed_at_first_entry(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    state = await helpers.advance(client, "P4")
    first_ai1 = state["data"]["ai1"]

    branch = (
        await session.execute(select(tables.Branch).where(tables.Branch.branch_index == 1))
    ).scalars().one()
    assert branch.condition == williams_condition("P00", 1), "§3.3 결정론 매핑과 다르다"
    condition, stimulus_hash = branch.condition, branch.stimulus_hash
    assert stimulus_hash == dossier_loader.load("P00").stimulus_hash(condition)

    # 새로고침·중복 진행 요청을 반복해도 재추첨·재생성이 없다.
    for _ in range(3):
        await helpers.state(client)
        await client.post("/api/advance", json={"from_screen": "P4"})
    await session.refresh(branch)
    assert (branch.condition, branch.stimulus_hash) == (condition, stimulus_hash)
    assert (await helpers.state(client))["data"]["ai1"] == first_ai1

    # AI1 turn은 1건뿐이다 — 재진입이 자극을 다시 렌더하지 않는다.
    ai1_turns = (
        await session.execute(select(tables.Turn).where(tables.Turn.role == "ai1"))
    ).scalars().all()
    assert len(ai1_turns) == 1


async def test_nt07_four_branches_follow_the_williams_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    for branch_index in range(1, 5):
        await helpers.complete_branch(client, branch_index, "no_reply")
    branches = (
        await session.execute(select(tables.Branch).order_by(tables.Branch.branch_index))
    ).scalars().all()
    assert [b.condition for b in branches] == [williams_condition("P00", i) for i in range(1, 5)]


# --------------------------------------------------------------------------- #
# NT-08 — 새로고침·재접속 복구
# --------------------------------------------------------------------------- #


async def test_nt08_refresh_restores_the_same_screen_and_stimulus(client: AsyncClient) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    before = await helpers.state(client)
    for _ in range(3):
        after = await helpers.state(client)
        assert after == before, "새로고침이 화면·자극을 바꾼다"


async def test_nt08_rejoin_restores_the_saved_point(client: AsyncClient) -> None:
    """§3.5 재접속 — 동일 번호+코드 재입력 → 저장 지점 복원(새 세션 생성 아님)."""
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    before = await helpers.state(client)
    assert before["screen"] == "P3"

    client.cookies.clear()  # 브라우저를 닫았다 다시 연 상황
    restored = await helpers.join(client, "P00", created["access_code"])
    assert restored["restored"] is True
    assert restored["screen"] == "P3"
    assert restored["ss_state"] == before["ss_state"]


async def test_nt08_ai2_is_never_regenerated(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§8.3-4 — 새로고침 시 저장된 최종 텍스트를 재서빙한다(재생성 0건)."""
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    await client.post("/api/branch/1/user1", json={"disposition": "reply", "text": "장단점만"})
    await client.post("/api/branch/1/sidecar", json={"choice": "none"})

    first = await client.post("/api/branch/1/ai2")
    assert first.status_code == 200
    text = first.json()["data"]["ai2"]
    assert text

    for _ in range(3):
        again = await client.post("/api/branch/1/ai2")
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["data"]["ai2"] == text
        assert (await helpers.state(client))["data"]["ai2"] == text

    assert await _count(session, tables.Generation) == 1
    ai2_turns = (
        await session.execute(select(tables.Turn).where(tables.Turn.role == "ai2"))
    ).scalars().all()
    assert len(ai2_turns) == 1


async def test_nt08_rating_order_survives_refresh(client: AsyncClient) -> None:
    """문항 순서도 저장 상태다 — 새로고침이 다시 뽑지 않는다(§3.5)."""
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    await client.post("/api/branch/1/user1", json={"disposition": "end"})
    await client.post("/api/branch/1/sidecar", json={"choice": "skip"})
    first = (await helpers.state(client))["data"]["blocks"]
    for _ in range(3):
        assert (await helpers.state(client))["data"]["blocks"] == first


# --------------------------------------------------------------------------- #
# NT-09 — 중복 제출 idempotency
# --------------------------------------------------------------------------- #


async def test_nt09_duplicate_session_level_submissions(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.open_and_join(client, "P00")
    from app.assets.screen_copy import CONSENT_ITEMS

    body = {"items": {item.field: True for item in CONSENT_ITEMS}}
    first = await client.post("/api/consent", json=body)
    second = await client.post("/api/consent", json=body)
    assert first.status_code == second.status_code == 200
    assert second.json()["screen"] == "P2"

    await helpers.presurvey(client)
    count_after_first = await _count(session, tables.PresurveyResponse)
    # 같은 payload로 재제출 — 200 + 기존 레코드, 행은 늘지 않는다.
    replay = await client.post(
        "/api/presurvey", json={"responses": [{"position": 1, "value": "ph_1"}]}
    )
    assert replay.status_code == 200
    assert await _count(session, tables.PresurveyResponse) == count_after_first


async def test_nt09_duplicate_branch_level_submissions(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")

    body = {"disposition": "reply", "text": "장기 계획 말고 장단점만"}
    first = await client.post("/api/branch/1/user1", json=body)
    second = await client.post("/api/branch/1/user1", json=body)
    assert first.status_code == second.status_code == 200
    assert second.json()["replayed"] is True
    user1_turns = (
        await session.execute(select(tables.Turn).where(tables.Turn.role == "user1"))
    ).scalars().all()
    assert len(user1_turns) == 1

    sidecar_body = {"choice": "has", "free_text": "말 안 한 사정", "relevance": 5}
    assert (await client.post("/api/branch/1/sidecar", json=sidecar_body)).status_code == 200
    assert (await client.post("/api/branch/1/sidecar", json=sidecar_body)).status_code == 200
    assert await _count(session, tables.SidecarEntry) == 1

    await client.post("/api/branch/1/ai2")
    await helpers.advance(client, "P7")
    assert (
        await client.post("/api/branch/1/downstream", json={"code": "pause"})
    ).status_code == 200
    assert (
        await client.post("/api/branch/1/downstream", json={"code": "end"})
    ).status_code == 200
    assert await _count(session, tables.DownstreamAction) == 1

    assert (
        await client.post("/api/branch/1/ratings", json=helpers.ratings_payload())
    ).status_code == 200
    assert (
        await client.post("/api/branch/1/ratings", json=helpers.ratings_payload(7))
    ).status_code == 200
    assert await _count(session, tables.Rating) == rating_items.ITEM_COUNT


async def test_nt09_duplicate_advance_does_not_skip_a_screen(client: AsyncClient) -> None:
    """§3.5 — 중복 클릭이 한 단계 더 밀지 않는다."""
    await helpers.reach_branch_block(client, "P00")
    first = await helpers.advance(client, "P4")
    assert first["screen"] == "P5"
    again = await helpers.advance(client, "P4")  # 이미 P5인데 P4에서 다시 눌림
    assert again["screen"] == "P5"


# --------------------------------------------------------------------------- #
# NT-14 — 비합법 전이 요청 거부
# --------------------------------------------------------------------------- #


async def test_nt14_branch_steps_cannot_be_skipped(client: AsyncClient) -> None:
    await helpers.reach_branch_block(client, "P00")

    # B0에서 곧장 User1 (AI1 표시 없이)
    assert (
        await client.post("/api/branch/1/user1", json={"disposition": "end"})
    ).status_code == 409

    await helpers.advance(client, "P4")
    # sidecar 없이 AI2 (§0.4 sidecar 배치 동결)
    assert (await client.post("/api/branch/1/ai2")).status_code == 409
    # AI2 없이 downstream (NT-14의 예시 그대로)
    assert (
        await client.post("/api/branch/1/downstream", json={"code": "pause"})
    ).status_code == 409
    # downstream 없이 평정
    assert (
        await client.post("/api/branch/1/ratings", json=helpers.ratings_payload())
    ).status_code == 409

    # 아직 열리지 않은 branch
    assert (
        await client.post("/api/branch/3/user1", json={"disposition": "end"})
    ).status_code == 409


async def test_nt14_session_steps_cannot_be_skipped(client: AsyncClient) -> None:
    await helpers.open_and_join(client, "P00")
    assert (await client.post("/api/checkpoint/confirm")).status_code == 409
    assert (
        await client.post("/api/presurvey", json={"responses": []})
    ).status_code == 409
    await helpers.consent(client)
    assert (await client.post("/api/checkpoint/confirm")).status_code == 409


async def test_nt14_submissions_after_completion_are_refused(client: AsyncClient) -> None:
    await helpers.reach_branch_block(client, "P00")
    for branch_index in range(1, 5):
        await helpers.complete_branch(client, branch_index, "no_reply")
    await helpers.advance(client, "P10")
    await client.post("/api/debrief/confirm")
    assert (await client.post("/api/checkpoint/confirm")).status_code == 409
    assert (
        await client.post("/api/branch/4/ratings", json=helpers.ratings_payload())
    ).status_code == 409


async def test_no_session_cookie_is_401(client: AsyncClient) -> None:
    client.cookies.clear()
    assert (await client.get("/api/state")).status_code == 401


# --------------------------------------------------------------------------- #
# NT-17 — no_reply/end branch에 AI2·downstream 부재
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("disposition", ["no_reply", "end"])
async def test_nt17_no_ai2_or_downstream_for_non_reply(
    client: AsyncClient, session: AsyncSession, disposition: str
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    await client.post("/api/branch/1/user1", json={"disposition": disposition})
    state = (await client.post("/api/branch/1/sidecar", json={"choice": "none"})).json()

    # sidecar 다음이 곧 평정이다 — P7·P8을 지나지 않는다.
    assert state["screen"] == "P9"
    assert state["b_state"] == "B6"
    assert state["has_ai2"] is False

    assert (await client.post("/api/branch/1/ai2")).status_code == 409
    assert (
        await client.post("/api/branch/1/downstream", json={"code": "pause"})
    ).status_code == 409
    assert await _count(session, tables.Generation) == 0
    assert await _count(session, tables.LlmCall) == 0

    # 그래도 12문항 2블록은 동일하게 제시된다(D-22).
    blocks = state["data"]["blocks"]
    assert sum(len(block["items"]) for block in blocks) == rating_items.ITEM_COUNT


async def test_reply_branch_requires_text(client: AsyncClient) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    assert (
        await client.post("/api/branch/1/user1", json={"disposition": "reply", "text": "   "})
    ).status_code == 400
    assert (
        await client.post(
            "/api/branch/1/user1", json={"disposition": "no_reply", "text": "본문"}
        )
    ).status_code == 400


# --------------------------------------------------------------------------- #
# NT-18 — 평정 2블록 제시·저장
# --------------------------------------------------------------------------- #


async def test_nt18_two_blocks_with_ai1_anchor_and_within_block_randomization(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    ai1 = (await helpers.state(client))["data"]["ai1"]
    await client.post("/api/branch/1/user1", json={"disposition": "no_reply"})
    await client.post("/api/branch/1/sidecar", json={"choice": "none"})

    data = (await helpers.state(client))["data"]
    blocks = data["blocks"]
    assert [block["block"] for block in blocks] == [1, 2], "블록 순서는 1→2 고정(§4.9)"
    assert blocks[0]["ai1_card"] == ai1, "블록 1은 해당 branch AI1 카드를 앵커로 단다"
    assert blocks[1]["ai1_card"] is None, "블록 2에는 카드가 없다"
    assert len(blocks[0]["items"]) == 2
    assert len(blocks[1]["items"]) == 10
    assert data["scale"] == {
        "min": 1,
        "max": 7,
        "min_label": "전혀 그렇지 않다",
        "max_label": "매우 그렇다",
    }

    # 화면에는 위치와 문항 원문만 — 변수명(구성개념 라벨)은 내려가지 않는다.
    for block in blocks:
        for item in block["items"]:
            assert set(item) == {"position", "text"}
    positions = [item["position"] for block in blocks for item in block["items"]]
    assert sorted(positions) == list(range(1, 13))

    await client.post("/api/branch/1/ratings", json=helpers.ratings_payload(6))
    rows = (
        await session.execute(select(tables.Rating).order_by(tables.Rating.display_order))
    ).scalars().all()
    assert len(rows) == 12
    assert {row.block for row in rows} == {1, 2}
    assert sorted(row.display_order for row in rows) == list(range(1, 13))
    assert {row.item_id for row in rows} == set(rating_items.ITEMS_BY_ID)
    # 블록 1은 문항 1·2, 블록 2는 나머지 — 종결 유형과 무관하다(D-22).
    block1 = {row.item_id for row in rows if row.block == 1}
    assert block1 == {"recognition", "substantive_uptake"}
    assert all(1 <= row.value <= 7 for row in rows)


async def test_nt18_partial_ratings_are_refused(client: AsyncClient) -> None:
    await helpers.reach_branch_block(client, "P00")
    await helpers.advance(client, "P4")
    await client.post("/api/branch/1/user1", json={"disposition": "end"})
    await client.post("/api/branch/1/sidecar", json={"choice": "none"})
    partial = {"items": [{"position": 1, "value": 4}]}
    assert (await client.post("/api/branch/1/ratings", json=partial)).status_code == 400
    out_of_range = {"items": [{"position": p, "value": 9} for p in range(1, 13)]}
    assert (await client.post("/api/branch/1/ratings", json=out_of_range)).status_code == 422


async def test_rating_order_differs_across_branches(client: AsyncClient) -> None:
    """블록 내 무작위가 실제로 섞이는지 — 네 branch의 순서가 전부 같으면 무작위가 아니다."""
    orders = set()
    for seed in range(8):
        presented = rating_items.presentation_order("seed", seed)
        orders.add(tuple(entry.item.item_id for entry in presented))
    assert len(orders) > 1


# --------------------------------------------------------------------------- #
# NT-12 · NT-27 — 세션 1개 불변식, 코드 TTL·재발급
# --------------------------------------------------------------------------- #


async def test_nt12_one_session_per_participant(client: AsyncClient) -> None:
    await helpers.create_session(client, "P01")
    duplicate = await client.post(
        "/admin/sessions", json={"participant_no": "P01"}, auth=helpers.ADMIN_AUTH
    )
    assert duplicate.status_code == 409


async def test_nt12_p00_is_unlimited(client: AsyncClient) -> None:
    """§2.5 — P00은 QA 전용이므로 세션 수 제한이 없다."""
    first = await helpers.create_session(client, "P00")
    second = await helpers.create_session(client, "P00")
    assert first["session_id"] != second["session_id"]


async def test_participant_row_stores_sequence_index(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§8.1 — sequence_index는 생성 시 결정론 산출·저장(§3.3)."""
    created = await helpers.create_session(client, "P03")
    participant = await session.get(tables.Participant, "P03")
    assert participant is not None
    assert participant.sequence_index == 3 == created["sequence_index"]
    assert participant.is_test is False
    assert (await session.get(tables.Participant, "P03")).dossier_version


async def test_nt27_expired_code_is_refused_then_reissued(
    client: AsyncClient, session: AsyncSession
) -> None:
    created = await helpers.create_session(client, "P00")
    row = await _session_row(session, "P00")
    row.code_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    expired = await client.post(
        "/api/join", json={"participant_no": "P00", "access_code": created["access_code"]}
    )
    assert expired.status_code == 401
    assert "연구자에게 문의" in expired.json()["detail"]

    reissued = await client.post(
        f"/admin/sessions/{created['session_id']}/code", auth=helpers.ADMIN_AUTH
    )
    assert reissued.status_code == 200
    assert reissued.json()["session_id"] == created["session_id"], "재발급은 동일 세션 바인딩"
    assert reissued.json()["access_code"] != created["access_code"]

    state = await helpers.join(client, "P00", reissued.json()["access_code"])
    assert state["screen"] == "P1"
    # 새 세션이 생기지 않았다.
    assert (
        await session.execute(
            select(func.count()).select_from(tables.Session).where(
                tables.Session.participant_no == "P00"
            )
        )
    ).scalar_one() == 1

    # 옛 코드는 더 이상 통하지 않는다.
    client.cookies.clear()
    stale = await client.post(
        "/api/join", json={"participant_no": "P00", "access_code": created["access_code"]}
    )
    assert stale.status_code == 401


async def test_wrong_code_is_refused_and_throttled(client: AsyncClient) -> None:
    """§4.0 — 실패 5회 시 30초 지연."""
    await helpers.create_session(client, "P00")
    for _ in range(4):
        response = await client.post(
            "/api/join", json={"participant_no": "P00", "access_code": "ZZZZZZ"}
        )
        assert response.status_code == 401
    blocked = await client.post(
        "/api/join", json={"participant_no": "P00", "access_code": "ZZZZZZ"}
    )
    assert blocked.status_code == 401
    after_limit = await client.post(
        "/api/join", json={"participant_no": "P00", "access_code": "ZZZZZZ"}
    )
    assert after_limit.status_code == 429
    assert 0 < int(after_limit.headers["retry-after"]) <= 30


async def test_admin_requires_credentials(client: AsyncClient) -> None:
    """§2.7 — 콘솔은 Basic auth 뒤에 있다."""
    assert (await client.post("/admin/sessions", json={"participant_no": "P00"})).status_code == 401
    assert (
        await client.post(
            "/admin/sessions", json={"participant_no": "P00"}, auth=("wrong", "wrong")
        )
    ).status_code == 401


async def test_code_issue_is_audited(client: AsyncClient, session: AsyncSession) -> None:
    """§2.7 — 전 콘솔 행위가 audit에 남는다."""
    await helpers.create_session(client, "P00")
    rows = (await session.execute(select(tables.AuditLog))).scalars().all()
    assert [row.action for row in rows] == ["code_issue"]
    assert rows[0].actor == helpers.ADMIN_USER
