"""OpenRouter 클라이언트 (구현명세서 §2.2 — v5.0 이식·개정).

키 하나로 MAIN(AI2 생성)·VALIDATOR(integrity checker) 두 모델을 호출한다. 슬러그는 env로만
주입한다. 동시성·타임아웃·재시도·감사 기록은 `calls.py`가 담당하므로 이 모듈은 **HTTP 왕복만**
한다.

v5.0에서 바뀐 것
- **프롬프트 캐싱 미사용**(D-21·§2.2.3): 참가자별 payload가 상이하고 호출량이 소량이라
  이득이 없다. 구 `cache_control` breakpoint 코드는 이식하지 않았다.
- provider 고정은 유지한다(§2.2.2-①) [확인 2 — 문법 현행 여부 재확인].

응답의 실제 model 문자열은 계속 기록해 silent update를 감지한다(§2.2.2-②).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.llm.gateway.client import LLMRequest, LLMResponse, ModelRole, NoClientConfigured

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"

#: §2.2.2-① provider 고정. AI2는 Anthropic 계열, checker는 타 제공사(OpenAI 계열)만 허용하고
#: fallback을 끈다 — provider가 세션마다 달라지면 자극·판정 특성이 cohort를 오염시킨다(§1.4).
#: 슬러그와 달리 **제공사 계열은 §2.2.1이 문서에 고정한 값**이므로 env가 아니라 코드에 둔다.
_PROVIDER_ROUTING: dict[ModelRole, dict[str, Any]] = {
    ModelRole.MAIN: {"only": ["anthropic"], "allow_fallbacks": False},
    ModelRole.VALIDATOR: {"only": ["openai"], "allow_fallbacks": False},
}


class OpenRouterClient:
    """§2.2.3 호출 규약 중 HTTP 부분. 클라이언트 레벨 자동 재시도는 두지 않는다."""

    def __init__(self, *, api_key: str, main_model: str, validator_model: str) -> None:
        self._api_key = api_key
        self._models = {ModelRole.MAIN: main_model, ModelRole.VALIDATOR: validator_model}

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenRouterClient:
        if not (
            settings.openrouter_api_key and settings.main_model_id and settings.validator_model_id
        ):
            raise NoClientConfigured(
                "OPENROUTER_API_KEY·MAIN_MODEL_ID·VALIDATOR_MODEL_ID가 필요하다 (§2.4)."
            )
        client = cls(
            api_key=settings.openrouter_api_key,
            main_model=settings.main_model_id,
            validator_model=settings.validator_model_id,
        )
        client._warn_on_provider_mismatch()
        return client

    def model_for(self, role: ModelRole) -> str:
        return self._models[role]

    def _warn_on_provider_mismatch(self) -> None:
        """슬러그 계열과 고정 provider가 어긋나면 기동 시점에 경고한다.

        `_PROVIDER_ROUTING`이 코드 고정이라, env 슬러그만 다른 계열로 바꾸면 **전 호출이
        런타임에 실패**하고 조용히 fallback으로 수렴한다. 그 오설정을 세션 전에 드러낸다.
        """
        for role, slug in self._models.items():
            pinned = _PROVIDER_ROUTING[role]["only"]
            if slug.split("/", 1)[0] not in pinned:
                logger.warning(
                    "모델 슬러그와 고정 provider 불일치 — role=%s slug=%s pinned=%s (§2.2.2-①)",
                    role,
                    slug,
                    pinned,
                )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self._models[request.role],
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
            "provider": _PROVIDER_ROUTING[request.role],
            # §2.2.3 토큰·비용 계량 — include를 켜야 usage에 cost가 실린다.
            "usage": {"include": True},
        }
        if request.max_tokens:
            body["max_tokens"] = request.max_tokens
        if request.expect_json:
            # §2.2.3 구조화 출력. 스키마 본문은 프롬프트(부록 A.2)가 이미 지시하므로 여기서는
            # JSON 형식만 강제한다 — prompt_config를 유일한 스키마 source of truth로 유지한다.
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if request.request_id:
            headers["X-Request-Id"] = request.request_id

        # 타임아웃은 calls.py의 asyncio.timeout이 권위다. httpx에도 같은 값을 주어 소켓을 닫는다.
        async with httpx.AsyncClient(timeout=request.timeout_ms / 1000) as http:
            response = await http.post(API_URL, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return LLMResponse(
            text=choice,
            provider_reported_model=data.get("model"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
        )
