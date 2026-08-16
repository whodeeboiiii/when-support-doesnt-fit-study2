"""NT-01 · NT-02 · NT-10 — evidence boundary 런타임 검증 (구현명세서 §1.2 · §6.2 · §3.4).

NT-04(정적 검사)가 "그 값이 LLM 경로에 **도달할 수 있는가**"를 막는다면, 여기는 "이번 세션에서
실제로 **무엇이 나갔는가**"를 본다. 방법은 §1.2 표의 금지 항목마다 **고유 문자열(sentinel)을
심고**, 세션을 끝까지 돌린 뒤 모델에 나간 문자열 전문에서 그 sentinel을 찾는 것이다.

sentinel을 쓰는 이유: 실제 payload 조립을 뜯어보는 대신 "나간 것"만 본다. 조립기 구조가
바뀌어도 이 테스트의 의미는 그대로다.

    금지(§1.2 · §6.2): AI1 원문 · 조건 라벨 · sequence · sidecar 전 필드 ·
    researcher_only 층 · 타 branch의 User1/AI2/sidecar · 평정 · 사전 설문
"""

from __future__ import annotations

from typing import Sequence

import pytest
from httpx import AsyncClient

from app.assets import dossier_loader, presurvey
from app.assets.dossier_private import load_researcher_only
from app.llm.fake_llm import FakeLLM
from app.llm.prompts import AI2_PROMPT_KEY, CHECKER_PROMPT_KEY
from app.core.williams import condition as williams_condition
from tests import helpers

#: branch별 고유 발화 — 어느 branch의 것이 어디에 나갔는지 구분하려고 심는다.
USER1_SENTINELS = {
    1: "브랜치하나고유발화알파",
    2: "브랜치둘고유발화베타",
    3: "브랜치셋고유발화감마",
    4: "브랜치넷고유발화델타",
}
SIDECAR_TEXT_SENTINEL = "사이드카비공개기록엡실론"
SIDECAR_REASON_SENTINEL = "미전송사유제타"


async def _run_branch(client: AsyncClient, index: int, *, with_sidecar: bool) -> None:
    await helpers.advance(client, "P4")
    await client.post(
        f"/api/branch/{index}/user1",
        json={"disposition": "reply", "text": f"{USER1_SENTINELS[index]} 장단점만 정리해줘"},
    )
    sidecar = (
        {
            "choice": "has",
            "free_text": SIDECAR_TEXT_SENTINEL,
            "relevance": 6,
            "reason": SIDECAR_REASON_SENTINEL,
        }
        if with_sidecar
        else {"choice": "none"}
    )
    await client.post(f"/api/branch/{index}/sidecar", json=sidecar)
    await client.post(f"/api/branch/{index}/ai2")
    await helpers.advance(client, "P7")
    await client.post(f"/api/branch/{index}/downstream", json={"code": "pause"})
    await client.post(f"/api/branch/{index}/ratings", json=helpers.ratings_payload())


def _forbidden_strings() -> list[str]:
    """§1.2 표의 금지 항목에서 실제 문자열을 모은다."""
    dossier = dossier_loader.load("P00")
    strings = [
        # AI1 원문 4종 (§0.4 — referent 치환으로만 반영)
        *(dossier.stimulus(condition) for condition in dossier_loader.CONDITIONS),
        # researcher_only 층 전 필드
        *(str(value) for value in load_researcher_only("P00").values()),
        # sidecar
        SIDECAR_TEXT_SENTINEL,
        SIDECAR_REASON_SENTINEL,
        # 사전 설문 문항 원문
        presurvey.load().items[0].text,
    ]
    return [value for value in strings if value.strip()]


def _sent(llm: FakeLLM, prompt_key: str) -> Sequence[str]:
    sent = llm.sent_texts(prompt_key)
    assert sent, f"{prompt_key} 호출이 한 번도 없었다 — 검사가 공허하다"
    return sent


