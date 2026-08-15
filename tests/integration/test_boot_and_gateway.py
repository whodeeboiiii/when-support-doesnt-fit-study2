"""DEV_MODE 기동과 LLM 게이트웨이 왕복 (§2.0 · §2.2.3 · §8.4 · §9.1).

NS1의 완료 조건 두 가지를 그대로 건다.
- `DEV_MODE=true`로 앱이 뜨고(자산 게이트 통과), `/api/health`가 응답한다.
- 이식한 게이트웨이가 fake LLM으로 왕복하고, 호출 1건이 `llm_calls` 1행으로 남는다(NT-15의
  전제 — 최종 표시 텍스트의 경로 복원은 NS3에서 `generations`와 함께 완성된다).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import prompts
from app.llm.fake_llm import FakeLLM
from app.llm.gateway import calls
from app.models.tables import LlmCall


async def test_health_endpoint_reports_assets(client) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dev_mode"] is True
    assert body["dossiers"]["loaded"] == 13  # P00 + P01–P12
    # 자산 **내용**은 실리지 않는다 (§2.9 · NT-13).
    assert "stimuli" not in response.text
    assert "researcher_only" not in response.text


async def test_dev_mode_injects_fake_llm() -> None:
    """§6.7 — DEV_MODE는 실키 없이 전 경로를 돌린다."""
    from app.llm.gateway.client import get_client
    from app.main import _install_llm_client

    _install_llm_client()
    assert isinstance(get_client(), FakeLLM)


async def test_call_model_records_one_llm_call_row(session: AsyncSession, llm: FakeLLM) -> None:
    result = await calls.call_model(
        session,
        prompt_key=prompts.AI2_PROMPT_KEY,
        system="[대화 맥락]\n맥락 요약",
        user="[사용자 메시지]\n장기 계획 말고 장단점만 정리해줘",
    )
    assert result.text
    assert result.retry_count == 0

    rows = (await session.execute(select(LlmCall))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.role == "main"
    assert row.status == "ok"
    assert row.request_id
    assert row.prompt_hash  # §8.4 — 원문이 아니라 hash를 남긴다
    assert row.params["prompt_key"] == prompts.AI2_PROMPT_KEY
    assert row.params["temperature"] == 0.4
    assert row.params["prompt_hash"] == prompts.config_hash()
    assert row.provider_reported_model == "fake/main"


async def test_checker_call_parses_json(session: AsyncSession) -> None:
    """§2.2.3 — checker만 JSON. 파싱 결과가 `data`로 온다."""
    result = await calls.call_model(
        session,
        prompt_key=prompts.CHECKER_PROMPT_KEY,
        system="검증기",
        user="[AI 응답 초안]\n초안",
    )
    assert result.data == {"violations": [], "pass": True}


async def test_failure_retries_once_then_raises(session: AsyncSession, llm: FakeLLM) -> None:
    """§9.1 — 동일 request id로 1회 재시도, 그 뒤는 호출부의 fallback 사다리로 넘긴다."""
    llm.fail(prompts.AI2_PROMPT_KEY, times=2)

    try:
        await calls.call_model(
            session, prompt_key=prompts.AI2_PROMPT_KEY, system="s", user="u"
        )
    except calls.CallFailed:
        pass
    else:  # pragma: no cover
        raise AssertionError("CallFailed가 나야 한다")

    assert llm.call_count(prompts.AI2_PROMPT_KEY) == 2
    request_ids = {call.request_id for call in llm.calls}
    assert len(request_ids) == 1, "재시도는 동일 request id여야 한다 (§9.1)"

    rows = (await session.execute(select(LlmCall))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status.startswith("error:")


async def test_timeouts_follow_the_frozen_parameters() -> None:
    """§0.5 — AI2 90,000ms / checker 45,000ms."""
    from app.llm.gateway.client import ModelRole

    assert calls.timeout_ms(ModelRole.MAIN) == 90_000
    assert calls.timeout_ms(ModelRole.VALIDATOR) == 45_000
