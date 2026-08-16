"""화면 문안 대조 (구현명세서 §0.4 "윤문 금지" · §4 · §7.3 · §9.1).

§11.1 NS2의 완료 기준 중 하나가 "문안 [정본] 항목 초안 대조"다. 사람이 눈으로 하는 대조를
기계가 대신한다 — 대조 기준은 리포에 함께 있는 `docs/구현명세서_v1.0.1.md`이고, 명세서가
개정되면 이 테스트가 먼저 깨져서 자산 동기화를 강제한다.

[정본]과 [제안]을 나눠 검사하는 이유: 둘 다 지금은 명세서 원문과 일치해야 하지만, 어긋났을 때
할 일이 다르다. [정본]이 어긋나면 **코드를 되돌린다**(윤문 금지). [제안]이 어긋나면 PI 승인
이력을 확인하고 명세서·코드를 함께 고친다(§1.4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.assets import rating_items, screen_copy

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_TEXT = (REPO_ROOT / "docs" / "구현명세서_v1.0.1.md").read_text(encoding="utf-8")

#: **[정본]** — 논문 초안 수록 원문. 윤문 금지(§0.4).
CANONICAL = {
    "sidecar 질문(reply)": screen_copy.SIDECAR_QUESTION_REPLY,
    "sidecar 질문(no_reply·end)": screen_copy.SIDECAR_QUESTION_NO_REPLY,
    "sidecar '있음' 안내": screen_copy.SIDECAR_HAS_NOTICE,
    "sidecar 관련성 평정": screen_copy.SIDECAR_RELEVANCE_QUESTION,
}

#: [제안] — PI 승인 대상. 현재는 명세서 본문이 유일한 출처다.
PROPOSED = {
    "P0 검증 실패": screen_copy.JOIN_FAILED,
    "P0 데스크톱 가드": screen_copy.DESKTOP_ONLY,
    "P3 안내": screen_copy.CHECKPOINT_INTRO,
    "P4 재진입 안내": screen_copy.BRANCH_REENTRY,
    "P5 답장하지 않기": screen_copy.NO_REPLY_BUTTON,
    "P5 대화 종료": screen_copy.END_BUTTON,
    "P6 전환 안내": screen_copy.SIDECAR_TRANSITION,
    "P6 미전송 이유": screen_copy.SIDECAR_REASON_PROMPT,
    "P7 로딩": screen_copy.AI2_LOADING,
    "P8 지시": screen_copy.DOWNSTREAM_INSTRUCTION,
    "P9 블록 1 지시": screen_copy.RATINGS_BLOCK1_INSTRUCTION,
    "P9 블록 2 지시": screen_copy.RATINGS_BLOCK2_INSTRUCTION,
    "P9 척도 하단": screen_copy.RATINGS_SCALE_MIN_LABEL,
    "P9 척도 상단": screen_copy.RATINGS_SCALE_MAX_LABEL,
    "P10 종료 버튼": screen_copy.CROSS_REVIEW_END_BUTTON,
    "§9.1 AI2 지연": screen_copy.AI2_DELAYED,
    "§9.1 저장 실패": screen_copy.SAVE_FAILED,
    "§9.1 복구": screen_copy.RESTORING,
    "§9.1 코드 만료": screen_copy.CODE_EXPIRED,
    "§9.1 abort": screen_copy.SESSION_ABORTED,
}


@pytest.mark.parametrize("label,text", sorted(CANONICAL.items()))
def test_canonical_copy_matches_spec(label: str, text: str) -> None:
    assert text in SPEC_TEXT, f"[정본] {label}: 명세서 원문과 다르다 (윤문 금지 — §0.4)"


@pytest.mark.parametrize("label,text", sorted(PROPOSED.items()))
def test_proposed_copy_matches_spec(label: str, text: str) -> None:
    assert text in SPEC_TEXT, f"[제안] {label}: 명세서 문안과 다르다 (§1.4 변경 절차)"


@pytest.mark.parametrize("item", rating_items.RATING_ITEMS, ids=lambda item: item.item_id)
def test_rating_item_row_matches_the_spec_table(item: rating_items.RatingItem) -> None:
    """§7.3 표의 한 행 전체 — 번호·변수명·원문이 **같이** 맞아야 한다."""
    row = f"| {item.number} | `{item.item_id}` | {item.text} |"
    assert row in SPEC_TEXT, f"§7.3 표와 다르다: {row}"


def test_twelve_items_two_blocks() -> None:
    """§4.9·D-22 — 12문항, 블록 1은 문항 1·2, 블록 2는 문항 3–12."""
    assert rating_items.ITEM_COUNT == 12
    anchor = rating_items.items_in_block(rating_items.BLOCK_ANCHOR)
    interaction = rating_items.items_in_block(rating_items.BLOCK_INTERACTION)
    assert [item.number for item in anchor] == [1, 2]
    assert [item.number for item in interaction] == list(range(3, 13))
    assert [item.item_id for item in anchor] == ["recognition", "substantive_uptake"]


def test_scale_is_one_to_seven() -> None:
    """§0.5 — 평정 척도 1–7."""
    assert (rating_items.SCALE_MIN, rating_items.SCALE_MAX) == (1, 7)
    assert rating_items.is_valid_value(1) and rating_items.is_valid_value(7)
    assert not rating_items.is_valid_value(0)
    assert not rating_items.is_valid_value(8)
    assert not rating_items.is_valid_value(True), "bool은 척도값이 아니다"


def test_downstream_codes_are_the_seven_fixed_codes() -> None:
    """§4.8 — 영문 코드 고정, 7종. 라벨은 [제안]."""
    assert screen_copy.DOWNSTREAM_CODES == (
        "continue_reply",
        "correct_reformulate",
        "pause",
        "end",
        "new_chat",
        "switch_ai",
        "seek_human",
    )
    for option in screen_copy.DOWNSTREAM_OPTIONS:
        # §4.8은 라벨과 코드를 붙여서 적는다 — "① 이어서 답장한다 `continue_reply`"
        assert f"{option.label} `{option.code}`" in SPEC_TEXT, f"§4.8과 다르다: {option.label}"


def test_sidecar_choices_are_the_three_spec_options() -> None:
    """§4.6 — 없음 / 있음 / 건너뛰기 → 저장값 none/has/skip(§8.1)."""
    assert [value for value, _ in screen_copy.SIDECAR_CHOICES] == ["none", "has", "skip"]
    assert [label for _, label in screen_copy.SIDECAR_CHOICES] == ["없음", "있음", "건너뛰기"]
    assert "선택지: 없음 / 있음 / 건너뛰기" in SPEC_TEXT


def test_no_normative_vocabulary_in_sidecar_copy() -> None:
    """§4.6 금지 — "AI가 알아야 했던"·"말했어야 했던"·"빠뜨린" 류 규범적 표현(§1.5-6)."""
    sidecar_copy = " ".join(
        [
            screen_copy.SIDECAR_TRANSITION,
            screen_copy.SIDECAR_QUESTION_REPLY,
            screen_copy.SIDECAR_QUESTION_NO_REPLY,
            screen_copy.SIDECAR_HAS_NOTICE,
            screen_copy.SIDECAR_RELEVANCE_QUESTION,
            screen_copy.SIDECAR_REASON_PROMPT,
        ]
    )
    for banned in ("알아야 했", "말했어야", "빠뜨린", "누락"):
        assert banned not in sidecar_copy, f"규범적 표현: {banned}"


def test_participant_copy_never_names_conditions() -> None:
    """§4.4·§4.10 — 조건명·구성 원리는 참가자 화면에 없다."""
    # 주석·docstring은 조건을 언급할 수 있으므로 **문자열 상수만** 본다.
    strings = [
        value
        for name, value in vars(screen_copy).items()
        if isinstance(value, str) and not name.startswith("__")
    ]
    assert len(strings) > 20, "검사 대상 문안이 사라졌다"
    for text in strings:
        for banned in ("C1", "C2", "C3", "C4", "uptake", "elicitation", "조건"):
            assert banned not in text, f"참가자 문안에 조작이 노출됐다: {text!r}"


def test_p9_instructions_do_not_reveal_branch_number() -> None:
    """§4.4 — branch 번호·조건명 비표시. 라벨 템플릿은 서식만 갖는다."""
    assert "{index}" in screen_copy.CROSS_REVIEW_BRANCH_LABEL
    assert "branch" not in screen_copy.CROSS_REVIEW_BRANCH_LABEL.lower()