async def test_nt01_ai2_payload_excludes_every_forbidden_source(
    client: AsyncClient, llm: FakeLLM
) -> None:
    await helpers.reach_branch_block(client, "P00")
    await _run_branch(client, 1, with_sidecar=True)
    await _run_branch(client, 2, with_sidecar=True)

    for payload in _sent(llm, AI2_PROMPT_KEY):
        for forbidden in _forbidden_strings():
            assert forbidden not in payload, f"AI2 payload 누출: {forbidden[:24]!r}"
        # 조건 라벨·sequence는 문자열로도 나가지 않는다(§6.2).
        for label in ("C1", "C2", "C3", "C4", "uptake", "elicitation", "sequence"):
            assert label not in payload, f"AI2 payload에 조작 라벨: {label}"


async def test_nt01_allowed_inputs_are_actually_present(
    client: AsyncClient, llm: FakeLLM
) -> None:
    """허용 3종이 **실제로** 들어가는지도 본다 — 다 빼 버려도 통과하는 검사는 검사가 아니다."""
    await helpers.reach_branch_block(client, "P00")
    await _run_branch(client, 1, with_sidecar=True)

    payload = _sent(llm, AI2_PROMPT_KEY)[0]
    ai_visible = dossier_loader.load("P00").ai_visible
    assert ai_visible.situation_summary in payload
    assert ai_visible.trouble_cue.text in payload
    assert USER1_SENTINELS[1] in payload


async def test_nt02_checker_payload_is_limited_to_its_allowlist(
    client: AsyncClient, llm: FakeLLM
) -> None:
    """§6.5 checker 입력 = ai_visible 요약 + user1_normalized + 초안 (+ prohibited_inference)."""
    await helpers.reach_branch_block(client, "P00")
    await _run_branch(client, 1, with_sidecar=True)

    dossier = dossier_loader.load("P00")
    for payload in _sent(llm, CHECKER_PROMPT_KEY):
        for forbidden in _forbidden_strings():
            assert forbidden not in payload, f"checker payload 누출: {forbidden[:24]!r}"
        assert dossier.ai_visible.situation_summary in payload
        assert USER1_SENTINELS[1] in payload
        # 판정 참조로 명시 허용된 것(§6.5)
        assert dossier.derivation.prohibited_inference[0] in payload


async def test_nt10_branch_isolation_across_four_branches(
    client: AsyncClient, llm: FakeLLM
) -> None:
    """§3.4 — 한 payload에 두 branch의 발화가 함께 실리는 일이 0회여야 한다."""
    await helpers.reach_branch_block(client, "P00")
    for index in range(1, 5):
        await _run_branch(client, index, with_sidecar=index % 2 == 1)

    assert llm.call_count(AI2_PROMPT_KEY) == 4, "reply 4개 branch면 AI2 호출도 4건이다"
    for prompt_key in (AI2_PROMPT_KEY, CHECKER_PROMPT_KEY):
        for payload in _sent(llm, prompt_key):
            present = [
                index for index, sentinel in USER1_SENTINELS.items() if sentinel in payload
            ]
            assert len(present) <= 1, f"{prompt_key} payload에 여러 branch 발화: {present}"


async def test_nt10_no_conversation_history_accumulates(
    client: AsyncClient, llm: FakeLLM
) -> None:
    """§3.4 — 세션 누적 대화 이력이라는 개념이 없다. payload 길이가 branch마다 늘지 않는다."""
    await helpers.reach_branch_block(client, "P00")
    for index in range(1, 5):
        await _run_branch(client, index, with_sidecar=False)

    lengths = [len(payload) for payload in _sent(llm, AI2_PROMPT_KEY)]
    spread = max(lengths) - min(lengths)
    assert spread < 200, f"payload가 branch마다 커진다 — 이력 누적 의심: {lengths}"


@pytest.mark.parametrize("branch_index", [1, 2, 3, 4])
async def test_ai1_text_never_reaches_the_model(
    client: AsyncClient, llm: FakeLLM, branch_index: int
) -> None:
    """§0.4 — AI1 원문 비전달. 조건이 무엇이든 해당 branch의 자극 전문이 나가지 않는다."""
    await helpers.reach_branch_block(client, "P00")
    for index in range(1, branch_index + 1):
        await _run_branch(client, index, with_sidecar=False)

    stimulus = dossier_loader.load("P00").stimulus(williams_condition("P00", branch_index))
    for prompt_key in (AI2_PROMPT_KEY, CHECKER_PROMPT_KEY):
        for payload in llm.sent_texts(prompt_key):
            assert stimulus not in payload
