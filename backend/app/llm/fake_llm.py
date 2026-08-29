"""fake LLM — DEV_MODE·CI 공용 결정론 클라이언트 (구현명세서 §6.6 · 부록 A.6 (v2)).

`llm.gateway.client.LLMClient` 프로토콜을 만족하는 가짜 구현이다. 실호출 0건으로 전 경로를
돌린다 — 팀 시연(DEV_MODE=true)과 CI가 같은 구현을 쓴다.

기본 응답은 **규칙을 지키는 모델**을 모사한다(부록 A.6).
- AI2(`ai2_generation`): [대화 맥락]·[AI의 직전 답변]·[사용자 메시지] 블록을 되받는 결정론
  응답. 질문 0개·1,200자 미만이라 규칙 계층(§6.4 R-3·R-4)을 통과한다 — 통합 테스트가 fallback이 아니라
  정상 경로를 돌아야 하기 때문이다.
- checker(`integrity_checker`): `{"violations": [], "pass": true}` 결정론 JSON.

부록 A.6의 "fixture 트리거 문자열로 위반 유형 재현"도 여기 있다(§10.1). User1에 `[[fixture:…]]`
토큰이 들어오면 해당 위반을 가진 결정론 초안을 낸다 — 위반 경로(재생성·fallback)를 실호출 없이
끝까지 태우기 위해서다. checker 역할은 초안에서 **규칙표 문구**를 찾아 결정론 JSON을 낸다.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence

from app.llm.gateway.client import LLMRequest, LLMResponse
from app.llm.prompts import AI2_CONSTRAINED_PROMPT_KEY, AI2_PROMPT_KEY, CHECKER_PROMPT_KEY

#: 부록 A.1·A.2 v2 프롬프트의 블록 머리말.
_CONTEXT_BLOCK = "[대화 맥락]"
_PRIOR_AI_BLOCK = "[AI의 직전 답변]"
_MESSAGE_BLOCK = "[사용자 메시지]"

_DRAFT_BLOCK = "[AI 응답 초안]"

_CHECKER_PASS = json.dumps({"violations": [], "pass": True}, ensure_ascii=False)

#: 부록 A.6 — fixture 트리거. User1 텍스트에 이 토큰이 있으면 해당 위반 초안을 낸다.
FIXTURE_TOKEN = "[[fixture:{name}]]"

#: 트리거별 결정론 초안. 규칙 계층(R-3·R-4)과 checker(부록 A.2 3유형)를 모두 재현한다.
FIXTURE_DRAFTS: dict[str, str] = {
    "clean": "말씀하신 범위 안에서 다음 내용을 이어가겠습니다.",
    # R-3 — 질문 2개(상한 1개)
    "questions_2": "어떤 쪽이 더 필요하세요? 아니면 다른 방식이 좋을까요?",
    # R-4 — 길이 상한 초과
    "too_long": "같은 내용을 길게 반복합니다. " * 80,
    # checker — expansion
    "expansion": "말씀하신 내용을 받아 6개월 커리어 계획을 새로 정리해 드리겠습니다.",
    # checker — unsupported_inference
    "unsupported_inference": "많이 불안하신 것 같아요. 정서적인 지지가 필요하신 상태로 보입니다.",
    # checker — correction_ignored
    "correction_ignored": "요청하신 것과 별개로 앞서 드린 장기 계획을 계속 진행하겠습니다.",
}

#: checker 결정론 규칙표 — 초안에 이 문구가 있으면 해당 유형을 보고한다.
CHECKER_SIGNALS: dict[str, str] = {
    "expansion": "6개월 커리어 계획",
    "unsupported_inference": "많이 불안하신 것 같아요",
    "correction_ignored": "앞서 드린 장기 계획을 계속",
}


def fixture_token(name: str) -> str:
    """fixture·테스트가 User1에 심는 트리거 문자열."""
    if name not in FIXTURE_DRAFTS:
        raise KeyError(f"알 수 없는 fixture 트리거: {name!r}")
    return FIXTURE_TOKEN.format(name=name)


def _block(text: str, name: str) -> str:
    match = re.search(rf"\[{re.escape(name.strip('[]'))}\]\n(.*?)(?:\n\[|\Z)", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _first_sentence(text: str, limit: int = 60) -> str:
    head = text.replace("\n", " ").split(".")[0].strip()
    return head[:limit]


def _default_ai2(request: LLMRequest) -> str:
    """규칙을 지키는 AI2 응답의 모사 — 새 추론 없이 받은 내용만 되짚는다.

    질문을 만들지 않는다(R-3 통과). 새 주제로 확장하지 않는다(checker `expansion` 미해당).
    단, User1에 fixture 트리거가 있으면 해당 위반 초안을 낸다(부록 A.5).
    """
    joined = f"{request.system}\n{request.user}"
    for name in FIXTURE_DRAFTS:
        if FIXTURE_TOKEN.format(name=name) in joined:
            return FIXTURE_DRAFTS[name]

    message = _block(joined, _MESSAGE_BLOCK) or _block(joined, _CONTEXT_BLOCK)
    echo = _first_sentence(message)
    tail = f" 말씀하신 부분({echo})은 그대로 두고 이어가겠습니다." if echo else ""
    return f"말씀해주신 내용을 그대로 받아서 다음 응답을 이어갑니다.{tail}"


def _default_checker(request: LLMRequest) -> str:
    """규칙표 기반 결정론 JSON (부록 A.6·A.2).

    초안 블록만 본다 — 맥락·User1에 같은 문구가 있어도 위반이 아니다(위반은 **AI 출력**의
    성질이다).
    """
    draft = _block(f"{request.system}\n{request.user}", _DRAFT_BLOCK)
    violations = [
        {"type": violation_type, "span": signal, "rationale": "fake checker 규칙표 일치"}
        for violation_type, signal in CHECKER_SIGNALS.items()
        if signal in draft
    ]
    if not violations:
        return _CHECKER_PASS
    return json.dumps({"violations": violations, "pass": False}, ensure_ascii=False)


#: R3(A.1b 최대 제약 모드)은 A.1과 같은 블록 구조를 쓰므로 기본 응답도 같다 — fixture
#: 트리거도 그대로 먹는다(위반 초안을 R3에서도 재현할 수 있어야 fallback 경로가 닫힌다).
_DYNAMIC_DEFAULTS = {
    AI2_PROMPT_KEY: _default_ai2,
    AI2_CONSTRAINED_PROMPT_KEY: _default_ai2,
    CHECKER_PROMPT_KEY: _default_checker,
}


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
        """NT-01·NT-02 leakage 검사가 보는 것 — 실제로 모델에 나간 문자열 전문."""
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
        else:
            text = _DYNAMIC_DEFAULTS[request.prompt_key](request)
        return LLMResponse(
            text=text,
            provider_reported_model=f"fake/{request.role}",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
        )
