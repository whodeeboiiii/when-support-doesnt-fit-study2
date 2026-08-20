"""integrity 규칙 계층 — 결정론 검사 (구현명세서 §6.4 R-1·R-3·R-4 + R-2 플래그).

| ID  | 검사 | 판정 | 필요한 맥락 |
|-----|------|------|-------------|
| R-1 | researcher_only·sidecar·**checkpoint 수정 전 원문**·평정·User2 유래 문자열의 등장 | 위반 | 세션 저장물 |
| R-2 | **대안 AI1 3종의 u·q segment 전문 일치** | **위반 아님 — `alt_overlap` 플래그** | dossier |
| R-3 | 질문 수 > 1 | 위반 | 출력 텍스트만 |
| R-4 | 출력 길이 상한(1,200자) 초과 | 위반 | 출력 텍스트만 |

**R-2가 v2에서 성격이 바뀌었다**(§6.4). v1의 "타 branch 문자열"은 4-branch 설계와 함께
폐기됐고, 대신 focal에 없는 segment(대안의 u·q)가 AI2 출력에 verbatim 등장하는지를 본다.
그런데 이것은 **위반이 아니다** — AI2는 공통 정책상 스스로 비슷한 조정·질문을 할 수 있고,
그게 조작 실패를 뜻하지 않는다. 그래서 재생성을 부르지 않고 `generations.alt_overlap`에
기록만 한다. 이 구분을 흐리면 정상 생성물이 fallback으로 떨어져 조작 자체가 바뀐다.

R-3·R-4는 텍스트만 보면 판정된다. R-1은 **대조 문자열**이 필요한데, 그 문자열을 이 모듈이
직접 읽지 않는다 — `llm/`은 `assets.dossier_private`를 import할 수 없다(NT-04).
호출부(`api/leakage_sources.py`)가 `ForbiddenText` 목록으로 넘긴다. 그래서 이 모듈은
"무엇이 금지인지"를 모르고 "이 문자열이 출력에 있는가"만 판정한다.

전 규칙이 **결정론**이다. 같은 입력에 같은 판정이어야 fixture 러너의 통과 기준(§10.1 결정론부
100%)이 의미를 갖는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.core.text_metrics import count_questions, split_sentences

#: §6.3 ④ · §0.5 — AI2의 clarification question 상한.
MAX_QUESTIONS = 1

#: §6.4 R-4 출력 길이 상한 (기본 1,200자 [파일럿 확정]).
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

    검출은 §6.4가 명시한 의문부호·의문형 종결 휴리스틱이다
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
# R-1 — 금지 문자열 대조 (§6.4)
# --------------------------------------------------------------------------- #

#: 대조 최소 길이 [파일럿 확정]. 짧은 조각(예: sidecar의 "네")까지 대조하면 정상 응답이
#: 통째로 위반으로 잡힌다 — 그건 dead-end 금지(§9.1)를 실질적으로 무력화한다.
MIN_LEAK_MATCH_CHARS = 8

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ForbiddenText:
    """출력에 등장하면 안 되는 문자열 1건 (R-1).

    `source`는 어디서 온 문자열인지의 **라벨**이며, 위반 detail에는 라벨만 남기고 **원문은
    남기지 않는다** — 위반 기록이 새 누출 경로가 되면 안 된다(§2.9 · §1.2).

    `whole_only`는 대조 단위를 전문으로 좁힌다. 문장 단위 대조가 과잉이 되는 값에 쓴다.
    참가자 발화(User1·User2)·sidecar·researcher_only·수정 전 원문은 개인 고유 문자열이라
    문장 단위로 본다.
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
    """R-1 — 금지 문자열이 출력에 등장하는가 (§6.4).

    `allowed`는 **이번 호출에서 모델에게 정당하게 준 것 전부**(= §6.2 allowlist를 통과한
    payload 전문)다. 거기에 이미 있는 문자열은 누출의 증거가 될 수 없으므로 대조에서 뺀다.
    §6.4의 R-1 정의가 그 예외를 명시한다 — "payload에 정당히 포함된 문자열 제외".

    이 예외가 v2에서 특히 중요한 지점은 **checkpoint 수정**이다(D-25). 참가자가 한 segment를
    고쳐도 대부분의 문장은 그대로이므로, 수정 전 원문과 수정본이 상당 부분 겹친다. effective
    checkpoint는 payload에 정당히 들어가 있으므로, 그 겹치는 문장이 R-1로 잡히면 정상
    응답이 fallback으로 떨어진다. `allowed` 대조가 그것을 막는다.

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


@dataclass(frozen=True, slots=True)
class AltSegment:
    """R-2 대조 대상 1건 — 대안 조건의 `u` 또는 `q` segment (§6.4).

    **금지 문자열이 아니다.** focal 자극에 없는 segment가 AI2 출력에 그대로 나타났다는
    사실을 기록할 뿐이고, 그 사실은 재생성을 부르지 않는다.
    """

    condition: str
    segment: str
    text: str


def flag_alt_overlap(output: str, segments: Sequence[AltSegment]) -> list[dict[str, str]]:
    """R-2 — 대안 segment의 **전문 일치**만 본다. 반환값은 `generations.alt_overlap`이다.

    전문 일치로 좁히는 이유는 §6.4의 판정 근거와 같다: AI2는 같은 정책·같은 dossier에서
    나오므로 문장 몇 개가 닮는 것은 정상이다. 그 segment가 **통째로** 나타났을 때만 기록할
    가치가 있는 사건이 된다.

    기록에는 조건 라벨이 들어간다 — `generations`는 연구자 층이고, §1.2 표에서 조건 라벨은
    콘솔·export에 허용된다. 이 값이 참가자 payload나 LLM 호출로 가는 경로는 없다.
    """
    haystack = _canonical(output)
    overlaps: list[dict[str, str]] = []
    for entry in segments:
        needle = _canonical(entry.text)
        if len(needle) >= MIN_LEAK_MATCH_CHARS and needle in haystack:
            overlaps.append({"condition": entry.condition, "segment": entry.segment})
    return overlaps


def check_all(
    output: str, forbidden: Sequence[ForbiddenText] = (), *, allowed: str = ""
) -> list[RuleViolation]:
    """§6.4 규칙 계층 전부 (R-1·R-3·R-4). 파이프라인이 부르는 단일 진입점이다.

    R-2는 여기 없다 — 위반이 아니므로 `flag_alt_overlap()`이 따로 부른다.
    """
    return [
        *check_forbidden_texts(output, forbidden, allowed=allowed),
        *check_text_rules(output),
    ]
