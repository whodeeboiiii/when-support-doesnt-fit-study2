"""P00 [정본] 문안 대조 (구현명세서 §5.5 · §0.4 "윤문 금지" · 부록 D.1 마지막 줄).

§5.5는 P00의 R/U/Q segment와 trouble cue를 **초안 신 §7.6 worked example에서 글자 그대로**
가져오라고 지시한다. 사람 눈으로 대조하면 언젠가 조사 하나가 바뀌므로 기계가 본다.

대조 대상은 명세서 파일 자체다 — 상수를 코드에 복사하면 "복사본끼리 일치"만 확인하게 된다.
명세서에서 문자열을 뽑아 dossier와 맞춘다.

⚠ trouble cue의 마침표: §5.5가 "(초안에 마침표 없음 — 그대로)"라고 못박았다. 마침표를 붙이면
이 테스트가 깨진다. 그게 목적이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.assets import dossier_loader

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "구현명세서_v2.0.md"


@pytest.fixture(scope="module")
def spec() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def p00() -> dossier_loader.Dossier:
    dossier_loader.reset_cache()
    return dossier_loader.load("P00")


def _quoted_after(spec: str, marker: str) -> str:
    """§5.5의 `- \\`r\\` = "…"` 형식에서 큰따옴표 안을 뽑는다."""
    index = spec.index(marker)
    match = re.search(r'"([^"]+)"', spec[index : index + 400])
    assert match, f"명세서에서 {marker!r} 뒤의 인용문을 찾지 못했다"
    return match.group(1)


# --------------------------------------------------------------------------- #
# §5.5 [정본] — segment 3종
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", ["r", "u", "q"])
def test_segment_matches_spec_verbatim(
    key: str, spec: str, p00: dossier_loader.Dossier
) -> None:
    """§5.5 segment **[정본, 초안 §7.6 표]** — 글자 단위 일치. 윤문 0건."""
    expected = _quoted_after(spec, f"- `{key}` = ")
    assert p00.stimulus.segment(key) == expected


def test_trouble_cue_matches_spec_without_period(
    spec: str, p00: dossier_loader.Dossier
) -> None:
    """§5.5 — trouble cue **[정본]** "장기 계획까지 짜달라는 건 아니야" (마침표 없음, 그대로)."""
    expected = _quoted_after(spec, "trouble cue **[정본]**")
    assert p00.ai_visible.trouble_cue == expected
    assert not p00.ai_visible.trouble_cue.endswith("."), "§5.5는 마침표 없음을 명시한다"


def test_assembled_conditions_match_spec_segments(p00: dossier_loader.Dossier) -> None:
    """§5.5 — "조립 결과가 초안 §7.6 표의 C1–C4 문자열과 글자 단위 일치해야 한다".

    명세서 v2.0 본문은 조립 결과 4종을 따로 싣지 않고 **조립 규칙**(D-35)을 준다. 그래서
    여기서는 segment로부터 규칙대로 조립한 결과와 로더의 산출을 대조한다 — 규칙이 바뀌면
    이 테스트가 먼저 깨진다.
    """
    stimulus = p00.stimulus
    assert p00.assemble("C1") == stimulus.r
    assert p00.assemble("C2") == f"{stimulus.r} {stimulus.q}"
    assert p00.assemble("C3") == f"{stimulus.r} {stimulus.u}"
    assert p00.assemble("C4") == f"{stimulus.r} {stimulus.u} {stimulus.q}"


# --------------------------------------------------------------------------- #
# §5.5 evidence_code — PI 확정 근거
# --------------------------------------------------------------------------- #


def test_evidence_code_matches_spec(p00: dossier_loader.Dossier) -> None:
    """§5.5 — a_level A2 · locus trajectory_timing · permitted_operation · residual_uncertainty."""
    code = p00.evidence_code
    assert code.a_level == "A2"
    assert code.mismatch_locus == "trajectory_timing"
    assert code.permitted_operation == "long-term expansion을 제거하고 present decision frame으로 돌아감"
    assert code.residual_uncertainty == "현재 결정에서 stability와 growth 중 무엇에 더 weight를 둘지"


def test_neutral_fallback_matches_spec(spec: str, p00: dossier_loader.Dossier) -> None:
    """§5.5 neutral_fallback [제안 승계]."""
    expected = _quoted_after(spec, "neutral_fallback [제안 승계]: ")
    assert p00.stimulus.neutral_fallback == expected


def test_checkpoint_mentions_three_year_plan(p00: dossier_loader.Dossier) -> None:
    """§5.5 — AI가 이를 **3-year career plan**으로 확장했다(v1의 6개월이 아니다)."""
    assert "3년" in p00.ai_visible.problematic_ai_response


def test_p00_is_qa_synthetic_not_a_real_participant(p00: dossier_loader.Dossier) -> None:
    """§5.1 — P00 = QA 합성(`is_test=true`). 배정표에 없다."""
    from app.core import assignment

    assert not assignment.load().has("P00")
