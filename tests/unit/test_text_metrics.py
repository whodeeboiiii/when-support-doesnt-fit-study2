"""문자·문장·질문 계량 규칙 (§5.2 `stimuli_meta` · §6.5 R-3).

자산 계약(NT-22·NT-23)과 런타임 규칙(R-3)이 같은 함수를 쓰므로, 이 규칙이 흔들리면 두 곳이
한꺼번에 흔들린다. 그래서 규칙 자체를 여기서 고정한다 — 조정은 [파일럿 확정] 창에서만.
"""

from __future__ import annotations

import pytest

from app.core.text_metrics import count_questions, count_sentences, measure
from app.llm.integrity_rules import MAX_OUTPUT_CHARS, check_text_rules


def test_plain_statement_has_no_question() -> None:
    assert count_questions("장기 계획까지 간 건 지금 요청하신 범위를 넘었네요.") == 0


def test_question_mark_counts() -> None:
    text = "지금은 두 선택지의 장단점을 더 정리하는 것과 결정 기준을 좁히는 것 중 어느 쪽이 더 필요하세요?"
    assert count_questions(text) == 1


def test_interrogative_ending_without_question_mark_counts() -> None:
    """§6.5 휴리스틱 — 의문부호가 없어도 의문형 종결은 질문으로 센다."""
    assert count_questions("어느 쪽이 더 도움이 될까요") == 1


def test_two_questions_are_counted_separately() -> None:
    assert count_questions("지금 무엇이 필요하세요? 다음은 어떻게 할까요?") == 2


def test_sentence_split_handles_trailing_fragment() -> None:
    assert count_sentences("첫 문장이다. 둘째 문장이다") == 2


def test_measure_matches_component_counts() -> None:
    text = "받았습니다. 이어서 볼까요?"
    metrics = measure(text)
    assert metrics.as_dict() == {"chars": len(text), "sentences": 2, "questions": 1}


def test_r3_flags_more_than_one_question() -> None:
    violations = check_text_rules("이건 어떠세요? 저건 어떠세요?")
    assert [violation.rule for violation in violations] == ["R-3"]


def test_r3_allows_exactly_one_question() -> None:
    assert check_text_rules("말씀하신 범위 안에서 정리해볼게요. 이렇게 진행할까요?") == []


def test_r4_flags_overlong_output() -> None:
    violations = check_text_rules("가" * (MAX_OUTPUT_CHARS + 1))
    assert [violation.rule for violation in violations] == ["R-4"]


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_is_measurable(text: str) -> None:
    assert measure(text).as_dict() == {"chars": 0, "sentences": 0, "questions": 0}
