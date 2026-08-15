"""P00 [정본] 문안의 글자 단위 대조 (§0.4 "윤문 금지" · 부록 A.6 · 부록 D.1).

명세서는 [정본] 표시가 붙은 문안을 **한 글자도 고치지 말라**고 못박는다. 사람이 눈으로
대조하는 항목(부록 D.1 체크리스트)이지만, P00은 파일로 존재하므로 기계가 대신 볼 수 있다.
자극 문장이 조용히 다듬어지면 조작 자체가 달라진다.

대조 기준은 리포에 함께 있는 `docs/구현명세서_v1.0.1.md`다 — 명세서가 개정되면 이 테스트가
먼저 깨져서 자산 동기화를 강제한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_TEXT = (REPO_ROOT / "docs" / "구현명세서_v1.0.1.md").read_text(encoding="utf-8")
P00 = json.loads((REPO_ROOT / "dossiers" / "P00.json").read_text(encoding="utf-8"))


def _canonical_strings() -> dict[str, str]:
    derivation = P00["derivation"]
    return {
        # 부록 A.6 — trouble cue·residual uncertainty·question stem
        "trouble_cue": P00["ai_visible"]["trouble_cue"]["text"],
        "residual_uncertainty": derivation["residual_uncertainty"]["text"],
        "question_stem": derivation["residual_uncertainty"]["question_stem"],
        # 부록 A.6 stimuli [정본 — 초안 §7.6]
        "stimuli.C1": derivation["stimuli"]["C1"],
        "stimuli.C3": derivation["stimuli"]["C3"],
        # 부록 A.4 P00 예시 fallback
        "neutral_fallback": derivation["neutral_fallback"],
    }


@pytest.mark.parametrize("label,text", sorted(_canonical_strings().items()))
def test_p00_canonical_text_matches_spec(label: str, text: str) -> None:
    assert text in SPEC_TEXT, f"P00 {label}: 명세서 원문과 다르다 (윤문 금지 — §0.4)"


def test_c2_and_c4_are_exactly_c1_c3_plus_the_question_stem() -> None:
    """부록 A.6 — "C2: C1 + question stem", "C4: C3 + question stem".

    P00은 명세서가 결합 방식까지 지정한 유일한 dossier다. P01–P12에는 이 제약을 걸지
    않는다 — §5.3이 요구하는 것은 recognition의 **동등성**이지 문자열 동일성이 아니다.
    """
    stimuli = P00["derivation"]["stimuli"]
    stem = P00["derivation"]["residual_uncertainty"]["question_stem"]
    assert stimuli["C2"] == f"{stimuli['C1']} {stem}"
    assert stimuli["C4"] == f"{stimuli['C3']} {stem}"


def test_p00_is_marked_as_qa_only() -> None:
    """§5.1 — P00은 QA 전용 합성 참가자다. 분석 제외 표시가 자산에 남아 있어야 한다."""
    assert P00["participant_no"] == "P00"
    assert "QA" in P00["sampling"]["notes_ref"]
