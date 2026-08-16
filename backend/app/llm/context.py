"""LLM payload 조립 — allowlist 강제 지점 (구현명세서 §6.2 · §1.2 · 부록 A.1·A.2).

    AI2 payload는 정확히 다음으로 구성한다: ① 시스템 프롬프트(정책, 부록 A.1)
    ② dossier `ai_visible` layer ③ 해당 branch의 User1(정규화본).
    **AI1 원문·조건 라벨·sequence·sidecar·researcher_only·타 branch·평정·사전설문은 어떤
    형태로도 포함하지 않는다** (§6.2 — 동결).

allowlist를 **시그니처로** 건다. 이 모듈의 함수들은 `AiVisible`과 문자열만 받는다 — `Dossier`
전체를 받지 않으므로 `derivation`(자극 4종·fallback·prohibited_inference·referent_map)이
실수로 프롬프트에 실릴 자리가 없다. checker만 예외적으로 `prohibited_inference`를 받는데,
그건 §6.5가 checker 입력으로 **명시 허용**한 것이다(§1.2의 판정 맥락).

`trouble_cue.form`(explicit/mitigated/…)은 렌더하지 않는다. 그 값은 대화에서 사용자가 제공한
정보가 아니라 **연구자의 코딩 라벨**이고, 조건 라벨을 넣지 않는 것과 같은 이유로 제외한다
(§6.2 "checkpoint 정보"의 범위).

⚠ 부록 A.2에는 출력 예시의 중괄호가 있다. `str.format`을 쓰면 깨지므로 **명시 치환**만 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.assets.dossier_loader import AiVisible
from app.llm import prompts

#: 부록 A.1·A.2의 블록 머리말. 프롬프트 문안과 같은 문자열이어야 한다.
CONTEXT_BLOCK = "[대화 맥락]"
MESSAGE_BLOCK = "[사용자 메시지]"
DRAFT_BLOCK = "[AI 응답 초안]"
FEEDBACK_BLOCK = "[수정 요청]"

#: A.1의 치환 자리
_AI2_PLACEHOLDERS = ("{ai_visible_context}", "{user1_normalized}")
_CHECKER_PLACEHOLDER = "{prohibited_inference}"

#: §6.5 재생성 안내 [제안]. **위반 유형만** 싣는다 — 위반 span에는 sidecar·researcher_only
#: 문자열이 들어 있을 수 있고(R-1·R-2), 그걸 되돌려 보내면 그 자체가 §1.2 위반이다.
REGENERATION_NOTICE = "직전 초안에서 다음 문제가 발견되었습니다: {types}. 위 원칙을 모두 지켜 다시 작성하세요."


class PayloadAssemblyError(RuntimeError):
    """치환되지 않은 자리·빈 필수 입력 — 조용히 보내지 않는다."""


@dataclass(frozen=True, slots=True)
class Payload:
    system: str
    user: str

    def joined(self) -> str:
        """실제로 모델에 나가는 문자열 전문 — leakage 검사(NT-01·NT-02)가 보는 대상."""
        return f"{self.system}\n{self.user}"


def render_ai_visible(ai_visible: AiVisible) -> str:
    """§6.2 ② — checkpoint 정보만. 라벨·메타는 렌더하지 않는다."""
    lines = [
        f"- 상황: {ai_visible.situation_summary}",
        f"- 사용자의 처음 요청: {ai_visible.original_request}",
        f"- 그 요청에 대한 AI의 이전 응답: {ai_visible.problematic_ai_response}",
        f"- 그 응답에 대해 사용자가 남긴 말: {ai_visible.trouble_cue.text}",
    ]
    if ai_visible.prior_evidence:
        lines.append("- 대화에서 이미 확인된 정보:")
        lines.extend(f"  · {item}" for item in ai_visible.prior_evidence)
    return "\n".join(lines)


def _split_at_context(filled: str) -> Payload:
    """정책부(system)와 자료부(user)로 나눈다.

    이어 붙이면 부록 A.1 전문 그대로다 — 문안은 한 글자도 바꾸지 않고, 채팅 API의 role 구분만
    따른다(정책은 system, 사건·발화는 user).
    """
    index = filled.find(CONTEXT_BLOCK)
    if index == -1:
        raise PayloadAssemblyError(f"프롬프트에 {CONTEXT_BLOCK} 블록이 없다 (부록 A.1)")
    return Payload(system=filled[:index].strip(), user=filled[index:].strip())


def _assert_filled(text: str, placeholders: Sequence[str]) -> None:
    for placeholder in placeholders:
        if placeholder in text:
            raise PayloadAssemblyError(f"치환되지 않은 자리: {placeholder}")


def build_ai2_payload(
    ai_visible: AiVisible,
    user1_normalized: str,
    *,
    violation_types: Sequence[str] = (),
) -> Payload:
    """§6.2 AI2 입력 3종. `violation_types`는 §6.5의 재생성 1회에서만 채워진다."""
    if not user1_normalized.strip():
        raise PayloadAssemblyError("User1이 비어 있다 — reply branch만 이 경로에 온다(§3.2)")

    filled = prompts.system_template(prompts.AI2_PROMPT_KEY)
    filled = filled.replace("{ai_visible_context}", render_ai_visible(ai_visible))
    filled = filled.replace("{user1_normalized}", user1_normalized)
    _assert_filled(filled, _AI2_PLACEHOLDERS)

    payload = _split_at_context(filled)
    if violation_types:
        notice = REGENERATION_NOTICE.format(types=", ".join(sorted(set(violation_types))))
        payload = Payload(payload.system, f"{payload.user}\n\n{FEEDBACK_BLOCK}\n{notice}")
    return payload


def build_checker_payload(
    ai_visible: AiVisible,
    user1_normalized: str,
    draft: str,
    prohibited_inference: Sequence[str] = (),
) -> Payload:
    """§6.5 checker 입력 — ai_visible + user1_normalized + 초안 (+ prohibited_inference)."""
    system = prompts.system_template(prompts.CHECKER_PROMPT_KEY).replace(
        _CHECKER_PLACEHOLDER,
        "; ".join(prohibited_inference) if prohibited_inference else "(없음)",
    )
    _assert_filled(system, (_CHECKER_PLACEHOLDER,))
    user = "\n\n".join(
        [
            f"{CONTEXT_BLOCK}\n{render_ai_visible(ai_visible)}",
            f"{MESSAGE_BLOCK}\n{user1_normalized}",
            f"{DRAFT_BLOCK}\n{draft}",
        ]
    )
    return Payload(system=system, user=user)
