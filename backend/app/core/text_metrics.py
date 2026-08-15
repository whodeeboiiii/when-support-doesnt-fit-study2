"""문자·문장·질문 수 계량 (구현명세서 §5.2 `stimuli_meta` · §6.5 R-3).

계량 규칙을 **한 곳에** 둔다. 같은 "질문 수"가 두 자리에서 쓰이기 때문이다.

- 자산 계약: `derivation.stimuli_meta`의 chars·sentences·questions가 실제 원문과 일치해야
  하고(NT-23), C1·C3은 질문 0 / C2·C4는 질문 1이어야 한다(NT-22).
- 런타임 규칙 계층: AI2 출력의 질문 수 > 1이면 R-3 위반이다(§6.5).

두 자리가 서로 다른 계산을 쓰면 "자산에서는 질문 1개인데 런타임에서는 2개"가 되어 조작
정합성이 조용히 깨진다.

⚠ 질문 검출은 §6.5가 명시한 **휴리스틱**이다 — "의문부호·의문형 종결 휴리스틱
[파일럿 확정: 검출 규칙 1회 조정 가능]". 조정 창은 §1.4의 QA·soft launch 열뿐이고,
조정하면 자산 계약 테스트(NT-22·23)를 같이 돌려야 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: 문장 종결 부호. 한국어 평서문(…다.)·의문문(…요?)·감탄(…!)과 말줄임표를 모두 종결로 본다.
_SENTENCE_END = re.compile(r"[.!?…]+")

#: 종결 부호 없이 끝나는 의문형 어미 (부호가 있으면 `?`가 이미 잡는다).
#: 보수적으로 유지한다 — 평서문을 질문으로 오탐하면 C1·C3 자극이 계약 위반으로 잡힌다.
_INTERROGATIVE_ENDING = re.compile(
    r"(나요|가요|까요|은가요|는가요|습니까|ㅂ니까|입니까|을까|ㄹ까|는지요|나\?|냐|니)$"
)

#: 문장 말미에서 떼어내는 따옴표·괄호류.
_TRAILING_WRAPPERS = "\"'”’)]》』」〉 \t"


@dataclass(frozen=True, slots=True)
class TextMetrics:
    """`stimuli_meta` 1건과 같은 모양 (§5.2 스키마)."""

    chars: int
    sentences: int
    questions: int

    def as_dict(self) -> dict[str, int]:
        return {"chars": self.chars, "sentences": self.sentences, "questions": self.questions}


def split_sentences(text: str) -> list[str]:
    """종결 부호 기준 문장 분리. 부호가 없는 마지막 조각도 한 문장으로 센다."""
    pieces: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        piece = text[start : match.end()].strip()
        if piece:
            pieces.append(piece)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return pieces


def is_question(sentence: str) -> bool:
    """문장 1개가 질문인지 — 의문부호 우선, 없으면 의문형 종결 어미(§6.5 휴리스틱)."""
    stripped = sentence.strip().rstrip(_TRAILING_WRAPPERS)
    if stripped.endswith("?"):
        return True
    body = stripped.rstrip(".!…" + _TRAILING_WRAPPERS)
    return bool(_INTERROGATIVE_ENDING.search(body))


def count_chars(text: str) -> int:
    """문자 수 — 앞뒤 공백만 제거하고 내부 공백·줄바꿈은 그대로 센다."""
    return len(text.strip())


def count_sentences(text: str) -> int:
    return len(split_sentences(text))


def count_questions(text: str) -> int:
    return sum(1 for sentence in split_sentences(text) if is_question(sentence))


def measure(text: str) -> TextMetrics:
    sentences = split_sentences(text)
    return TextMetrics(
        chars=count_chars(text),
        sentences=len(sentences),
        questions=sum(1 for sentence in sentences if is_question(sentence)),
    )
