"""화면 문안 [정본] 대조 (구현명세서 §4 · §0.4 "윤문 금지" · 부록 D.1 마지막 줄).

**[정본] 7건**(§4.2 checkpoint 안내 · §4.4 User1 지시 · §4.5 sidecar 3단 · §5.5 P00 R/U/Q)이
동결 대상이다. 이 파일은 앞의 다섯(화면 문안)을 보고, P00 자극 3종은 dossier 자산이라
`test_p00_canonical_text.py`가 본다.

대조 대상은 **명세서 파일 자체**다. 상수를 테스트에 복사하면 "복사본끼리 일치"만 확인하게
되고, 명세서가 개정될 때 코드가 따라가지 않는다.

[제안] 문안은 글자 대조를 걸지 않는다 — PI 승인 대상이라 바뀔 수 있다. 대신 **금지 표현이
없는지**를 본다(§4.5 규범 어휘 금지, §4 서두 조건 라벨 금지).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.assets import screen_copy

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "구현명세서_v2.0.md"


@pytest.fixture(scope="module")
def spec() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    """명세서는 인용 블록(`> `)에서 줄바꿈으로 접어 놓는다 — 공백만 정규화해 대조한다."""
    return re.sub(r"\s+", " ", text.replace("> ", " ")).strip()


# --------------------------------------------------------------------------- #
# [정본] 5건 — 화면 문안
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("constant", "marker"),
    [
        (screen_copy.CHECKPOINT_VERIFY_INTRO, "다음은 이전에 말씀해주신"),
        (screen_copy.USER1_INSTRUCTION, "이 연구에서는 대화를 한 번 더"),
        (screen_copy.SIDECAR_Q1, "방금 보낸 답장에는 포함하지 않았지만"),
        (screen_copy.SIDECAR_Q2, "그 생각이나 정보는 방금 답장을"),
        (screen_copy.SIDECAR_Q3, "답장에 그 내용을 넣지 않은 이유가"),
    ],
)
def test_canonical_copy_matches_spec(constant: str, marker: str, spec: str) -> None:
    """[정본] — 명세서 원문과 글자 그대로. 윤문 0건(§0.4 동결)."""
    normalized_spec = _normalize(spec)
    assert _normalize(constant) in normalized_spec, (
        f"[정본] 문안이 명세서와 다르다 — 시작: {constant[:24]!r}"
    )
    assert marker in constant, "대조 대상이 바뀌었는지 확인하라"


def test_canonical_copy_registry_has_five_screen_items() -> None:
    """부록 H.2가 지정한 [정본] 상수명 5종이 전부 등록돼 있다."""
    assert len(screen_copy.CANONICAL_COPY) == 5
    assert screen_copy.CHECKPOINT_VERIFY_INTRO in screen_copy.CANONICAL_COPY
    assert screen_copy.SIDECAR_Q3 in screen_copy.CANONICAL_COPY


def test_checkpoint_intro_keeps_the_private_thought_clause() -> None:
    """§4.2 — "속마음을 다시 설명하지 않으셔도 됩니다"는 §3.4가 명시적으로 의지하는 문장이다."""
    assert "속마음을 다시 설명하지 않으셔도 됩니다" in screen_copy.CHECKPOINT_VERIFY_INTRO


# --------------------------------------------------------------------------- #
# 금지 표현 (§4 서두 · §4.2 · §4.5 · §1.5)
# --------------------------------------------------------------------------- #


def _all_participant_copy() -> str:
    """참가자 화면에 나갈 수 있는 문자열 전부."""
    pieces: list[str] = []
    for name in dir(screen_copy):
        if name.startswith("_"):
            continue
        value = getattr(screen_copy, name)
        if isinstance(value, str):
            pieces.append(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                if isinstance(item, str):
                    pieces.append(item)
                elif isinstance(item, tuple):
                    pieces.extend(str(part) for part in item)
                elif hasattr(item, "label"):
                    pieces.append(item.label)
        elif isinstance(value, dict):
            pieces.extend(str(item) for item in value.values())
    return "\n".join(pieces)


@pytest.mark.parametrize(
    "banned",
    [
        # §4 서두 — 조건명·구성 원리 비공개
        "C1",
        "C2",
        "C3",
        "C4",
        "uptake",
        "elicitation",
        "recognition segment",
        "focal",
        "actionability",
        # §4.5 — sidecar 규범 어휘 금지(§1.5-7)
        "빠뜨린",
        "알아야 했던",
        "말했어야",
        "withholding",
        # §4.2 · 부록 D.3 — 선호 재활성화 질문 금지
        "무엇을 원했",
        "뭘 원했",
    ],
)
def test_participant_copy_has_no_banned_expression(banned: str) -> None:
    """§4 서두 · §4.2 · §4.5 — 이 문자열이 생기면 그건 조작 노출이거나 규범 유도다."""
    assert banned not in _all_participant_copy()


def test_alt_exposure_label_has_no_condition_name() -> None:
    """§4.9 — 라벨은 "다른 응답 1/2/3"이고 조건명이 없다."""
    label = screen_copy.ALT_EXPOSURE_LABEL.format(position=1)
    assert label == "다른 응답 1"


def test_pairwise_labels_are_positions_not_conditions() -> None:
    """§4.10 — 「응답 A」(좌)·「응답 B」(우). 어느 쪽이 focal인지 라벨링하지 않는다."""
    assert screen_copy.PAIRWISE_SIDE_LABELS == ("응답 A", "응답 B")


# --------------------------------------------------------------------------- #
# 구조 — v2에서 바뀐 것들
# --------------------------------------------------------------------------- #


def test_consent_has_six_items_including_alternative_exposure() -> None:
    """§4.1 — 항목 키 6종. ⑥ `alternative_exposure`가 v2 신설이다."""
    fields = [item.field for item in screen_copy.CONSENT_ITEMS]
    assert fields == [
        "participation",
        "study1_data_use",
        "recording",
        "overseas_transfer",
        "withdrawal_and_compensation",
        "alternative_exposure",
    ]


def test_sidecar_provenance_choices_are_three(spec: str) -> None:
    """§4.5 · §7.3 — preexisting / prompt_evoked / uncertain. 4범주는 **사후 코딩**이다."""
    values = [value for value, _label in screen_copy.SIDECAR_PROVENANCE_CHOICES]
    assert values == ["preexisting", "prompt_evoked", "uncertain"]
    # deliberate withholding은 시스템 값이 아니다(§1.5-7).
    assert "deliberate" not in _all_participant_copy()


def test_sidecar_third_step_only_for_preexisting() -> None:
    """§4.5 — 3단은 `preexisting`인 경우에만 뜬다."""
    assert screen_copy.SIDECAR_REASON_PROVENANCE == "preexisting"


def test_end_types_are_six_with_fixed_codes() -> None:
    """§4.7 — 영문 코드 고정 6종, 표 순서 그대로(무작위 아님)."""
    assert screen_copy.END_TYPE_CODES == (
        "stop_here",
        "new_chat",
        "switch_ai",
        "seek_human",
        "no_further_need",
        "other",
    )


def test_no_reply_button_does_not_exist() -> None:
    """D-32 — "답장 보내지 않기"·"대화 종료" 버튼이 v2에 없다(User1 필수)."""
    copy = _all_participant_copy()
    assert "답장 보내지 않기" not in copy
    assert not hasattr(screen_copy, "NO_REPLY_BUTTON")


def test_no_presurvey_copy_remains() -> None:
    """D-31 — 사전 설문 폐기. 화면 문안에 흔적이 남지 않는다."""
    assert "사전 설문" not in _all_participant_copy()
    assert not hasattr(screen_copy, "PRESURVEY_INTRO")
