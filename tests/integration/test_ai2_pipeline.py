"""AI2 파이프라인 — NT-11 · NT-15 · NT-16 + §9.1 오류 경로 (구현명세서 §6 · §8.3 · §9.1).

세 가지를 본다.

1. **시간 순서**(NT-16 · §8.3): sidecar 제출 **전에** AI2가 생성되는 경로가 존재하지 않는다.
   참가자에게 "이 내용은 AI에게 전달되지 않습니다"라고 고지하는 문안(§4.6 [정본])의 진실성이
   여기 걸려 있다 — 정보 경계뿐 아니라 **시간 순서로도** 보장한다.
2. **normalization 저장**(NT-11): 전 조건 동일 규칙 + raw/normalized/matched_pattern 저장.
3. **audit 재구성**(NT-15): `generations`·`llm_calls`만으로 {정상 | 재생성 통과 | fallback}
   경로가 복원된다. 참가자 화면에서는 구분되지 않지만(§4.7) 기록에서는 구분되어야 한다.

§9.1의 세 경로(AI2 호출 실패 · checker 실패 · 재생성 후에도 위반)도 여기서 끝까지 태운다.
어느 경로든 **표시 가능한 텍스트**로 끝나야 한다(dead-end 금지).
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader
from app.core.williams import condition as williams_condition
from app.llm.fake_llm import FakeLLM
from app.llm.prompts import AI2_PROMPT_KEY, CHECKER_PROMPT_KEY
from app.models import tables
from app.security import fernet
from tests import helpers

REFERRING_USER1 = "응 그렇게 해줘"


async def _reach_sidecar(client: AsyncClient, index: int, text: str = REFERRING_USER1) -> None:
    await helpers.advance(client, "P4")
    response = await client.post(
        f"/api/branch/{index}/user1", json={"disposition": "reply", "text": text}
    )
    assert response.status_code == 200


async def _reach_ai2(client: AsyncClient, index: int, text: str = REFERRING_USER1) -> None:
    await _reach_sidecar(client, index, text)
    await client.post(f"/api/branch/{index}/sidecar", json={"choice": "none"})


async def _finish_branch(client: AsyncClient, index: int) -> None:
    await helpers.advance(client, "P7")
    await client.post(f"/api/branch/{index}/downstream", json={"code": "pause"})
    await client.post(f"/api/branch/{index}/ratings", json=helpers.ratings_payload())


async def _generations(db: AsyncSession, branch_index: int = 1) -> list[tables.Generation]:
    result = await db.execute(
        select(tables.Generation)
        .join(tables.Branch, tables.Generation.branch_id == tables.Branch.id)
        .where(tables.Branch.branch_index == branch_index)
        .order_by(tables.Generation.attempt, tables.Generation.fallback_used)
    )
    return list(result.scalars().all())


async def reconstruct_path(db: AsyncSession, branch_index: int = 1) -> dict[str, Any]:
    """NT-15 — **`generations`·`llm_calls`만으로** 최종 표시 텍스트의 경로를 복원한다.

    참가자 응답·화면 상태를 보지 않는다. 이 함수가 성립한다는 것이 곧 "논문의 generation
    integrity 보고를 이 필드만으로 재구성할 수 있다"는 §8.4의 요구다.
    """
    generations = await _generations(db, branch_index)
    finals = [row for row in generations if row.final]
    assert len(finals) == 1, f"final 행은 정확히 1건이어야 한다 (실제 {len(finals)})"
    final = finals[0]

    calls = list(
        (
            await db.execute(
                select(tables.LlmCall).where(
                    tables.LlmCall.generation_id.in_([row.id for row in generations])
                )
            )
        )
        .scalars()
        .all()
    )
    drafts = [row for row in generations if not row.fallback_used]
    if final.fallback_used:
        path = "fallback"
    elif final.attempt > 1:
        path = "regenerated"
    else:
        path = "clean"
    return {
        "path": path,
        "attempts": len(drafts),
        "final_attempt": final.attempt,
        "checker_skipped": final.checker_skipped,
        "violations": [item.get("rule") for item in (final.rule_violations or [])],
        "main_calls": sum(1 for call in calls if call.role == "main"),
        "validator_calls": sum(1 for call in calls if call.role == "validator"),
        "call_errors": sum(1 for call in calls if call.status != "ok"),
        "text": fernet.decrypt(final.output_text) if final.output_text else None,
    }


# --------------------------------------------------------------------------- #
# NT-16 — sidecar 제출 전 AI2 호출 0건
# --------------------------------------------------------------------------- #


async def test_nt16_no_ai2_call_before_sidecar(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await _reach_sidecar(client, 1)

    # User1은 저장·정규화까지 끝났지만(§8.3-1) 모델은 아직 한 번도 불리지 않았다.
    assert llm.call_count(AI2_PROMPT_KEY) == 0
    assert (await client.post("/api/branch/1/ai2")).status_code == 409
    assert llm.call_count(AI2_PROMPT_KEY) == 0
    assert (
        await session.execute(select(tables.Generation))
    ).scalars().all() == []

    await client.post("/api/branch/1/sidecar", json={"choice": "none"})
    await client.post("/api/branch/1/ai2")
    assert llm.call_count(AI2_PROMPT_KEY) == 1


async def test_nt16_sidecar_row_exists_before_the_first_call(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """시간 순서를 저장물로도 확인한다 — sidecar 행이 generations보다 먼저 존재한다."""
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    sidecar = (await session.execute(select(tables.SidecarEntry))).scalars().one()
    assert sidecar is not None
    await client.post("/api/branch/1/ai2")
    assert llm.call_count(AI2_PROMPT_KEY) == 1


# --------------------------------------------------------------------------- #
# NT-11 — normalization 전 조건 동일 + 저장
# --------------------------------------------------------------------------- #


async def test_nt11_normalization_is_stored_with_raw_and_normalized(
    client: AsyncClient, session: AsyncSession
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)

    turn = (
        await session.execute(select(tables.Turn).where(tables.Turn.role == "user1"))
    ).scalars().one()
    row = (await session.execute(select(tables.Normalization))).scalars().one()

    assert fernet.decrypt(turn.text) == REFERRING_USER1, "원문은 그대로 보존된다"
    normalized = fernet.decrypt(turn.text_normalized)
    proposition = dossier_loader.load("P00").derivation.referent_map[0].proposition
    assert proposition in normalized, "지시 대상이 복원되어야 한다"
    assert REFERRING_USER1 in normalized, "원문 병기(부록 A.3)"
    assert row.applied is True
    assert row.matched_pattern_id == "NP-01"
    assert row.referent_id == "R-01"


async def test_nt11_same_rule_in_every_condition(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§6.4 — 전 조건 동일 규칙. 네 branch(=네 조건)에서 같은 입력은 같은 판정이다."""
    await helpers.reach_branch_block(client, "P00")
    for index in range(1, 5):
        await _reach_ai2(client, index)
        await client.post(f"/api/branch/{index}/ai2")
        await _finish_branch(client, index)

    rows = (
        await session.execute(
            select(tables.Normalization, tables.Branch.condition).join(
                tables.Branch, tables.Normalization.branch_id == tables.Branch.id
            )
        )
    ).all()
    assert len(rows) == 4
    conditions = {condition for _row, condition in rows}
    assert conditions == {williams_condition("P00", index) for index in range(1, 5)}
    assert {(row.applied, row.matched_pattern_id, row.referent_id) for row, _ in rows} == {
        (True, "NP-01", "R-01")
    }


