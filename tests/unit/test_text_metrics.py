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


def test_declarative_ending_is_not_a_question_even_with_interrogative_morpheme() -> None:
    """§6.5 [파일럿 확정 2026-08-27] — 평서 종결 부호로 끝나면 질문이 아니다.

    `냐|니` 어미가 아무 단어 끝에나 걸려서 평서문이 질문으로 잡혔다. P23 세션의 R-3
    오탐이 이 경로였고 결과는 재생성 1회 + neutral_fallback이다.
    """
    for sentence in ("커피를 마시면 잠이 살아나요.", "어머니.", "그러니.", "도움이 될 거니.", "정리해 봤어요!"):
        assert count_questions(sentence) == 0, sentence


def test_unpunctuated_question_still_counts() -> None:
    """오탐만 죽인다 — 부호 없는 진짜 질문의 검출(recall)은 그대로다."""
    assert count_questions("커피를 마시면 잠이 깨나요") == 1
    assert count_questions("지금 필요한 게 무엇인가요") == 1


def test_declarative_fix_does_not_move_any_locked_asset() -> None:
    """규칙 조정의 조건: 자산 계약(NT-22·23)이 한 건도 움직이지 않아야 한다.

    `stimuli_meta`는 lock된 파일에 적힌 숫자다 — 계량 규칙이 바뀌어 이 숫자와 어긋나면
    기동 게이트가 전 dossier를 거부한다. 그래서 규칙을 고칠 때마다 여기서 전수 대조한다.
    """
    from app.assets import dossier_loader, files

    for participant_no in files.available_participant_numbers():
        dossier = dossier_loader.load(participant_no)
        for condition in dossier_loader.CONDITIONS:
            assert (
                count_questions(dossier.assemble(condition))
                == dossier.stimulus.stimuli_meta[condition].questions
            ), f"{participant_no}/{condition}"
        assert count_questions(dossier.stimulus.neutral_fallback) == 0, participant_no


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
