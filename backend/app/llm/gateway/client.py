"""LLM 클라이언트 인터페이스와 프로세스 단일 주입점 (구현명세서 §2.2 — v5.0 이식).

게이트웨이를 **인터페이스 뒤에** 두는 이유: 팀 시연(DEV_MODE)·CI·fixture 러너가 실호출 없이
전 경로를 돌려야 한다(§6.7·§10.1). 호출부는 `get_client()`만 알고, 실제 구현은 기동 시
주입된다(`app.main`).

클라이언트가 주입되지 않았으면 `NoClientConfigured`를 raise한다 — 조용히 실호출로 새지 않고
§9.1 오류 경로(재시도 → neutral_fallback)로 수렴한다. 즉 키가 없는 개발 환경에서도 참가자
흐름은 dead-end 없이 끝까지 진행된다(§9.1 dead-end 금지).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ModelRole(StrEnum):
    """§2.2.1 모델 배정 — 이원화(D-18). 슬러그는 env로만 주입한다."""

    MAIN = "main"  # AI2 생성 (부록 A.1) — Anthropic 계열
    VALIDATOR = "validator"  # integrity checker (부록 A.2) — OpenAI 계열, 타 제공사


@dataclass(frozen=True, slots=True)
class LLMRequest:
    role: ModelRole
    #: prompt_config의 프롬프트 키 (§6.7) — audit·fake LLM이 호출 종류를 구분한다.
    prompt_key: str
    system: str
    user: str
    temperature: float
    timeout_ms: int
    max_tokens: int | None = None
    #: §2.2.3 구조화 출력은 checker만 (`response_format: json_object`). AI2는 자유 텍스트다.
    expect_json: bool = False
    #: §9.1 "동일 request id 1회 retry" — 재시도가 같은 논리 요청임을 제공사에 알린다.
    request_id: str = ""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    #: §2.2.2-② silent update 감지 — 매 호출 저장, 변경 최초 감지 시 notify
    provider_reported_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


class NoClientConfigured(RuntimeError):
    """LLM 클라이언트 미주입(키·슬러그 미설정 포함). §9.1 경로로 수렴시킨다."""


_client: LLMClient | None = None


def set_client(client: LLMClient | None) -> None:
    """기동 시(`app.main`) 또는 테스트에서 1회 주입한다."""
    global _client
    _client = client


def get_client() -> LLMClient:
    if _client is None:
        raise NoClientConfigured(
            "LLM 클라이언트가 주입되지 않았다 (OPENROUTER_API_KEY·MAIN_MODEL_ID 미설정 가능)."
        )
    return _client
