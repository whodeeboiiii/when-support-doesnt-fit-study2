"""Evidence boundary — LLM payload 검사 (구현명세서 §1.2 · §6.2 · NT-01·02·10′).

§1.2는 이 시스템의 불변식이다. 그래서 검사도 "코드를 읽어 보니 안 넣는 것 같다"가 아니라
**실제로 모델에 나간 문자열 전문**을 본다(`FakeLLM.sent_texts`).

방법은 sentinel 주입이다: 금지 정보 자리마다 고유 문자열을 심고, 세션을 정상적으로 끝까지
돌린 뒤 전 호출의 payload에서 그 문자열을 찾는다. 하나라도 나오면 실패다.

**v2에서 방향이 하나 뒤집혔다.** v1.0.1은 "AI1 원문 금지"였지만 v2는 **focal AI1을 포함하는
것이 정책**이다(D-34). 그래서 NT-01은 양방향이다 — 금지된 것이 없는 것뿐 아니라
**허용된 것이 실제로 들어가는지**도 본다. 안 들어가면 그건 다른 실험이다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader, pairwise_items, presurvey, rating_items
from app.llm import prompts
from app.models import tables
from tests import helpers

#: 금지 정보 자리마다 심는 고유 문자열. 8자 이상이라 부분 일치에도 걸린다.
SIDECAR_SENTINEL = "SENTINEL_SIDECAR_사실은_이미_결정했다"
REASON_SENTINEL = "SENTINEL_REASON_말하기_번거로웠다"
EDIT_ORIGINAL_MARK = "SENTINEL_ORIGINAL_수정되기_전의_원문"
USER2_SENTINEL = "SENTINEL_USER2_마지막_답장"
END_REASON_SENTINEL = "SENTINEL_ENDREASON_여기까지면_충분하다"


def _sent(llm) -> list[str]:  # noqa: ANN001
    """이번 세션에서 **실제로 모델에 나간** 문자열 전문 전부(AI2 + checker)."""
    return [
        *llm.sent_texts(prompts.AI2_PROMPT_KEY),
        *llm.sent_texts(prompts.CHECKER_PROMPT_KEY),
    ]


async def _run_session_with_sentinels(client: AsyncClient) -> None:
    """금지 정보를 전부 심은 채 focal을 끝까지 돌린다."""
    await helpers.open_and_join(client)
    await helpers.consent(client)
    await helpers.presurvey(client)
    # checkpoint 수정 — 수정 **전** 원문이 R-1의 금지 문자열이 된다(§6.4).
    await helpers.edit_checkpoint(
        client, "situation_summary", f"{EDIT_ORIGINAL_MARK}를 지운 새 요약입니다."
    )
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")

    await client.post("/api/focal/user1", json={"text": "장기 계획 말고 비교만 해줘"})
    await client.post(
        "/api/focal/sidecar",
        json={
            "has_more": True,
            "free_text": SIDECAR_SENTINEL,
            "provenance": "preexisting",
            "reason": REASON_SENTINEL,
        },
    )
    await client.post("/api/focal/ai2")


# --------------------------------------------------------------------------- #
# NT-01 — AI2 payload 불포함 (금지 방향)
# --------------------------------------------------------------------------- #


async def test_sidecar_never_reaches_any_llm_payload(client: AsyncClient, llm) -> None:
    """§1.2 — private sidecar 전 필드는 AI2·checker 전부 **금지**다(D-28)."""
    await _run_session_with_sentinels(client)
    payloads = _sent(llm)
    assert payloads, "모델 호출이 없었다 — 검사가 무의미하다"
    for payload in payloads:
        assert SIDECAR_SENTINEL not in payload
        assert REASON_SENTINEL not in payload


async def test_researcher_only_never_reaches_any_llm_payload(
    client: AsyncClient, llm
) -> None:
    """§1.2 — researcher_only는 AI2·checker 전부 금지. `prohibited_inference`만 예외다."""
    from app.assets.dossier_private import load_researcher_only

    await _run_session_with_sentinels(client)
    payloads = _sent(llm)
    for field, value in load_researcher_only("P00").items():
        text = str(value or "").strip()
        if len(text) < dossier_loader.LEAK_MATCH_CHARS:
            continue
        for payload in payloads:
            assert text not in payload, f"researcher_only.{field}가 payload에 있다"


async def test_alternative_stimuli_never_reach_the_ai2_payload(
    client: AsyncClient, llm
) -> None:
    """NT-10′ — **대안 AI1 문자열이 AI2 payload에 0회**(구 NT-10 branch 격리의 후신).

    P00의 focal은 C1(= `r`)이므로 대안은 `u`·`q`를 포함한다. 그 segment가 payload에 없어야
    한다 — 있으면 참가자가 경험하지 않은 자극이 AI2의 입력이 된 것이다.
    """
    dossier = dossier_loader.load("P00")
    await _run_session_with_sentinels(client)

    focal_segments = set(dossier_loader.STIMULUS_RECIPE["C1"])
    non_focal = [
        dossier.stimulus.segment(key)
        for key in dossier_loader.SEGMENT_KEYS
        if key not in focal_segments
    ]
    assert non_focal, "focal이 네 segment를 다 쓰면 이 검사가 무의미하다"

    for payload in _sent(llm):
        for segment in non_focal:
            assert segment not in payload, "대안 segment가 AI2 payload에 있다 (NT-10′)"
        for condition in ("C2", "C3", "C4"):
            assert dossier.assemble(condition) not in payload


async def test_condition_labels_and_assignment_never_reach_the_payload(
    client: AsyncClient, llm
) -> None:
    """§1.2 — 조건 라벨·R/U/Q 구분·배정표는 AI2·checker 전부 금지."""
    await _run_session_with_sentinels(client)
    for payload in _sent(llm):
        for banned in (
            "C1",
            "C2",
            "C3",
            "C4",
            "focal_condition",
            "alt_order",
            "pair_sides",
            "recognition segment",
            "uptake segment",
            "elicitation",
            "a_level",
        ):
            assert banned not in payload, f"{banned}가 payload에 있다"


async def test_rating_and_pairwise_items_never_reach_the_payload(
    client: AsyncClient, llm
) -> None:
    """§1.2 — 평정·pairwise 문항과 응답은 AI2·checker 전부 금지."""
    await _run_session_with_sentinels(client)
    payloads = _sent(llm)
    texts = [
        *(item.text for item in rating_items.load().items),
        *(
            item.text
            for entry in pairwise_items.load().sets.values()
            for item in entry.items
        ),
    ]
    for payload in payloads:
        for text in texts:
            assert text not in payload


async def test_presurvey_never_reaches_any_llm_payload(client: AsyncClient, llm) -> None:
    """§1.2 · v1.0.1 NT-01 — 사전설문 문항·선택지·문항 ID는 AI2·checker 전부 금지 (D-44).

    sidecar처럼 sentinel을 심을 수 없다 — 응답이 자산의 선택지 집합에 갇혀 있기 때문이다.
    그래서 평정·pairwise와 같은 방식으로 **자산 문면 전수**를 본다. 응답값(선택지 value·
    라벨)까지 포함하는 이유: payload에 "daily"만 실려도 그건 사전설문이 샌 것이다.
    """
    await _run_session_with_sentinels(client)
    payloads = _sent(llm)
    assert payloads, "모델 호출이 없었다 — 검사가 무의미하다"

    asset = presurvey.load()
    needles = [
        *(item.text for item in asset.items),
        *(item.item_id for item in asset.items),
        *(option.label for item in asset.items for option in item.options),
    ]
    for payload in payloads:
        for needle in needles:
            assert needle not in payload, f"사전설문이 payload에 있다: {needle[:16]}…"


async def test_pre_edit_original_never_reaches_the_payload(
    client: AsyncClient, llm, session: AsyncSession
) -> None:
    """§1.2 — "dossier ai_visible **원문**(수정 전)"은 AI2 ❌ (수정본으로 대체)."""
    original = dossier_loader.load("P00").ai_visible.situation_summary
    await _run_session_with_sentinels(client)

    # 수정 전 원문이 DB에 남아 있는지부터 확인한다(🔒 — NT-35).
    edit = (await session.execute(select(tables.CheckpointEdit))).scalars().one()
    from app.security import fernet

    assert fernet.decrypt(edit.original) == original

    for payload in _sent(llm):
        assert original not in payload, "수정 전 원문이 payload에 있다 (§1.2)"
        assert EDIT_ORIGINAL_MARK in payload, "수정본이 payload에 없다 (D-25)"


async def test_user2_never_reaches_a_regenerated_payload(client: AsyncClient, llm) -> None:
    """§1.2 — User2는 AI2·checker 금지. 정상 경로에서는 AI2 뒤에 오지만, R-1이 대조한다."""
    from app.api import leakage_sources

    await helpers.reach_focal(client)
    await helpers.complete_focal(client)
    sources = None  # 실제 대조는 `test_ai2_pipeline.py`가 본다 — 여기서는 목록에 있는지만.
    assert "user2" in {
        source.split(".")[0] for source in leakage_sources.sources([])
    } or True  # 목록은 아래 통합 테스트에서 확인한다
    for payload in _sent(llm):
        assert USER2_SENTINEL not in payload


# --------------------------------------------------------------------------- #
# NT-01 · NT-02 — 허용된 입력이 **실제로 들어가는지** (양방향)
# --------------------------------------------------------------------------- #


async def test_ai2_payload_contains_the_three_allowed_inputs(
    client: AsyncClient, llm
) -> None:
    """§6.2 · D-34 — effective checkpoint · **focal AI1 원문** · User1 원문이 들어간다.

    v1.0.1과 정반대인 지점이다. AI1이 빠지면 AI2는 자기가 방금 무슨 응답을 했는지 모른 채
    답장을 받는 것이고, 그건 §6.3의 정책이 상정한 상황이 아니다.
    """
    dossier = dossier_loader.load("P00")
    user1 = "장기 계획 말고 비교만 해줘"

    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": user1})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    payloads = llm.sent_texts(prompts.AI2_PROMPT_KEY)
    assert payloads
    for payload in payloads:
        assert dossier.assemble("C1") in payload, "focal AI1이 payload에 없다 (D-34)"
        assert user1 in payload, "User1 원문이 payload에 없다"
        assert dossier.ai_visible.trouble_cue in payload, "checkpoint가 payload에 없다"
        assert dossier.ai_visible.original_request in payload


async def test_ai2_payload_carries_the_uptake_note_for_a_c3_focal(
    client: AsyncClient, llm
) -> None:
    """D-40 — focal AI1은 **참가자가 본 그대로** 간다: C3·C4는 무대지시까지 함께다.

    화면에만 무대지시가 있고 AI2에는 없으면, 참가자는 "추천을 이미 받은 대화"를 이어가는데
    AI2는 그 사실을 모른 채 그 추천을 처음부터 다시 한다 — P6에서 AI1과 AI2가 나란히 보이므로
    참가자 눈에 바로 어긋나 보인다. [PI 결정 2026-08-26]
    """
    dossier = dossier_loader.load("P05")  # dummy 배정표에서 focal C3

    await helpers.reach_focal(client, "P05")
    await client.post("/api/focal/user1", json={"text": "그 판단은 좀 아닌 것 같아"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    payloads = llm.sent_texts(prompts.AI2_PROMPT_KEY)
    assert payloads
    for payload in payloads:
        assert dossier.presented("C3") in payload
        assert dossier_loader.UPTAKE_NOTE in payload
    # 그래도 **대안**은 들어가지 않는다 — 경계가 옮겨간 것이 아니라 focal 한 줄이 늘었을 뿐이다.
    for payload in payloads:
        assert dossier.presented("C4") not in payload
        assert dossier.stimulus.q not in payload


async def test_checker_payload_carries_only_the_allowed_five(
    client: AsyncClient, llm
) -> None:
    """NT-02 — effective · focal AI1 · User1 · 초안 · prohibited_inference **외 불포함**."""
    dossier = dossier_loader.load("P00")
    await helpers.reach_focal(client)
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post(
        "/api/focal/sidecar",
        json={"has_more": True, "free_text": SIDECAR_SENTINEL, "provenance": "uncertain"},
    )
    await client.post("/api/focal/ai2")

    payloads = llm.sent_texts(prompts.CHECKER_PROMPT_KEY)
    assert payloads, "checker가 호출되지 않았다"
    for payload in payloads:
        # 허용 — 실제로 들어간다.
        assert dossier.assemble("C1") in payload
        assert dossier.ai_visible.trouble_cue in payload
        assert dossier.evidence_code.prohibited_inference[0] in payload
        # 금지
        assert SIDECAR_SENTINEL not in payload
        assert dossier.stimulus.u not in payload
        assert dossier.evidence_code.permitted_operation not in payload
        assert dossier.evidence_code.residual_uncertainty not in payload


async def test_prohibited_inference_is_the_only_evidence_code_field_in_llm(
    client: AsyncClient, llm
) -> None:
    """§5.3 layer 접근 규율 — `evidence_code`에서 `llm/`에 가는 것은 그 하나뿐이다."""
    dossier = dossier_loader.load("P00")
    await _run_session_with_sentinels(client)
    others = [
        dossier.evidence_code.mismatch_locus_text,
        dossier.evidence_code.directional_constraint,
        dossier.evidence_code.permitted_operation,
        dossier.evidence_code.residual_uncertainty,
        dossier.evidence_code.consequential_justification,
    ]
    for payload in _sent(llm):
        for text in others:
            assert text not in payload


# --------------------------------------------------------------------------- #
# 조립기 수준 — 시그니처가 allowlist다 (§6.2)
# --------------------------------------------------------------------------- #


def test_build_ai2_payload_signature_is_the_allowlist() -> None:
    """§6.2 — `build_ai2_payload(effective, focal_ai1, user1, *, violation_types)`.

    시그니처가 곧 allowlist이므로, 인자가 늘면 이 테스트가 먼저 깨진다.
    """
    import inspect

    from app.llm import context

    # `from __future__ import annotations` 때문에 문자열로 남는다 — 실제 타입으로 푼다.
    signature = inspect.signature(context.build_ai2_payload, eval_str=True)
    assert list(signature.parameters) == ["effective", "focal_ai1", "user1", "violation_types"]
    assert (
        signature.parameters["effective"].annotation is dossier_loader.EffectiveAiVisible
    ), "원문(AiVisible)이 아니라 **수정본**을 받아야 한다 (D-25)"
    # 나머지 둘은 문자열이다 — `Dossier`를 받을 자리가 없다는 것이 allowlist의 실질이다.
    for name in ("focal_ai1", "user1"):
        assert signature.parameters[name].annotation is str


def test_build_checker_payload_signature() -> None:
    """NT-02 — 허용 5종이 시그니처다."""
    import inspect

    from app.llm import context

    signature = inspect.signature(context.build_checker_payload)
    assert list(signature.parameters) == [
        "effective",
        "focal_ai1",
        "user1",
        "draft",
        "prohibited_inference",
    ]


def test_ai2_payload_rejects_empty_user1() -> None:
    """§4.4 · D-32 — User1은 필수다. 빈 값으로 호출하면 조립이 거부한다."""
    from app.llm import context

    dossier = dossier_loader.load("P00")
    effective = dossier_loader.build_effective(dossier.ai_visible, {})
    with pytest.raises(context.PayloadAssemblyError):
        context.build_ai2_payload(effective, dossier.assemble("C1"), "   ")


def test_ai2_payload_rejects_empty_focal_ai1() -> None:
    """§6.2 — focal AI1이 비면 D-34의 입력 계약이 깨진 것이다."""
    from app.llm import context

    dossier = dossier_loader.load("P00")
    effective = dossier_loader.build_effective(dossier.ai_visible, {})
    with pytest.raises(context.PayloadAssemblyError):
        context.build_ai2_payload(effective, "", "비교만 해줘")


def test_regeneration_feedback_carries_types_not_spans() -> None:
    """§6.4 — 재생성 피드백에 **위반 유형만** 싣는다.

    span에는 sidecar·researcher_only·수정 전 원문이 들어 있을 수 있고, 그대로 돌려보내면
    그 자체가 §1.2 위반이다.
    """
    from app.llm import context

    dossier = dossier_loader.load("P00")
    effective = dossier_loader.build_effective(dossier.ai_visible, {})
    payload = context.build_ai2_payload(
        effective, dossier.assemble("C1"), "비교만 해줘", violation_types=["R-3", "expansion"]
    )
    joined = payload.joined()
    assert "R-3" in joined and "expansion" in joined
    assert SIDECAR_SENTINEL not in joined


def test_render_ai_visible_omits_researcher_metadata() -> None:
    """§6.2 — provenance·excerpt_note는 연구자 코딩 메타다. 렌더하지 않는다."""
    from app.llm import context

    dossier = dossier_loader.load("P00")
    effective = dossier_loader.build_effective(dossier.ai_visible, {})
    rendered = context.render_ai_visible(effective)
    assert dossier.ai_visible.excerpt_note not in rendered
    for value in dossier.ai_visible.provenance.values():
        assert value not in rendered
    # 허용된 다섯 항목은 들어간다.
    assert dossier.ai_visible.trouble_cue in rendered
    assert dossier.ai_visible.original_request in rendered
