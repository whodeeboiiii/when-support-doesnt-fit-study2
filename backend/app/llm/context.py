"""LLM payload 조립 — allowlist 강제 지점 (구현명세서 §6.2 · §1.2 · 부록 A.1·A.2).

    AI2 payload = ① 시스템 프롬프트(부록 A.1 v2 — 전 조건·전 참가자 동일)
    ② **effective checkpoint**(참가자 수정 반영 ai_visible) ③ **focal AI1 원문**
    ④ **User1 원문**. 조건 라벨·R/U/Q 구분·대안 AI1·sidecar·researcher_only·
    evidence_code(prohibited_inference 제외)·배정표·평정·User2는 어떤 형태로도 포함하지
    않는다 (§6.2 — 동결, D-34).

**v1.0.1과 정반대인 지점이 둘 있다.**

1. **focal AI1 원문이 payload에 들어간다.** v1은 "AI1 원문 금지 + normalization으로 지시
   복원"이었지만, v2는 AI1을 직접 준다(D-34). 그래서 `normalization.py`가 삭제됐다 —
   지시 대상이 payload 안에 있으므로 복원할 것이 없다.
2. **checkpoint는 수정본이다.** 참가자가 P2에서 고친 값이 정본이고, **수정 전 원문은
   금지**다(§1.2 표). 그 원문은 오히려 R-1의 금지 문자열이다(§6.4).

allowlist를 **시그니처로** 건다(§6.2 — "시그니처가 allowlist다"). 이 모듈의 함수들은
`EffectiveAiVisible`과 문자열만 받는다:

- `Dossier` 전체를 받지 않으므로 `stimulus`(대안 segment)·`evidence_code`가 실수로
  프롬프트에 실릴 자리가 없다.
- `AiVisible`(원문)이 아니라 `EffectiveAiVisible`을 받으므로, 원문을 넘기는 호출은 타입이
  맞지 않는다(NT-01 개정).
- checker만 예외적으로 `prohibited_inference`를 받는데, 그건 §6.4가 checker 입력으로
  **명시 허용**한 것이다.

⚠ 부록 A.2에는 출력 예시의 중괄호가 있다. `str.format`을 쓰면 깨지므로 **명시 치환**만 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.assets.dossier_loader import EffectiveAiVisible
from app.llm import prompts

#: 부록 A.1·A.2의 블록 머리말. 프롬프트 문안과 같은 문자열이어야 한다.
CONTEXT_BLOCK = "[대화 맥락]"
PRIOR_AI_BLOCK = "[AI의 직전 답변]"
MESSAGE_BLOCK = "[사용자 메시지]"
DRAFT_BLOCK = "[AI 응답 초안]"
FEEDBACK_BLOCK = "[수정 요청]"

#: A.1 v2의 치환 자리 — `{user1_normalized}`가 `{user1}`로, `{focal_ai1}`가 신설(D-34).
_AI2_PLACEHOLDERS = ("{ai_visible_context}", "{focal_ai1}", "{user1}")
_CHECKER_PLACEHOLDER = "{prohibited_inference}"

#: §6.4 재생성 안내 [제안]. **위반 유형만** 싣는다 — 위반 span에는 sidecar·researcher_only·
#: 수정 전 원문이 들어 있을 수 있고(R-1), 그걸 되돌려 보내면 그 자체가 §1.2 위반이다.
REGENERATION_NOTICE = (
    "직전 초안에서 다음 문제가 발견되었습니다: {types}. 위 원칙을 모두 지켜 다시 작성하세요."
)


class PayloadAssemblyError(RuntimeError):
    """치환되지 않은 자리·빈 필수 입력 — 조용히 보내지 않는다."""


@dataclass(frozen=True, slots=True)
class Payload:
    system: str
    user: str

    def joined(self) -> str:
        """실제로 모델에 나가는 문자열 전문 — leakage 검사(NT-01·NT-02)가 보는 대상."""
        return f"{self.system}\n{self.user}"


def render_ai_visible(effective: EffectiveAiVisible) -> str:
    """§6.2 ② — checkpoint 정보만, **전부 effective(수정본)**.

    부록 A.1의 렌더 형식(승계): 상황 / 대화에서 이미 확인된 정보 / 사용자의 처음 요청 /
    그 요청에 대한 AI의 이전 응답 / 그 응답에 대해 사용자가 남긴 말.

    `provenance`·`excerpt_note`는 렌더하지 않는다 — 연구자 코딩 메타이지 대화에서 사용자가
    제공한 정보가 아니다(조건 라벨을 넣지 않는 것과 같은 이유).
    """
    lines = [f"- 상황: {effective.situation_summary}"]
    if effective.prior_evidence:
        lines.append("- 대화에서 이미 확인된 정보:")
        lines.extend(f"  · {item}" for item in effective.prior_evidence)
    lines += [
        f"- 사용자의 처음 요청: {effective.original_request}",
        f"- 그 요청에 대한 AI의 이전 응답: {effective.problematic_ai_response}",
        f"- 그 응답에 대해 사용자가 남긴 말: {effective.trouble_cue}",
    ]
    return "\n".join(lines)


def _split_at_context(filled: str) -> Payload:
    """정책부(system)와 자료부(user)로 나눈다.

    이어 붙이면 부록 A.1 전문 그대로다 — 문안은 한 글자도 바꾸지 않고, 채팅 API의 role 구분만
    따른다(정책은 system, 사건·발화는 user).

    ⚠ 경계는 **줄 첫머리에 홀로 선 블록 머리말**이다. A.1 v2의 첫 문단은 본문 안에서
    "아래 [대화 맥락]은 …"으로 같은 문자열을 언급한다 — 단순 `find`로 자르면 그 언급에서
    끊겨 **원칙 1–5가 통째로 user로 넘어간다**(system은 첫 문장 조각만 남는다).
    """
    match = re.search(rf"^{re.escape(CONTEXT_BLOCK)}$", filled, re.MULTILINE)
    if match is None:
        raise PayloadAssemblyError(
            f"프롬프트에 {CONTEXT_BLOCK} 블록(줄 단독)이 없다 (부록 A.1)"
        )
    return Payload(system=filled[: match.start()].strip(), user=filled[match.start() :].strip())


def _assert_filled(text: str, placeholders: Sequence[str]) -> None:
    for placeholder in placeholders:
        if placeholder in text:
            raise PayloadAssemblyError(f"치환되지 않은 자리: {placeholder}")


def build_ai2_payload(
    effective: EffectiveAiVisible,
    focal_ai1: str,
    user1: str,
    *,
    violation_types: Sequence[str] = (),
) -> Payload:
    """§6.2 AI2 입력 3종 (D-34). `violation_types`는 §6.4의 재생성 1회에서만 채워진다.

    시그니처가 곧 allowlist다 — 인자가 셋뿐이므로 여기 없는 정보는 payload에 실릴 방법이 없다.
    """
    if not user1.strip():
        raise PayloadAssemblyError("User1이 비어 있다 — User1은 필수다(§4.4 · D-32)")
    if not focal_ai1.strip():
        raise PayloadAssemblyError("focal AI1이 비어 있다 — 조립된 자극이 필요하다(§5.4)")

    filled = prompts.system_template(prompts.AI2_PROMPT_KEY)
    filled = filled.replace("{ai_visible_context}", render_ai_visible(effective))
    filled = filled.replace("{focal_ai1}", focal_ai1)
    filled = filled.replace("{user1}", user1)
    _assert_filled(filled, _AI2_PLACEHOLDERS)

    payload = _split_at_context(filled)
    if violation_types:
        notice = REGENERATION_NOTICE.format(types=", ".join(sorted(set(violation_types))))
        payload = Payload(payload.system, f"{payload.user}\n\n{FEEDBACK_BLOCK}\n{notice}")
    return payload


def build_checker_payload(
    effective: EffectiveAiVisible,
    focal_ai1: str,
    user1: str,
    draft: str,
    prohibited_inference: Sequence[str] = (),
) -> Payload:
    """§6.4 checker 입력 — effective + focal AI1 + User1 + 초안 (+ prohibited_inference).

    허용 목록이 정확히 이 다섯이다(NT-02). 초안은 판정 대상이므로 당연히 들어가고,
    `prohibited_inference`는 §6.4가 명시 허용한 유일한 evidence_code 필드다.
    """
    system = prompts.system_template(prompts.CHECKER_PROMPT_KEY).replace(
        _CHECKER_PLACEHOLDER,
        "; ".join(prohibited_inference) if prohibited_inference else "(없음)",
    )
    _assert_filled(system, (_CHECKER_PLACEHOLDER,))
    user = "\n\n".join(
        [
            f"{CONTEXT_BLOCK}\n{render_ai_visible(effective)}",
            f"{PRIOR_AI_BLOCK}\n{focal_ai1}",
            f"{MESSAGE_BLOCK}\n{user1}",
            f"{DRAFT_BLOCK}\n{draft}",
        ]
    )
    return Payload(system=system, user=user)
