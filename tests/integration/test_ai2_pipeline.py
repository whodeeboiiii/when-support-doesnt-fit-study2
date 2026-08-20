"""AI2 파이프라인 (구현명세서 §6.1 · §6.4 · §6.5 · §9.1 · §8.4 · NT-15·16·25).

    payload 조립 → 생성(MAIN) → 규칙 검사(R-1·R-3·R-4) → checker(VALIDATOR)
    → 위반 시 재생성 1회 → 재위반 시 neutral_fallback

세 가지를 본다.
1. **사다리의 끝은 언제나 표시 가능한 텍스트다**(§9.1 dead-end 금지). 어느 경로로 가도
   참가자 화면에는 {정상 | 재생성 통과 | fallback} 중 하나가 뜬다.
2. **경로가 사후 복원된다**(NT-15). `generations`·`llm_calls`만으로 무엇이 왜 기각됐는지
   말할 수 있어야 한다.
3. **R-2는 위반이 아니다**(§6.4 v2 개정). 대안 segment overlap은 `alt_overlap`에 기록만
   되고 재생성을 부르지 않는다 — 이걸 위반으로 승격시키면 정상 생성물이 fallback으로
   떨어지고 조작 자체가 바뀐다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader
from app.llm import prompts
from app.llm.fake_llm import fixture_token
from app.models import tables
from app.security import fernet
from tests import helpers


async def _generations(db: AsyncSession) -> list[tables.Generation]:
    result = await db.execute(
        select(tables.Generation).order_by(tables.Generation.attempt, tables.Generation.created_at)
    )
    return list(result.scalars().all())


async def _final(db: AsyncSession) -> tables.Generation:
    rows = [row for row in await _generations(db) if row.final]
    assert len(rows) == 1, f"final 생성물은 정확히 1행이어야 한다 (실제 {len(rows)})"
    return rows[0]


async def _run_focal_ai2(client: AsyncClient, user1: str) -> None:
    await helpers.reach_focal(client)
    response = await client.post("/api/focal/user1", json={"text": user1})
    assert response.status_code == 200, response.text
    await client.post("/api/focal/sidecar", json={"has_more": False})
    response = await client.post("/api/focal/ai2")
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# 정상 경로
# --------------------------------------------------------------------------- #


async def test_clean_generation_is_final_on_first_attempt(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§6.1 — 규칙·checker를 통과하면 attempt 1이 그대로 final이다."""
    await _run_focal_ai2(client, "장기 계획 말고 비교만 해줘")

    rows = await _generations(session)
    assert len(rows) == 1
    final = rows[0]
    assert (final.attempt, final.final, final.fallback_used) == (1, True, False)
    assert final.rule_violations == []
    assert final.checker_skipped is False
    assert final.alt_overlap == []

    # 호출 1건 = `llm_calls` 1행 (§8.4).
    calls = (await session.execute(select(tables.LlmCall))).scalars().all()
    assert {row.role for row in calls} == {"main", "validator"}
    assert all(row.prompt_hash for row in calls), "prompt_hash가 비어 있다 (§8.4 재현성)"


async def test_ai2_turn_is_stored_encrypted_and_linked(
    client: AsyncClient, session: AsyncSession
) -> None:
    """§8.1 — `turns.ai2`가 🔒로 저장되고 `generation_id`로 이어진다."""
    await _run_focal_ai2(client, "비교만 해줘")
    turn = (
        await session.execute(select(tables.Turn).where(tables.Turn.role == "ai2"))
    ).scalars().one()
    final = await _final(session)
    assert turn.generation_id == final.id
    assert fernet.decrypt(turn.text) == fernet.decrypt(final.output_text)
    assert b"\x00" not in (turn.text or b""), "평문 저장 흔적"


# --------------------------------------------------------------------------- #
# 규칙 위반 → 재생성 → fallback (§6.1 사다리)
# --------------------------------------------------------------------------- #