async def test_normalization_result_reaches_the_payload(
    client: AsyncClient, llm: FakeLLM
) -> None:
    """§6.2 ③ — payload에 실리는 것은 **정규화본**이다."""
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    await client.post("/api/branch/1/ai2")

    proposition = dossier_loader.load("P00").derivation.referent_map[0].proposition
    payload = llm.sent_texts(AI2_PROMPT_KEY)[0]
    assert proposition in payload


# --------------------------------------------------------------------------- #
# NT-15 — audit 재구성 (§8.4)
# --------------------------------------------------------------------------- #


async def test_nt15_clean_path(client: AsyncClient, session: AsyncSession) -> None:
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    await client.post("/api/branch/1/ai2")

    record = await reconstruct_path(session)
    assert record["path"] == "clean"
    assert (record["attempts"], record["final_attempt"]) == (1, 1)
    assert (record["main_calls"], record["validator_calls"]) == (1, 1)
    assert record["violations"] == []
    assert record["checker_skipped"] is False


async def test_nt15_regenerated_path(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """§6.5 — 위반 1회 → 같은 정책으로 재생성 → 통과."""
    llm.stub(
        AI2_PROMPT_KEY,
        "어느 쪽이 더 필요하세요? 아니면 다른 방식이 좋을까요?",  # R-3 위반(질문 2개)
        "말씀하신 범위 안에서 이어가겠습니다.",
    )
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    await client.post("/api/branch/1/ai2")

    record = await reconstruct_path(session)
    assert record["path"] == "regenerated"
    assert (record["attempts"], record["final_attempt"]) == (2, 2)
    assert record["main_calls"] == 2
    assert record["text"] == "말씀하신 범위 안에서 이어가겠습니다."

    rejected = [row for row in await _generations(session) if not row.final]
    assert [item["rule"] for item in rejected[0].rule_violations] == ["R-3"]
    assert rejected[0].output_text is not None, "기각된 초안 원문이 남아야 한다"


async def test_nt15_fallback_after_second_violation(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """§9.1 — 재생성 후에도 위반 → neutral_fallback + violation 기록."""
    llm.stub(AI2_PROMPT_KEY, "어느 쪽이세요? 아니면 다른 쪽일까요?")  # 매번 R-3 위반
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    response = await client.post("/api/branch/1/ai2")
    assert response.status_code == 200

    record = await reconstruct_path(session)
    assert record["path"] == "fallback"
    assert record["attempts"] == 2, "재생성까지 시도한 뒤에 fallback이다"
    assert record["main_calls"] == 2
    assert record["violations"] == ["R-3"]
    assert record["text"] == dossier_loader.load("P00").derivation.neutral_fallback
    # 참가자 화면에도 그 텍스트가 그대로 뜬다(§4.7 — 경로는 구분되지 않는다).
    assert (await helpers.state(client))["data"]["ai2"] == record["text"]


async def test_nt15_fallback_after_call_failure(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """§9.1 — AI2 timeout·API 오류 → 동일 request id 1회 retry → 실패 시 fallback."""
    llm.fail(AI2_PROMPT_KEY)
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    response = await client.post("/api/branch/1/ai2")
    assert response.status_code == 200

    record = await reconstruct_path(session)
    assert record["path"] == "fallback"
    assert record["attempts"] == 1, "호출 실패는 재생성 대상이 아니다 — 이미 재시도했다"
    assert record["call_errors"] == 1
    assert record["violations"] == ["call_failed"]
    assert record["text"] == dossier_loader.load("P00").derivation.neutral_fallback


async def test_retry_reuses_the_same_request_id(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """§9.1 — "동일 request id 1회 retry". 재시도가 새 논리 요청이 되지 않는다."""
    llm.fail(AI2_PROMPT_KEY)
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    await client.post("/api/branch/1/ai2")

    request_ids = {call.request_id for call in llm.calls if call.prompt_key == AI2_PROMPT_KEY}
    assert len(request_ids) == 1, "재시도가 request id를 바꿨다"
    rows = (await session.execute(select(tables.LlmCall))).scalars().all()
    assert len([row for row in rows if row.role == "main"]) == 1, "호출 1건 = llm_calls 1행"


async def test_checker_failure_is_recorded_and_does_not_block(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """§9.1 — checker timeout·파싱 실패 → 규칙 계층만으로 판정 + `checker_skipped`."""
    llm.fail(CHECKER_PROMPT_KEY)
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    response = await client.post("/api/branch/1/ai2")
    assert response.status_code == 200

    record = await reconstruct_path(session)
    assert record["path"] == "clean", "checker 불능이 정상 생성물을 fallback으로 떨어뜨리지 않는다"
    assert record["checker_skipped"] is True
    assert record["validator_calls"] == 1


async def test_checker_violation_triggers_regeneration(
    client: AsyncClient, session: AsyncSession, llm: FakeLLM
) -> None:
    """§6.5 — 규칙은 통과했지만 checker가 잡은 경우에도 재생성 1회."""
    from app.llm import fake_llm

    llm.stub(
        AI2_PROMPT_KEY,
        fake_llm.FIXTURE_DRAFTS["expansion"],  # checker가 expansion으로 잡는다
        "말씀하신 범위 안에서 이어가겠습니다.",
    )
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    await client.post("/api/branch/1/ai2")

    record = await reconstruct_path(session)
    assert record["path"] == "regenerated"
    rejected = [row for row in await _generations(session) if not row.final][0]
    assert rejected.rule_violations == []
    assert rejected.checker_result["violations"][0]["type"] == "expansion"


async def test_regeneration_feedback_carries_types_not_spans(
    client: AsyncClient, llm: FakeLLM
) -> None:
    """§6.5 재생성 피드백에 위반 **유형만** 실린다 — span에는 금지 문자열이 들어 있을 수 있다."""
    llm.stub(AI2_PROMPT_KEY, "어느 쪽이세요? 아니면 다른 쪽일까요?")
    await helpers.reach_branch_block(client, "P00")
    await _reach_sidecar(client, 1)
    await client.post(
        "/api/branch/1/sidecar",
        json={"choice": "has", "free_text": "비공개기록에타", "relevance": 5},
    )
    await client.post("/api/branch/1/ai2")

    second = llm.sent_texts(AI2_PROMPT_KEY)[1]
    assert "R-3" in second, "재생성 요청에 위반 유형이 실려야 한다"
    assert "비공개기록에타" not in second


async def test_audit_records_asset_versions(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§8.4 — 자산 버전·hash가 호출 기록에 남아야 재현이 가능하다."""
    await helpers.reach_branch_block(client, "P00")
    await _reach_ai2(client, 1)
    await client.post("/api/branch/1/ai2")

    call = (
        await session.execute(select(tables.LlmCall).where(tables.LlmCall.role == "main"))
    ).scalars().one()
    assert call.prompt_hash and len(call.prompt_hash) == 64
    assert call.params["prompt_config_version"] == "prompt_config_v1"
    assert call.params["normalization_patterns_version"] == "normalization_patterns_v1"
    assert call.params["temperature"] == 0.4
    assert call.request_id
