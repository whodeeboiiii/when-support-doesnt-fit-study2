"""fake LLM — DEV_MODE·CI 공용 결정론 클라이언트 (구현명세서 §6.7 · 부록 A.5, v5.0 이식).

`llm.gateway.client.LLMClient` 프로토콜을 만족하는 가짜 구현이다. 실호출 0건으로 전 경로를
돌린다 — 팀 시연(DEV_MODE=true)과 CI가 같은 구현을 쓴다.

기본 응답은 **규칙을 지키는 모델**을 모사한다(부록 A.5).
- AI2(`ai2_generation`): [대화 맥락]·[사용자 메시지] 블록을 되받는 결정론 응답. 질문 0개·
  1,200자 미만이라 규칙 계층(§6.5 R-3·R-4)을 통과한다 — 통합 테스트가 fallback이 아니라
  정상 경로를 돌아야 하기 때문이다.
- checker(`integrity_checker`): `{"violations": [], "pass": true}` 결정론 JSON.

⚠ 부록 A.5의 "fixture 트리거 문자열로 위반 유형 재현"은 NS3(§10.1 integrity fixture)에서
`stub()` 위에 얹는다. NS1은 정상 경로 응답과 장애 주입(`fail()`)까지만 제공한다.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence

from app.llm.gateway.client import LLMRequest, LLMResponse
from app.llm.prompts import AI2_PROMPT_KEY, CHECKER_PROMPT_KEY

#: 부록 A.1·A.2 프롬프트의 블록 머리말.
_CONTEXT_BLOCK = "[대화 맥락]"
_MESSAGE_BLOCK = "[사용자 메시지]"

_CHECKER_PASS = json.dumps({"violations": [], "pass": True}, ensure_ascii=False)


def _block(text: str, name: str) -> str:
    match = re.search(rf"\[{re.escape(name.strip('[]'))}\]\n(.*?)(?:\n\[|\Z)", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _first_sentence(text: str, limit: int = 60) -> str:
    head = text.replace("\n", " ").split(".")[0].strip()
    return head[:limit]


def _default_ai2(request: LLMRequest) -> str:
    """규칙을 지키는 AI2 응답의 모사 — 새 추론 없이 받은 내용만 되짚는다.

    질문을 만들지 않는다(R-3 통과). 새 주제로 확장하지 않는다(checker `expansion` 미해당).
    """
    joined = f"{request.system}\n{request.user}"
    message = _block(joined, _MESSAGE_BLOCK) or _block(joined, _CONTEXT_BLOCK)
    echo = _first_sentence(message)
    tail = f" 말씀하신 부분({echo})은 그대로 두고 이어가겠습니다." if echo else ""
    return f"말씀해주신 내용을 그대로 받아서 다음 응답을 이어갑니다.{tail}"


_DYNAMIC_DEFAULTS = {AI2_PROMPT_KEY: _default_ai2}
_STATIC_DEFAULTS = {CHECKER_PROMPT_KEY: _CHECKER_PASS}


class FakeLLM:
    """호출을 기록하고 스텁을 돌려준다. 스텁이 없으면 규칙을 지키는 기본 응답을 낸다."""

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []
        self._queues: dict[str, list[str | Exception]] = defaultdict(list)

    # --- 스텁 등록 ---

    def stub(self, prompt_key: str, *responses: str | dict | Exception) -> None:
        """호출 순서대로 소비한다. 큐가 비면 마지막 응답을 반복한다."""
        for response in responses:
            value = (
                json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else response
            )
            self._queues[prompt_key].append(value)

    def fail(self, prompt_key: str, error: Exception | None = None, *, times: int = 2) -> None:
        """§9.1 장애 시뮬레이션. 기본 times=2 = 최초 호출 + 1회 재시도 모두 실패."""
        for _ in range(times):
            self._queues[prompt_key].append(error or TimeoutError("fake timeout"))

    # --- 호출 기록 조회 ---

    def call_count(self, prompt_key: str) -> int:
        return sum(1 for call in self.calls if call.prompt_key == prompt_key)

    def prompt_keys(self) -> list[str]:
        return [call.prompt_key for call in self.calls]

    def sent_texts(self, prompt_key: str) -> Sequence[str]:
        """§NT-01·NT-02 leakage 검사가 보는 것 — 실제로 모델에 나간 문자열 전문."""
        return [
            f"{call.system}\n{call.user}" for call in self.calls if call.prompt_key == prompt_key
        ]

    # --- LLMClient 프로토콜 ---

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        queue = self._queues.get(request.prompt_key)
        if queue:
            value = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(value, Exception):
                raise value
            text = value
        elif request.prompt_key in _DYNAMIC_DEFAULTS:
            text = _DYNAMIC_DEFAULTS[request.prompt_key](request)
        else:
            text = _STATIC_DEFAULTS[request.prompt_key]
        return LLMResponse(
            text=text,
            provider_reported_model=f"fake/{request.role}",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
        )
