"""integrity 규칙 계층 — 결정론 검사 (구현명세서 §6.5 R-1–R-4).

| ID  | 검사 | 필요한 맥락 |
|-----|------|-------------|
| R-1 | researcher_only·sidecar 유래 문자열의 출력 내 등장 | 해당 branch의 저장물 (NS3) |
| R-2 | 타 branch User1/AI2 문자열의 등장 | 세션의 다른 branch (NS3) |
| R-3 | 질문 수 > 1 | 출력 텍스트만 |
| R-4 | 출력 길이 상한(1,200자) 초과 | 출력 텍스트만 |

**NS1에서는 R-3·R-4만 구현한다.** 두 규칙은 텍스트만 보면 판정되고, 자산 계약 테스트
NT-21(전 dossier의 `neutral_fallback`이 R-3·R-4를 통과)이 지금 필요하기 때문이다.
R-1·R-2는 branch 저장물을 입력으로 받으므로 NS3(§6.5 파이프라인)에서 이 모듈에 추가한다.

⚠ R-1을 구현할 때 **researcher_only 층을 이 모듈이 직접 로드하지 않는다.** 대조 문자열은
호출부(파이프라인)가 넘긴다 — `llm/`은 `assets.dossier_private`를 import할 수 없다(NT-04).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.text_metrics import count_questions

#: §6.3-4 · §0.5 — AI2의 clarification question 상한.
MAX_QUESTIONS = 1

#: §6.5 R-4 출력 길이 상한 (기본 1,200자 [파일럿 확정]).
MAX_OUTPUT_CHARS = 1_200


@dataclass(frozen=True, slots=True)
class RuleViolation:
    """§8.1 `generations.rule_violations`에 그대로 들어가는 모양."""

    rule: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "detail": self.detail}


def check_question_count(text: str) -> RuleViolation | None:
    """R-3 — 질문 수 > 1이면 위반.

    검출은 §6.5가 명시한 의문부호·의문형 종결 휴리스틱이다
    [파일럿 확정: 검출 규칙 1회 조정 가능] — 규칙 본체는 `core/text_metrics.py`에 있다.
    """
    count = count_questions(text)
    if count > MAX_QUESTIONS:
        return RuleViolation("R-3", f"질문 {count}개 — 상한 {MAX_QUESTIONS}개")
    return None


def check_length(text: str) -> RuleViolation | None:
    """R-4 — 출력 길이 상한 초과."""
    length = len(text.strip())
    if length > MAX_OUTPUT_CHARS:
        return RuleViolation("R-4", f"{length}자 — 상한 {MAX_OUTPUT_CHARS}자")
    return None


def check_text_rules(text: str) -> list[RuleViolation]:
    """텍스트만으로 판정 가능한 규칙(R-3·R-4) 전부.

    `neutral_fallback` 자산 검사(NT-21)와 AI2 출력 검사(NS3)가 같은 함수를 쓴다 — 자산이
    통과한 규칙과 런타임이 적용하는 규칙이 갈라지지 않게 한다(§6.6).
    """
    return [
        violation
        for violation in (check_question_count(text), check_length(text))
        if violation is not None
    ]