async def test_rule_violation_triggers_one_regeneration(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§0.5 — 재생성 **최대 1회**. 첫 초안이 R-3을 어기고 두 번째가 통과하는 경우."""
    llm.stub(
        prompts.AI2_PROMPT_KEY,
        "어느 쪽이 필요하세요? 아니면 다른 방식이 좋을까요?",  # R-3 (질문 2개)
        "말씀하신 범위 안에서 비교를 이어가겠습니다.",  # 통과
    )
    await _run_focal_ai2(client, "비교만 해줘")

    rows = await _generations(session)
    assert [row.attempt for row in rows] == [1, 2]
    assert rows[0].final is False
    assert [item["rule"] for item in rows[0].rule_violations] == ["R-3"]
    assert rows[1].final is True and rows[1].fallback_used is False


async def test_repeated_violation_falls_back(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§6.5 — 재생성 후에도 위반이면 참가자별 `neutral_fallback`으로 수렴한다(§9.1)."""
    llm.stub(prompts.AI2_PROMPT_KEY, "어느 쪽인가요? 아니면 다른 쪽인가요?")
    await _run_focal_ai2(client, "비교만 해줘")

    final = await _final(session)
    assert final.fallback_used is True
    expected = dossier_loader.load("P00").stimulus.neutral_fallback
    assert fernet.decrypt(final.output_text) == expected

    # fallback은 **별도 행**이다 — 기각된 초안 원문이 덮어써지지 않는다.
    rows = await _generations(session)
    assert len(rows) == 3, "attempt 1·2 + fallback 행"
    drafts = [fernet.decrypt(row.output_text) for row in rows if not row.fallback_used]
    assert all(draft != expected for draft in drafts)


async def test_call_failure_converges_to_fallback(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§9.1 — AI2 호출 실패의 종착지도 fallback이다. **참가자 화면은 막다르지 않는다**."""
    llm.fail(prompts.AI2_PROMPT_KEY, times=4)
    await _run_focal_ai2(client, "비교만 해줘")

    final = await _final(session)
    assert final.fallback_used is True
    assert any(
        item.get("rule") == "call_failed" for item in (final.rule_violations or [])
    ), "장애 경로가 기록되지 않았다"

    state = await helpers.state(client)
    assert state["data"]["ai2"], "표시할 텍스트가 없다 (§9.1 dead-end 금지)"


async def test_checker_failure_is_absorbed_as_skipped(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§9.1 — checker 실패는 `checker_skipped`로 흡수하고 규칙 계층만으로 판정한다.

    판정 불능을 위반으로 취급하면 정상 생성물이 fallback으로 떨어진다.
    """
    llm.fail(prompts.CHECKER_PROMPT_KEY, times=4)
    await _run_focal_ai2(client, "비교만 해줘")

    final = await _final(session)
    assert final.checker_skipped is True
    assert final.fallback_used is False, "checker 불능이 fallback을 불렀다"
    assert final.rule_violations == []


async def test_checker_violation_triggers_regeneration(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """부록 A.2 — checker 3유형. fixture 트리거로 `expansion`을 재현한다(부록 A.6)."""
    await _run_focal_ai2(client, f"비교만 해줘 {fixture_token('expansion')}")

    rows = await _generations(session)
    assert len(rows) >= 2, "checker 위반이 재생성을 부르지 않았다"
    first = rows[0]
    assert first.checker_result is not None
    assert "expansion" in {
        item.get("type") for item in first.checker_result.get("violations", [])
    }


async def test_rule_violation_skips_the_checker(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§6.1 (NS3 결정 승계) — 규칙 위반이 이미 있으면 checker를 부르지 않는다.

    판정 결과(재생성)가 같고 시간 예산을 아낀다. 기록에서는 `rule_violations`가 비어 있지
    않고 `checker_result=null`인 상태로 구분된다.
    """
    llm.stub(prompts.AI2_PROMPT_KEY, "어느 쪽인가요? 다른 쪽인가요?", "정상 응답입니다.")
    await _run_focal_ai2(client, "비교만 해줘")

    rows = await _generations(session)
    assert rows[0].rule_violations and rows[0].checker_result is None
    # checker는 두 번째 시도에서만 불린다.
    assert llm.call_count(prompts.CHECKER_PROMPT_KEY) == 1


# --------------------------------------------------------------------------- #
# §6.4 R-2 — alt_overlap은 **위반이 아니다**
# --------------------------------------------------------------------------- #


async def test_alt_segment_overlap_is_flagged_not_violated(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§6.4 R-2 (v2 개정) — 대안 segment가 통째로 나와도 재생성을 부르지 않는다.

    "AI2가 정책상 스스로 유사 질문을 할 수 있으므로 위반으로 보지 않는다"가 명세의 근거다.
    """
    dossier = dossier_loader.load("P00")
    # P00의 focal은 C1(= r)이므로 u는 대안에만 있는 segment다.
    llm.stub(prompts.AI2_PROMPT_KEY, dossier.stimulus.u)

    await _run_focal_ai2(client, "비교만 해줘")

    final = await _final(session)
    assert final.fallback_used is False, "overlap이 fallback을 불렀다 — 위반으로 승격됐다"
    assert final.rule_violations == [], "overlap이 rule_violations에 들어갔다"
    assert final.alt_overlap == [{"condition": "C3", "segment": "u"}] or any(
        item["segment"] == "u" for item in final.alt_overlap
    ), f"overlap이 기록되지 않았다: {final.alt_overlap}"
    # 재생성이 없었다 — 생성 행이 1건이다.
    assert len(await _generations(session)) == 1


async def test_partial_overlap_is_not_flagged(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§6.4 — **전문 일치**만 본다. 문장 몇 개가 닮는 것은 같은 정책의 정상 결과다."""
    dossier = dossier_loader.load("P00")
    llm.stub(prompts.AI2_PROMPT_KEY, dossier.stimulus.u[:20] + " 이어서 정리하겠습니다.")
    await _run_focal_ai2(client, "비교만 해줘")

    final = await _final(session)
    assert final.alt_overlap == []


# --------------------------------------------------------------------------- #
# R-1 — 금지 문자열 대조 (§6.4)
# --------------------------------------------------------------------------- #


async def test_sidecar_leak_in_output_is_a_violation(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """R-1 — sidecar 문자열이 출력에 등장하면 위반이다(§1.2 방화벽의 런타임 검출)."""
    secret = "사실은 이직 쪽으로 이미 기울어 있었다"
    llm.stub(prompts.AI2_PROMPT_KEY, f"말씀하신 {secret}를 전제로 이어가겠습니다.")

    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post(
        "/api/focal/sidecar",
        json={"has_more": True, "free_text": secret, "provenance": "preexisting"},
    )
    await client.post("/api/focal/ai2")

    rows = await _generations(session)
    assert any(
        item["rule"] == "R-1" for row in rows for item in (row.rule_violations or [])
    ), "sidecar 누출이 R-1로 잡히지 않았다"
    # 위반 기록에는 **라벨만** 남는다 — 원문이 새 누출 경로가 되면 안 된다(§2.9).
    for row in rows:
        for item in row.rule_violations or []:
            assert secret not in item["detail"]


async def test_pre_edit_original_leak_is_a_violation(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """R-1 (v2 신설) — **checkpoint 수정 전 원문**이 출력에 등장하면 위반이다(§6.4)."""
    original = dossier_loader.load("P00").ai_visible.problematic_ai_response
    llm.stub(prompts.AI2_PROMPT_KEY, f"앞서 {original} 그 부분을 빼겠습니다.")

    await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.edit_checkpoint(
        client, "problematic_ai_response", "AI가 다른 방향으로 답했습니다."
    )
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    rows = await _generations(session)
    assert any(
        item["rule"] == "R-1" for row in rows for item in (row.rule_violations or [])
    ), "수정 전 원문 누출이 R-1로 잡히지 않았다"


async def test_effective_checkpoint_echo_is_not_a_violation(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§6.4 R-1의 예외 — payload에 정당히 포함된 문자열은 대조에서 뺀다.

    이 예외가 없으면 수정본을 되짚는 정상 응답이 위반으로 잡힌다(수정 전 원문과 수정본은
    대부분의 문장이 겹치기 때문이다).
    """
    dossier = dossier_loader.load("P00")
    llm.stub(prompts.AI2_PROMPT_KEY, dossier.ai_visible.original_request)

    await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.edit_checkpoint(client, "situation_summary", "조금 다른 상황 요약입니다.")
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    final = await _final(session)
    assert final.fallback_used is False, "정상 응답이 fallback으로 떨어졌다 (§6.4 예외 미적용)"


# --------------------------------------------------------------------------- #
# NT-15 — audit 재구성
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("stubs", "expected"),
    [
        (["정상 응답입니다."], "clean"),
        (["어느 쪽인가요? 다른 쪽인가요?", "정상 응답입니다."], "regenerated"),
        (["어느 쪽인가요? 다른 쪽인가요?"], "fallback"),
    ],
)
async def test_path_is_reconstructible_from_generations(
    client: AsyncClient, session: AsyncSession, llm, stubs: list[str], expected: str
) -> None:
    """§8.4 · NT-15 — `generations`만으로 {정상 | 재생성 | fallback}이 복원된다."""
    llm.stub(prompts.AI2_PROMPT_KEY, *stubs)
    await _run_focal_ai2(client, "비교만 해줘")

    rows = await _generations(session)
    final = next(row for row in rows if row.final)
    if final.fallback_used:
        path = "fallback"
    elif final.attempt > 1:
        path = "regenerated"
    else:
        path = "clean"
    assert path == expected

    # 콘솔 R2·R3의 라벨과 같은 판정을 쓴다(표시용 상태 컬럼을 따로 두지 않는다).
    from app.api.admin_views import ai2_state

    row = (await session.execute(select(tables.Session))).scalars().first()
    assert ai2_state(row, rows) == expected


async def test_every_call_has_one_llm_calls_row(
    client: AsyncClient, session: AsyncSession, llm
) -> None:
    """§8.4 — 호출 1건 = 1행. 자산 버전·파라미터가 함께 남는다."""
    await _run_focal_ai2(client, "비교만 해줘")
    calls = (await session.execute(select(tables.LlmCall))).scalars().all()
    assert len(calls) == llm.call_count(prompts.AI2_PROMPT_KEY) + llm.call_count(
        prompts.CHECKER_PROMPT_KEY
    )
    for call in calls:
        assert call.request_id and call.status
        assert call.params, "생성 파라미터가 기록되지 않았다"


# --------------------------------------------------------------------------- #
# NT-25 — fixture 러너 (§10.1)
# --------------------------------------------------------------------------- #


async def test_integrity_fixture_v2_is_deterministic(session: AsyncSession) -> None:
    """§10.1 — 규칙 계층·alt_overlap·checker 블록 전부 100%."""
    from tests import fixture_runner

    report = await fixture_runner.run_integrity_fixture(session)
    breaches = report.gate_failures(fixture_runner.INTEGRITY_THRESHOLDS)
    assert breaches == [], f"fixture 미달: {breaches}\n{[f.id for f in report.failures()]}"
    assert set(report.blocks) == {"R", "A", "C"}, "블록 A(alt_overlap)가 빠졌다"
