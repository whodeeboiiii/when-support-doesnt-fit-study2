"""dossier 자산 계약 — 스키마 v2 (구현명세서 §5.3 · §5.4 · 부록 C NT-20~23).

**전 dossier(실값·더미 무관)가 같은 계약을 통과해야 한다.** 더미가 계약을 못 지키면 CI가
검증하는 것이 실제 자산이 아니게 되고, 실값이 들어올 때 처음 깨진다.

v1.0.1에서 달라진 검사(부록 H.2):
- `sampling`·`cue form`·`referent_map`·`stimuli.C1–C4` 전문 검사 → **삭제**
- `evidence_code`·`provenance`·`qc` 검사 → **신설**
- 질문 수 계약이 조건 전문이 아니라 **segment + 조립 결과** 양쪽에 걸린다(NT-22 개정)
"""

from __future__ import annotations

import json

import pytest

from app.assets import dossier_loader
from app.assets.dossier_loader import (
    A_LEVELS,
    CONDITIONS,
    EDITABLE_SEGMENTS,
    MISMATCH_LOCI,
    PROVENANCE_VALUES,
    QUESTION_COUNT_BY_CONDITION,
    SEGMENT_KEYS,
    STIMULUS_RECIPE,
    Dossier,
    DossierContractError,
)
from app.assets.files import available_participant_numbers, dossier_path
from app.core.text_metrics import count_questions, measure
from app.llm.integrity_rules import check_text_rules

ALL = sorted(available_participant_numbers())


@pytest.fixture(scope="module")
def dossiers() -> dict[str, Dossier]:
    dossier_loader.reset_cache()
    return dossier_loader.load_all()


def test_every_participant_dossier_loads(dossiers: dict[str, Dossier]) -> None:
    """§5.4 기동 게이트 — 한 건이라도 계약 위반이면 여기서 예외가 난다."""
    assert set(dossiers) == set(ALL)
    # §5.1 — P00 + 배정표 24명.
    assert "P00" in dossiers
    assert len(dossiers) >= 25


# --------------------------------------------------------------------------- #
# NT-20 — 스키마 전수 · layer 분리 · provenance 커버리지 · qc 키
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL)
def test_evidence_code_schema(participant_no: str, dossiers: dict[str, Dossier]) -> None:
    """§5.3 evidence_code — a_level·locus는 **descriptor**다(§1.5-4)."""
    code = dossiers[participant_no].evidence_code
    assert code.a_level in A_LEVELS
    assert code.mismatch_locus in MISMATCH_LOCI
    for field in (
        code.mismatch_locus_text,
        code.directional_constraint,
        code.permitted_operation,
        code.residual_uncertainty,
        code.consequential_justification,
    ):
        assert field.strip(), "evidence_code 필수 서술이 비어 있다"
    assert code.prohibited_inference, "prohibited_inference는 checker 입력이다 (§6.4)"


