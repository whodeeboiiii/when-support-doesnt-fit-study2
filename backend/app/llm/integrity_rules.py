"""integrity 규칙 계층 — 결정론 검사 (구현명세서 §6.5 R-1–R-4).

| ID  | 검사 | 필요한 맥락 |
|-----|------|-------------|
| R-1 | researcher_only·sidecar 유래 문자열의 출력 내 등장 | 해당 branch의 저장물 (NS3) |
| R-2 | 타 branch User1/AI2 문자열의 등장 | 세션의 다른 branch (NS3) |
| R-3 | 질문 수 > 1 | 출력 텍스트만 |
| R-4 | 출력 길이 상한(1,200자) 초과 | 출력 텍스트만 |

R-3·R-4는 텍스트만 보면 판정된다. R-1·R-2는 **대조 문자열**이 필요한데, 그 문자열을 이
모듈이 직접 읽지 않는다 — `llm/`은 `assets.dossier_private`를 import할 수 없고(NT-04) 타
branch 저장물을 조회할 수도 없다. 호출부(§6.1 파이프라인의 진입점, `api/leakage_sources.py`)가
`ForbiddenText` 목록으로 넘긴다. 그래서 이 모듈은 "무엇이 금지인지"를 모르고 "이 문자열이
출력에 있는가"만 판정한다.

전 규칙이 **결정론**이다. 같은 입력에 같은 판정이어야 fixture 러너의 통과 기준(§10.1 결정론부
100%)이 의미를 갖는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.core.text_metrics import count_questions, split_sentences

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

    `neutral_fallback` 자산 검사(NT-21)와 AI2 출력 검사가 같은 함수를 쓴다 — 자산이 통과한
    규칙과 런타임이 적용하는 규칙이 갈라지지 않게 한다(§6.6).
    """
    return [
        violation
        for violation in (check_question_count(text), check_length(text))
        if violation is not None
    ]


# --------------------------------------------------------------------------- #
# R-1 · R-2 — 금지 문자열 대조 (§6.5)
# --------------------------------------------------------------------------- #

#: 대조 최소 길이 [파일럿 확정]. 짧은 조각(예: sidecar의 "네")까지 대조하면 정상 응답이
#: 통째로 위반으로 잡힌다 — 그건 dead-end 금지(§9.1)를 실질적으로 무력화한다.
MIN_LEAK_MATCH_CHARS = 8

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ForbiddenText:
    """출력에 등장하면 안 되는 문자열 1건.

    `rule`은 R-1(researcher_only·sidecar) 또는 R-2(타 branch)다. `source`는 어디서 온
    문자열인지의 **라벨**이며, 위반 detail에는 라벨만 남기고 **원문은 남기지 않는다** —
    위반 기록이 새 누출 경로가 되면 안 된다(§2.9 · §1.2).

    `whole_only`는 대조 단위를 전문으로 좁힌다. **타 branch의 AI2 출력**에 쓴다: 네 branch의
    AI2는 같은 정책 프롬프트(부록 A.1)와 같은 dossier에서 나오므로 문장 몇 개가 겹치는 것은
    격리 실패가 아니라 **동일 정책의 정상 결과**다. 그걸 위반으로 세면 정상 생성물이
    fallback으로 떨어져 조작이 바뀐다. 참가자 발화(User1)·sidecar·researcher_only는 반대로
    branch·개인 고유 문자열이므로 문장 단위로 본다.
    """

    rule: str
    source: str
    text: str
    whole_only: bool = False


def _canonical(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _needles(text: str, *, whole_only: bool = False) -> list[str]:
    """대조 단위 — 전문 + 문장 단위. 문장 하나만 옮겨 붙은 부분 누출도 잡는다."""
    canonical = _canonical(text)
    candidates = [canonical]
    if not whole_only:
        candidates.extend(_canonical(piece) for piece in split_sentences(canonical))
    return [piece for piece in dict.fromkeys(candidates) if len(piece) >= MIN_LEAK_MATCH_CHARS]


def check_forbidden_texts(
    output: str, forbidden: Sequence[ForbiddenText], *, allowed: str = ""
) -> list[RuleViolation]:
    """R-1·R-2 — 금지 문자열이 출력에 등장하는가.

    `allowed`는 **이번 호출에서 모델에게 정당하게 준 것 전부**(= §6.2 allowlist를 통과한
    payload 전문)다. 거기에 이미 있는 문자열은 누출의 증거가 될 수 없으므로 대조에서 뺀다.

    이 조정이 필요한 이유는 실제 세션에서 자주 일어나는 일 때문이다: 참가자가 두 branch에서
    **같은 말을 반복하면** 이번 branch의 User1과 타 branch의 User1이 같은 문자열이 된다.
    그때 AI2가 이번 User1을 그대로 되짚는 정상 응답이 R-2로 잡히고, 재생성해도 같은 이유로
    잡혀 fallback으로 떨어진다 — 조작 자체가 바뀐다(§6.6은 fallback을 예외 경로로 설계했다).
    R-2가 잡으려는 것은 **타 branch에서만 올 수 있는** 문자열이다(§3.4 격리).

    한 source가 여러 문장에서 걸려도 위반 1건으로 접는다 — 같은 사실을 여러 번 세지 않는다.
    """
    haystack = _canonical(output)
    permitted = _canonical(allowed)
    violations: list[RuleViolation] = []
    for entry in forbidden:
        needles = [
            needle
            for needle in _needles(entry.text, whole_only=entry.whole_only)
            if needle not in permitted
        ]
        if any(needle in haystack for needle in needles):
            violations.append(
                RuleViolation(entry.rule, f"{entry.source} 문자열이 출력에 등장했다")
            )
    return violations


def check_all(
    output: str, forbidden: Sequence[ForbiddenText] = (), *, allowed: str = ""
) -> list[RuleViolation]:
    """§6.5 규칙 계층 전부 (R-1–R-4). 파이프라인이 부르는 단일 진입점이다."""
    return [
        *check_forbidden_texts(output, forbidden, allowed=allowed),
        *check_text_rules(output),
    ]
