"""자산 계약 테스트 — dossier (부록 C NT-20·NT-21·NT-22·NT-23).

이 스위트는 **CI 상주**다(§10.4). dossier가 placeholder에서 실값으로 바뀌는 커밋마다 같이
돌아야 하고(§11.1 더미 자산 원칙), 통과하지 못하면 서버가 아예 뜨지 않는다(§5.4 기동 게이트).

여기서 검사하는 것은 "연구자가 쓴 내용이 좋은가"가 아니라 **조작이 성립하는 형식 조건**이다:
층이 분리돼 있는가, C1·C3에 질문이 없고 C2·C4에 정확히 1개 있는가, C2와 C4의 question stem이
글자 그대로 같은가, 기재된 계량이 실제 원문과 맞는가, fallback이 규칙 계층을 통과하는가.
"""

from __future__ import annotations

import json

import pytest

from app.assets import dossier_loader
from app.assets.files import PARTICIPANT_NUMBERS, dossier_path
from app.core.text_metrics import count_questions, measure
from app.llm.integrity_rules import MAX_OUTPUT_CHARS, check_text_rules

ALL_PARTICIPANTS = list(PARTICIPANT_NUMBERS)


@pytest.fixture(scope="module", autouse=True)
def _fresh_cache() -> None:
    dossier_loader.reset_cache()


# --------------------------------------------------------------------------- #
# NT-20 dossier 스키마 전수 검증 (필수 키·layer 분리·referent_map 형식) — 기동 게이트
# --------------------------------------------------------------------------- #


def test_nt20_every_dossier_loads_under_contract() -> None:
    """P00–P12 전수가 계약을 통과한다. 한 건이라도 깨지면 기동이 실패해야 한다(§5.4)."""
    dossiers = dossier_loader.validate_all()
    assert sorted(dossiers) == sorted(ALL_PARTICIPANTS)


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt20_required_keys_and_layers(participant_no: str) -> None:
    path, _is_dummy = dossier_path(participant_no)
    document = json.loads(path.read_text(encoding="utf-8"))

    assert set(document) == {
        "participant_no",
        "version",
        "locked_at",
        "hash",
        "sampling",
        "ai_visible",
        "researcher_only",
        "derivation",
    }
    # §5.2 세 층이 각자의 자리에 있다 — ai_visible에 회고 필드가 섞여 들어오면 §1.2가 깨진다.
    assert set(document["ai_visible"]) == {
        "situation_summary",
        "original_request",
        "problematic_ai_response",
        "trouble_cue",
        "prior_evidence",
    }
    assert set(document["derivation"]) == {
        "warranted_uptake",
        "prohibited_inference",
        "residual_uncertainty",
        "focal_repair_relevant_content",
        "stimuli",
        "stimuli_meta",
        "neutral_fallback",
        "referent_map",
    }
    assert {
        "retrospective_stance",
        "unsent_at_the_time",
        "mismatch_interpretation",
        "original_trajectory",
        "ideal_response_reported",
        "correction_labor_notes",
    } <= set(document["researcher_only"])


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt20_referent_map_shape(participant_no: str) -> None:
    """§6.4 — referent_map은 {patterns[], proposition} 목록이어야 정규화가 성립한다."""
    dossier = dossier_loader.load(participant_no)
    for entry in dossier.derivation.referent_map:
        assert entry.patterns, f"{participant_no}: 지시표현 패턴이 비었다"
        assert all(pattern.strip() for pattern in entry.patterns)
        assert entry.proposition.strip()


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt20_lock_metadata_is_consistent(participant_no: str) -> None:
    """§5.2 lock 절차 — hash가 있으면 현재 내용과 맞아야 한다(자산 무단 변경 탐지)."""
    dossier = dossier_loader.load(participant_no)
    if dossier.locked_hash is not None:
        assert dossier.locked_hash == dossier.content_hash, (
            f"{participant_no}: lock hash와 현재 내용이 다르다 — 자산이 lock 후 변경됐다(§1.4)"
        )
        assert dossier.locked_at, "hash가 있으면 locked_at도 있어야 한다"


# --------------------------------------------------------------------------- #
# NT-21 전 dossier의 neutral_fallback이 규칙 R-3·R-4 통과 (§6.6 · 부록 A.4)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt21_neutral_fallback_passes_rule_layer(participant_no: str) -> None:
    fallback = dossier_loader.load(participant_no).derivation.neutral_fallback
    violations = check_text_rules(fallback)
    assert violations == [], f"{participant_no} neutral_fallback 규칙 위반: {violations}"
    assert len(fallback.strip()) <= MAX_OUTPUT_CHARS


# --------------------------------------------------------------------------- #
# NT-22 자극 질문 수 계약 + C2·C4 question stem 동일성 (§0.4 · §5.3)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt22_question_counts(participant_no: str) -> None:
    """C1·C3 = 질문 0 / C2·C4 = 질문 1. elicitation이 곧 조건 축이므로 여기가 조작 그 자체다."""
    dossier = dossier_loader.load(participant_no)
    counts = {
        condition: count_questions(dossier.stimulus(condition))
        for condition in ("C1", "C2", "C3", "C4")
    }
    assert counts == {"C1": 0, "C2": 1, "C3": 0, "C4": 1}, f"{participant_no}: {counts}"


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt22_c2_and_c4_share_the_same_question_stem(participant_no: str) -> None:
    """§0.4 동결 — C2=C4 질문은 동일 stem이어야 elicitation 효과와 질문 내용이 갈린다.

    recognition clause의 **글자 단위 동일성은 요구하지 않는다** — §0.4가 요구하는 것은
    "내용·specificity·톤을 최대한 동일 유지"이고 그 판정은 2인 독립 판정(§5.2)의 몫이다.
    기계가 고정할 수 있는 것은 question stem 문자열의 동일성이다.
    """
    dossier = dossier_loader.load(participant_no)
    stem = dossier.derivation.residual_uncertainty.question_stem
    assert stem in dossier.stimulus("C2"), f"{participant_no}: C2에 question stem이 없다"
    assert stem in dossier.stimulus("C4"), f"{participant_no}: C4에 question stem이 없다"


# --------------------------------------------------------------------------- #
# NT-23 stimuli_meta(문자·문장·질문 수)와 실제 원문 일치
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_nt23_stimuli_meta_matches_text(participant_no: str) -> None:
    path, _is_dummy = dossier_path(participant_no)
    document = json.loads(path.read_text(encoding="utf-8"))
    stimuli = document["derivation"]["stimuli"]
    meta = document["derivation"]["stimuli_meta"]
    for condition, text in stimuli.items():
        assert meta[condition] == measure(text).as_dict(), (
            f"{participant_no}.{condition}: 기재 {meta[condition]} vs 실제 {measure(text).as_dict()}"
        )