@pytest.mark.parametrize("participant_no", ALL)
def test_provenance_covers_every_text_field(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """§5.4 기동 게이트 — "provenance 키가 ai_visible 텍스트 필드 전부를 덮음"."""
    visible = dossiers[participant_no].ai_visible
    assert set(visible.provenance) >= set(EDITABLE_SEGMENTS)
    for field, value in visible.provenance.items():
        assert value in PROVENANCE_VALUES, f"{field}: {value!r}는 §5.3 hierarchy에 없다"


@pytest.mark.parametrize("participant_no", ALL)
def test_qc_keys_exist(participant_no: str, dossiers: dict[str, Dossier]) -> None:
    """§5.4 — "시스템은 이 절차를 강제하지 않고 QC 필드의 **존재만** 검증한다"."""
    qc = dossiers[participant_no].stimulus.qc
    assert set(qc) == {
        "r_identity",
        "u_identity",
        "q_identity",
        "permitted_boundary",
        "leakage",
        "minimum_q",
        "reviewer",
        "at",
    }


@pytest.mark.parametrize("participant_no", ALL)
def test_trouble_cue_is_plain_text_not_a_form(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """§1.5-2 — v1.0.1의 cue form 분류는 **폐기**다. `trouble_cue`는 텍스트 하나다."""
    cue = dossiers[participant_no].ai_visible.trouble_cue
    assert isinstance(cue, str) and cue.strip()


@pytest.mark.parametrize("participant_no", ALL)
def test_loader_output_has_no_researcher_only(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """§1.2 · NT-04의 짝 — 로더 출력에 researcher_only 문자열이 섞여 있지 않다."""
    from app.assets.dossier_private import load_researcher_only

    dossier = dossiers[participant_no]
    payload = json.dumps(
        {
            "evidence_code": dossier.evidence_code.as_dict(),
            "ai_visible": dossier.ai_visible.as_dict(),
            "segments": {key: dossier.stimulus.segment(key) for key in SEGMENT_KEYS},
            "stimuli": dossier.all_stimuli(),
            "fallback": dossier.stimulus.neutral_fallback,
        },
        ensure_ascii=False,
    )
    for field, value in load_researcher_only(participant_no).items():
        text = str(value or "").strip()
        if len(text) >= dossier_loader.LEAK_MATCH_CHARS:
            assert text not in payload, f"researcher_only.{field}가 로더 출력에 있다"


# --------------------------------------------------------------------------- #
# NT-22 — segment 질문 수 · 조립 질문 수 · 조건 간 동일성
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL)
def test_segment_question_counts(participant_no: str, dossiers: dict[str, Dossier]) -> None:
    """§5.4 — `r`·`u` 질문 0개, `q` 질문 정확히 1개."""
    stimulus = dossiers[participant_no].stimulus
    assert count_questions(stimulus.r) == 0
    assert count_questions(stimulus.u) == 0
    assert count_questions(stimulus.q) == 1


@pytest.mark.parametrize("participant_no", ALL)
def test_assembled_question_counts(participant_no: str, dossiers: dict[str, Dossier]) -> None:
    """NT-22 — 조립 결과: C1·C3 질문 0 / C2·C4 질문 1."""
    dossier = dossiers[participant_no]
    for condition, expected in QUESTION_COUNT_BY_CONDITION.items():
        assert count_questions(dossier.assemble(condition)) == expected


@pytest.mark.parametrize("participant_no", ALL)
def test_segment_identity_across_conditions(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """§0.4 — R 문면 4조건 동일 · U는 C3=C4 verbatim · Q는 C2=C4 verbatim (NT-22)."""
    dossier = dossiers[participant_no]
    stimulus = dossier.stimulus
    assembled = dossier.all_stimuli()

    for condition in CONDITIONS:
        assert assembled[condition].startswith(stimulus.r), f"{condition}: R prefix 불일치"
    # C3·C4가 **같은 u 문자열**을 쓴다(내용 대체가 아니라 동일 segment 재사용 — D-35).
    assert stimulus.u in assembled["C3"] and stimulus.u in assembled["C4"]
    assert stimulus.q in assembled["C2"] and stimulus.q in assembled["C4"]
    # C1은 R뿐이다.
    assert assembled["C1"] == stimulus.r


@pytest.mark.parametrize("participant_no", ALL)
def test_assembly_is_single_space_join(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-35 — `r` / `r␣q` / `r␣u` / `r␣u␣q` (단일 공백 연결)."""
    dossier = dossiers[participant_no]
    stimulus = dossier.stimulus
    for condition, recipe in STIMULUS_RECIPE.items():
        expected = " ".join(stimulus.segment(key) for key in recipe)
        assert dossier.assemble(condition) == expected


@pytest.mark.parametrize("participant_no", ALL)
def test_assembly_is_deterministic(participant_no: str, dossiers: dict[str, Dossier]) -> None:
    """§5.4 — "런타임마다 동일". hash도 같아야 세션 간 비교가 성립한다(NT-07)."""
    dossier = dossiers[participant_no]
    for condition in CONDITIONS:
        assert dossier.assemble(condition) == dossier.assemble(condition)
        assert dossier.stimulus_hash(condition) == dossier.stimulus_hash(condition)
    # 네 조건의 hash가 서로 달라야 한다(자극이 실제로 다르다).
    hashes = {dossier.stimulus_hash(condition) for condition in CONDITIONS}
    assert len(hashes) == len(CONDITIONS)


# --------------------------------------------------------------------------- #
# NT-23 — stimuli_meta ↔ 조립 결과 계량 일치
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL)
def test_stimuli_meta_matches_assembly(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    dossier = dossiers[participant_no]
    for condition in CONDITIONS:
        assert dossier.stimulus.stimuli_meta[condition] == measure(dossier.assemble(condition))


# --------------------------------------------------------------------------- #
# NT-21 — neutral fallback이 규칙 계층을 통과한다
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL)
def test_neutral_fallback_passes_rules(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """§6.5 — 질문 0 · 비확장 · R-4 통과.

    자산 검사와 런타임 규칙이 **같은 함수**를 쓴다 — 갈라지면 "자산은 통과인데 표시하면
    위반"인 상태가 생긴다.
    """
    fallback = dossiers[participant_no].stimulus.neutral_fallback
    assert count_questions(fallback) == 0
    assert check_text_rules(fallback) == []


# --------------------------------------------------------------------------- #
# hash · lock
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL)
def test_content_hash_excludes_hash_field(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """§5.3 — hash 필드 자신을 제외한 canonical JSON sha256(자기참조 회피)."""
    path, _is_dummy = dossier_path(participant_no)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert dossiers[participant_no].content_hash == dossier_loader.compute_document_hash(document)
    # `hash`를 아무 값으로 바꿔도 content_hash는 그대로다.
    assert dossier_loader.compute_document_hash({**document, "hash": "x" * 64}) == (
        dossiers[participant_no].content_hash
    )


@pytest.mark.parametrize("participant_no", ALL)
def test_locked_state_is_honest(participant_no: str, dossiers: dict[str, Dossier]) -> None:
    """lock은 `locked_at`이 있고 hash가 현재 내용과 **일치할 때만** 참이다."""
    dossier = dossiers[participant_no]
    if dossier.is_locked:
        assert dossier.locked_at and dossier.locked_hash == dossier.content_hash
    else:
        assert not dossier.locked_at or dossier.locked_hash != dossier.content_hash


# --------------------------------------------------------------------------- #
# 계약 위반 거부 — 게이트가 실제로 끊는지
# --------------------------------------------------------------------------- #


def _p00_document() -> dict:
    path, _ = dossier_path("P00")
    return json.loads(path.read_text(encoding="utf-8"))


def _reject(document: dict, match: str, tmp_path, monkeypatch) -> None:
    """조작한 문서를 임시 dossier 디렉터리에 두고 로더가 거부하는지 본다."""
    target = tmp_path / "dossiers"
    target.mkdir(exist_ok=True)
    (target / "P00.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DOSSIER_DIR", str(target))
    dossier_loader.reset_cache()
    try:
        with pytest.raises(DossierContractError, match=match):
            dossier_loader.load("P00")
    finally:
        monkeypatch.delenv("DOSSIER_DIR", raising=False)
        dossier_loader.reset_cache()


def test_rejects_question_in_r_segment(tmp_path, monkeypatch) -> None:
    """NT-22 — R에 질문이 들어가면 recognition이 elicitation을 겸하게 된다."""
    document = _p00_document()
    document["stimulus"]["r"] = "지금 요청 범위를 넘었을까요?"
    _reject(document, "stimulus.r", tmp_path, monkeypatch)


def test_rejects_two_questions_in_q_segment(tmp_path, monkeypatch) -> None:
    """§0.4 — Q는 **minimum elicitation**(질문 1개)이다."""
    document = _p00_document()
    document["stimulus"]["q"] = "어느 쪽이 중요한가요? 다른 기준도 있나요?"
    _reject(document, "stimulus.q", tmp_path, monkeypatch)


def test_rejects_stale_stimuli_meta(tmp_path, monkeypatch) -> None:
    """NT-23 — segment를 고치고 meta를 안 고치면 거부."""
    document = _p00_document()
    document["stimulus"]["r"] = document["stimulus"]["r"] + " 덧붙인 문장입니다."
    _reject(document, "stimuli_meta", tmp_path, monkeypatch)


def test_rejects_fallback_with_question(tmp_path, monkeypatch) -> None:
    """NT-21 — fallback은 질문 0이다(§6.5)."""
    document = _p00_document()
    document["stimulus"]["neutral_fallback"] = "말씀 잘 받았습니다. 어떻게 할까요?"
    _reject(document, "neutral_fallback", tmp_path, monkeypatch)


def test_rejects_missing_provenance_field(tmp_path, monkeypatch) -> None:
    """§5.4 — provenance가 텍스트 필드 전부를 덮어야 한다."""
    document = _p00_document()
    document["ai_visible"]["provenance"].pop("trouble_cue")
    _reject(document, "provenance", tmp_path, monkeypatch)


def test_rejects_unknown_mismatch_locus(tmp_path, monkeypatch) -> None:
    """`<TODO: PH-03b>` — 목록 밖 locus는 받지 않는다."""
    document = _p00_document()
    document["evidence_code"]["mismatch_locus"] = "tone_mismatch"
    _reject(document, "mismatch_locus", tmp_path, monkeypatch)


def test_rejects_researcher_only_text_in_segment(tmp_path, monkeypatch) -> None:
    """§5.4 — 자산 수준에서 이미 방화벽이 깨진 상태를 기동 전에 끊는다(§1.2)."""
    document = _p00_document()
    leak = document["researcher_only"]["unsent_at_the_time"]
    document["stimulus"]["u"] = f"{document['stimulus']['u']} {leak}"
    # meta도 맞춰 둔다 — 그래야 실패 사유가 leakage 하나로 좁혀진다.
    stimulus = document["stimulus"]
    document["stimulus"]["stimuli_meta"] = {
        condition: measure(" ".join(stimulus[key] for key in recipe)).as_dict()
        for condition, recipe in STIMULUS_RECIPE.items()
    }
    _reject(document, "researcher_only", tmp_path, monkeypatch)


def test_rejects_v1_schema(tmp_path, monkeypatch) -> None:
    """v1.0.1 dossier를 그대로 넣으면 거부된다 — `sampling`·`derivation`은 v2에 없다."""
    document = _p00_document()
    document["sampling"] = {"actionability": 2, "mismatch_locus": "content_depth", "notes_ref": ""}
    _reject(document, "스키마에 없는 키", tmp_path, monkeypatch)
