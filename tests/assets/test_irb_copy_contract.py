"""IRB 문안 착지본 대조 (PH-IRB-1 · PH-IRB-2 · 구현명세서 §4.1 · §4.12).

**[정본] 5건과 같은 규율이되 대조 대상만 다르다.** 명세서 문안은 명세서 파일을 상대로
대조하지만(`test_screen_copy_canonical.py`), 동의서·디브리핑의 출처는 명세서가 아니라 IRB
서류다 — `docs/IRB_문안_정본_초안_v1.md`. 상수를 테스트에 복사하면 "복사본끼리 일치"만
확인하게 되고, IRB 심의 과정에서 문안이 바뀔 때 코드가 조용히 뒤처진다.

이 파일이 지키는 것 셋:

1. **글자 대조** — 화면에 나가는 문안이 IRB 문서와 한 글자도 다르지 않다.
2. **승인 상태 정합** — 초안이면 모집 게이트 표식(`<TODO: PH-IRB-n>`)이 남아 있고,
   정본이면 사라진다. 둘 사이의 어정쩡한 상태를 만들 수 없다(§11.2가 이 표식을 읽는다).
3. **필수 항목 충족** — 동의 항목 6종(§4.1), 디브리핑 공개 ①–⑦(§4.12).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.assets import screen_copy
from app.core import freeze

REPO_ROOT = Path(__file__).resolve().parents[2]
IRB_DOC_PATH = REPO_ROOT / "docs" / "IRB_문안_정본_초안_v1.md"

#: 승인된 정본의 `CONSENT_VERSION` 접두사. 초안 동안은 `irb_draft_`다.
APPROVED_VERSION_PREFIX = "irb_v1_"


@pytest.fixture(scope="module")
def irb_doc() -> str:
    return _normalize(IRB_DOC_PATH.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    """마크다운 마크업만 걷어내고 공백을 정규화한다 — 내용은 손대지 않는다.

    걷어내는 것은 인용 블록 머리(`> `)와 슬롯을 감싼 백틱뿐이다. 문서는
    ``` `[IRB 승인번호]` ```처럼 대괄호 슬롯을 코드 표기로 감싸지만 화면에 나가는 것은
    대괄호까지다.
    """
    lines = [re.sub(r"^>\s?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines).replace("`", "")).strip()


# --------------------------------------------------------------------------- #
# PH-IRB-1 — 동의서 (§4.1)
# --------------------------------------------------------------------------- #


def test_consent_notice_matches_the_irb_document(irb_doc: str) -> None:
    """§1-C P1 상단 안내 — 재확인 화면 도입문."""
    assert _normalize(screen_copy.CONSENT_NOTICE) in irb_doc


def test_consent_pii_notice_matches_the_irb_document(irb_doc: str) -> None:
    """§1-B 하단 — PII 입력 금지(심의용 연구계획서 19번)."""
    assert _normalize(screen_copy.CONSENT_PII_NOTICE) in irb_doc


def test_every_consent_label_matches_the_irb_document(irb_doc: str) -> None:
    """§1-B 축약형 라벨 6종. 화면 라벨을 윤문하면 서면 동의서와 어긋난다."""
    for item in screen_copy.CONSENT_ITEMS:
        assert _normalize(item.label) in irb_doc, f"동의 라벨이 IRB 문서와 다르다 — {item.field}"


def test_consent_labels_are_no_longer_todo_strings() -> None:
    """착지 확인 — 라벨에 `<TODO>` 표식이 섞여 나가지 않는다."""
    for item in screen_copy.CONSENT_ITEMS:
        assert "<TODO" not in item.label


def test_alternative_exposure_item_states_the_multiple_responses() -> None:
    """§4.1 ⑥ v2 신설 — 대안 노출은 **사전에** 고지된다(불완전 공개의 경계)."""
    label = dict((item.field, item.label) for item in screen_copy.CONSENT_ITEMS)[
        "alternative_exposure"
    ]
    assert "여러 AI 응답" in label


# --------------------------------------------------------------------------- #
# PH-IRB-2 — 디브리핑 (§4.12)
# --------------------------------------------------------------------------- #


def test_debrief_body_matches_the_irb_document(irb_doc: str) -> None:
    """§2-A 본문 전체 — 문단 순서까지 그대로."""
    assert _normalize(screen_copy.DEBRIEF_BODY) in irb_doc


@pytest.mark.parametrize("marker", ["(①)", "(②)", "(③)", "(④)", "(⑤)", "(⑥)", "(⑦)"])
def test_debrief_covers_every_required_disclosure(marker: str) -> None:
    """§4.12 필수 공개 7항목 — 하나라도 빠지면 불완전 공개가 닫히지 않는다."""
    assert marker in screen_copy.DEBRIEF_BODY


def test_debrief_says_no_response_is_the_right_answer() -> None:
    """§4.12 ② — v2에서 추가된 문장. v1의 "네 branch 비교"를 옮기면 안 된다."""
    assert '어느 것도 "정답"이 아닙니다' in screen_copy.DEBRIEF_BODY
    assert "branch" not in screen_copy.DEBRIEF_BODY


def test_debrief_states_the_sidecar_was_never_sent_to_the_ai() -> None:
    """§4.12 ⑤ — §1.2 evidence boundary가 참가자에게 확인되는 유일한 지점이다."""
    assert "AI에게 전달되지 않았고" in screen_copy.DEBRIEF_BODY


def test_debrief_states_the_checkpoint_edits_were_used() -> None:
    """§4.12 ⑥ — 수정본이 AI2 입력이었다는 사실(D-25)."""
    assert "수정 반영본으로 연구 자료에 포함" in screen_copy.DEBRIEF_BODY


# --------------------------------------------------------------------------- #
# 승인 상태 — 초안과 정본 사이의 어정쩡한 상태를 만들 수 없다
# --------------------------------------------------------------------------- #


def test_draft_copy_keeps_the_launch_gate_closed() -> None:
    """초안 문안이 착지해도 PH-IRB-1·2는 ⛔다 — 승인은 IRB가 하지 코드가 하지 않는다."""
    if screen_copy.CONSENT_VERSION.startswith(APPROVED_VERSION_PREFIX):
        pytest.skip("정본 착지 후 — 게이트 소멸이 정상이다")

    assert "PH-IRB-1" in screen_copy.CONSENT_TODO
    assert "PH-IRB-2" in screen_copy.DEBRIEF_TODO
    tags = {blocker.tag for blocker in freeze.blockers()}
    assert {"PH-IRB-1", "PH-IRB-2"} <= tags


def test_gate_marker_and_consent_version_agree() -> None:
    """승인 시 교체는 **한 묶음**이다 — 표식 제거와 버전 상향 중 하나만 하면 여기서 걸린다."""
    approved = screen_copy.CONSENT_VERSION.startswith(APPROVED_VERSION_PREFIX)
    marker_present = (
        "PH-IRB-1" in screen_copy.CONSENT_TODO or "PH-IRB-2" in screen_copy.DEBRIEF_TODO
    )
    assert approved is not marker_present, (
        "CONSENT_VERSION과 모집 게이트 표식이 어긋났다 — "
        "승인 후에는 표식을 지우고 CONSENT_VERSION을 irb_v1_<승인일>로 올린다"
    )


def test_gate_markers_never_reach_the_participant_screens() -> None:
    """표식은 게이트용이다. 화면 문안에 섞여 들어가면 참가자가 `<TODO>`를 읽게 된다."""
    rendered = "\n".join(
        [
            screen_copy.CONSENT_NOTICE,
            screen_copy.CONSENT_PII_NOTICE,
            screen_copy.DEBRIEF_BODY,
            *[item.label for item in screen_copy.CONSENT_ITEMS],
        ]
    )
    assert "<TODO" not in rendered


def test_approval_slots_are_still_open() -> None:
    """대괄호 슬롯 3종은 승인 후 치환한다 — 지금 비어 있는 것이 정상이다."""
    if screen_copy.CONSENT_VERSION.startswith(APPROVED_VERSION_PREFIX):
        assert "[IRB 승인번호]" not in screen_copy.DEBRIEF_BODY, "승인 후에는 슬롯을 치환한다"
    else:
        assert "[IRB 승인번호]" in screen_copy.DEBRIEF_BODY
