"""LLM 호출 단일 관문 (구현명세서 §2.2.3 · §8.4 · §9.1 — v5.0 이식·개정).

**모든 LLM 호출이 이 모듈의 `call_model`을 지난다.** 그래서 다음이 한 곳에서 강제된다.

- §2.2.3: `asyncio.Semaphore(LLM_CONCURRENCY=2)`, AI2 90s / checker 45s 타임아웃,
  클라이언트 라이브러리 자동 재시도 off.
- §9.1: 동일 request_id로 **1회만** 재시도한다. 그 뒤는 호출부가 재생성 1회 → neutral_fallback
  사다리로 수렴한다(§6.5·§6.6) — dead-end 금지.
- §8.4: 호출 1건 = `llm_calls` 1행. 자산 버전·hash·모델 문자열(요청·보고)·파라미터·토큰·비용·
  지연·상태를 남겨 generation integrity 보고(초안 §7.9)를 이 필드만으로 재구성한다(NT-15).

⚠ **payload 조립은 이 모듈의 일이 아니다.** §6.2 allowlist(= AI2 입력 3종)를 통과한 문자열만
넘어와야 하고, 그 조립기는 NS3의 `llm/context.py`다. 여기서는 받은 문자열을 그대로 보낸다 —
allowlist를 여기에 또 두면 검사 지점이 둘로 갈라져 어느 쪽이 권위인지 흐려진다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.llm import prompts
from app.llm.gateway.client import (
    LLMRequest,
    LLMResponse,
    ModelRole,
    get_client,
)
from app.models.tables import LlmCall
from app.notify import watch

logger = logging.getLogger(__name__)


class CallFailed(RuntimeError):
    """재시도까지 실패 — 호출부가 §6.6 neutral_fallback으로 수렴시킨다."""


@dataclass(slots=True)
class CallResult:
    text: str
    #: expect_json 호출(checker)의 파싱 결과. 자유 텍스트 호출(AI2)에서는 None.
    data: dict[str, Any] | None
    retry_count: int
    latency_ms: int
    provider_reported_model: str | None


_semaphore: asyncio.Semaphore | None = None


def _concurrency_guard() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().llm_concurrency)
    return _semaphore


def reset_concurrency_guard() -> None:
    """테스트에서 이벤트 루프가 바뀔 때 세마포어를 새로 만든다."""
    global _semaphore
    _semaphore = None


def timeout_ms(role: ModelRole) -> int:
    """§0.5 — AI2 90,000ms / checker 45,000ms [파일럿 확정]."""
    settings = get_settings()
    return settings.ai2_timeout_ms if role is ModelRole.MAIN else settings.checker_timeout_ms


async def call_model(
    session: AsyncSession,
    *,
    prompt_key: str,
    system: str,
    user: str,
    generation_id: uuid.UUID | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> CallResult:
    """프롬프트 1건을 모델에 보낸다. 실패는 `CallFailed`로 통일한다(§9.1)."""
    role = prompts.PROMPT_KEY_ROLE[prompt_key]
    params = prompts.parameters(prompt_key)
    expect_json = bool(params.get("expect_json"))
    resolved_temperature = params["temperature"] if temperature is None else temperature
    resolved_max_tokens = params.get("max_tokens") if max_tokens is None else max_tokens

    request = LLMRequest(
        role=role,
        prompt_key=prompt_key,
        system=system,
        user=user,
        temperature=float(resolved_temperature),
        timeout_ms=timeout_ms(role),
        max_tokens=resolved_max_tokens,
        expect_json=expect_json,
        request_id=str(uuid.uuid4()),
    )

    started = time.monotonic()
    retry_count = 0
    last_error: Exception | None = None
    response: LLMResponse | None = None
    data: dict[str, Any] | None = None

    # §9.1: 동일 request_id 1회 재시도. HTTP 클라이언트 레벨 재시도는 끈다(§2.2.3).
    for attempt in range(2):
        retry_count = attempt
        try:
            response = await _complete(request)
            data = _parse_json(response.text) if expect_json else None
            last_error = None
            break
        # 제공사 장애·타임아웃·파싱 실패를 구분하지 않는다 — 전부 §9.1의 같은 경로로 간다.
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("LLM 호출 실패 (prompt=%s, attempt=%s): %s", prompt_key, attempt, exc)

    latency_ms = int((time.monotonic() - started) * 1000)
    _record_call(
        session,
        request=request,
        response=response if last_error is None else None,
        generation_id=generation_id,
        latency_ms=latency_ms,
        status="ok" if last_error is None else f"error:{type(last_error).__name__}",
    )

    if last_error is None and response is not None:
        # §2.2.2-② — 모든 호출이 이 함수를 지나므로 모델 문자열 변경은 여기서만 관측된다.
        await watch.check_provider_model(str(role), response.provider_reported_model)
        return CallResult(
            text=response.text,
            data=data,
            retry_count=retry_count,
            latency_ms=latency_ms,
            provider_reported_model=response.provider_reported_model,
        )

    raise CallFailed(f"{prompt_key} 호출 실패: {last_error}") from last_error


async def _complete(request: LLMRequest) -> LLMResponse:
    client = get_client()
    async with _concurrency_guard():
        async with asyncio.timeout(request.timeout_ms / 1000):
            return await client.complete(request)


def _parse_json(text: str) -> dict[str, Any]:
    """checker 응답 파싱 (§2.2.3). 코드펜스로 감싸 오는 경우까지만 관용한다."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("JSON 객체를 찾을 수 없다")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON 객체가 아니다")
    return parsed


def _record_call(
    session: AsyncSession,
    *,
    request: LLMRequest,
    response: LLMResponse | None,
    generation_id: uuid.UUID | None,
    latency_ms: int,
    status: str,
) -> None:
    """§8.1 `llm_calls` 1행. **프롬프트·응답 원문은 남기지 않는다** — hash와 계량만 남긴다.

    flush하지 않는다. 감사 행은 요청 트랜잭션과 함께 커밋된다(§9.1 부분 상태 금지).
    """
    settings = get_settings()
    model_requested = (
        settings.main_model_id if request.role is ModelRole.MAIN else settings.validator_model_id
    )
    session.add(
        LlmCall(
            generation_id=generation_id,
            role=str(request.role),
            request_id=request.request_id,
            model_requested=model_requested,
            provider_reported_model=response.provider_reported_model if response else None,
            prompt_hash=prompts.call_hash(request.system, request.user),
            params={
                "prompt_key": request.prompt_key,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "timeout_ms": request.timeout_ms,
                "expect_json": request.expect_json,
                **prompts.version_lock(),
            },
            prompt_tokens=response.prompt_tokens if response else None,
            completion_tokens=response.completion_tokens if response else None,
            cost=response.cost_usd if response else None,
            latency_ms=latency_ms,
            status=status,
        )
    )
