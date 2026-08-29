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
import re

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
# NT-44 — prohibited_inference 작성 규칙 v2 (§5.3 · D-43)
# --------------------------------------------------------------------------- #

#: D-43 §2-1 — 주어는 반드시 사용자다. 제3자·일반 상황 서술은 항목이 아니다.
_PI_SUBJECT_PREFIXES = ("사용자가 ", "사용자의 ")
#: D-43 §2-1 — 단정형. 위반은 초안이 그 내용을 **사용자에 관한 사실로 전제**할 때만 성립한다.
_PI_ASSERTION_ENDINGS = ("단정하는 것", "전제하는 것")
_PI_MIN_ITEMS, _PI_MAX_ITEMS = 3, 5


@pytest.mark.parametrize("participant_no", ALL)
def test_prohibited_inference_follows_the_v2_authoring_rules(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-43 — 주어(사용자) · 단정형 · 3–5개.

    구판은 주어가 없어서("표현되지 않은 감정 추론") checker가 제3자·일반 상식 서술까지
    잡았고, 두 실참가자(P08·P23) 모두 그 경로로 `neutral_fallback`에 착지했다. 형식을
    문자로 고정하는 것이 그 재발을 막는 유일한 장치다.

    schema_dummy는 `<TODO: PH-03>` placeholder라 제외한다 — 실값이 들어올 때 이 테스트가
    형식을 강제한다.
    """
    dossier = dossiers[participant_no]
    if dossier.is_dummy:
        pytest.skip("schema_dummy — 실값 미착지 (PH-03)")

    items = dossier.evidence_code.prohibited_inference
    assert _PI_MIN_ITEMS <= len(items) <= _PI_MAX_ITEMS, (
        f"{participant_no}: {len(items)}개 — 사건에서 실제로 유혹이 큰 것만 "
        f"{_PI_MIN_ITEMS}–{_PI_MAX_ITEMS}개 (D-43 §2-1)"
    )
    for item in items:
        assert item.startswith(_PI_SUBJECT_PREFIXES), f"{participant_no}: 주어가 사용자가 아니다 — {item!r}"
        assert item.endswith(_PI_ASSERTION_ENDINGS), (
            f"{participant_no}: 단정형이 아니다 — {item!r}. AI 행위 제약(새 방향·새 방법 생성 "
            f"금지)은 이 목록이 아니라 permitted_operation에 둔다 (D-43 §1-2)"
        )
        # 이 목록은 LLM payload로 나간다 — 연구 어휘가 섞이면 그것부터가 조작 노출이다(§1.2).
        assert "참가자" not in item, f"{participant_no}: 연구 어휘 '참가자' — LLM에는 '사용자'다"


@pytest.mark.parametrize("participant_no", ALL)
def test_prohibited_inference_does_not_collide_with_the_evidence(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-43 ⑧ — **대화 맥락에 이미 있는 감정·사정은 항목에 넣지 않는다.**

    금지 항목이 evidence와 겹치면 checker가 "대화에 있는 내용"을 위반으로 잡는다. 실모델
    재검에서 P08이 그 경로로 두 번 fallback했다(목록에 "서운함", 맥락에 "속상하다") — 조건
    (c)와 "이미 쓴 표현 되짚기" 비위반 사유가 목록에 눌렸다.

    ⚠ 이 테스트가 잡는 것은 **글자 그대로 겹치는 항목**뿐이다("장소"를 금지하면서 맥락에
    "파티 장소는 파티룸"이 있는 경우). 같은 감정군인지("서운함" ↔ "속상하다")는 코딩
    판단이고, A.2 v3.1이 프롬프트 쪽에서 한 번 더 막는다.
    """
    dossier = dossiers[participant_no]
    if dossier.is_dummy:
        pytest.skip("schema_dummy — 실값 미착지 (PH-03)")

    visible = dossier.ai_visible
    evidence = " ".join(
        [
            visible.situation_summary,
            *visible.prior_evidence,
            visible.original_request,
            visible.problematic_ai_response,
            visible.trouble_cue,
        ]
    )
    for item in dossier.evidence_code.prohibited_inference:
        listed = re.search(r"([^,]+?) 등 대화에", item)
        if not listed:
            continue
        for term in (part.strip() for part in listed.group(1).split("·")):
            term = term.removeprefix("사용자가 ").removeprefix("사용자의 ").strip()
            stem = term.rstrip("함감움") if len(term) > 2 else term
            assert stem and stem not in evidence, (
                f"{participant_no}: 금지 항목의 {term!r}가 대화 맥락에 이미 있다 — "
                f"그 항목은 evidence와 충돌한다 (D-43 ⑧)"
            )


# --------------------------------------------------------------------------- #
# NT-43 — 표시본(무대지시) 계약 (§4.4 · D-40)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("participant_no", ALL)
def test_presented_adds_the_uptake_note_only_where_u_exists(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-40 · D-47 — u가 있는 조건(C3·C4)에만, 그리고 문면이 있는 사건에만 붙는다.

    A0은 문면이 빈 문자열이라 네 조건 전부 조립 결과 그대로다 — 무대지시가 "없는" 것이지
    "빈 괄호"가 붙는 것이 아니다.
    """
    dossier = dossiers[participant_no]
    note = dossier.uptake_note
    for condition in CONDITIONS:
        presented = dossier.presented(condition)
        if condition in {"C3", "C4"} and note:
            assert dossier.has_uptake_note(condition)
            assert presented.count(note) == 1
        else:
            assert not dossier.has_uptake_note(condition)
            assert presented == dossier.assemble(condition)


@pytest.mark.parametrize("participant_no", ALL)
def test_uptake_note_sits_right_after_u(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-40 — C3는 문말, C4는 **q 앞**이다.

    q 뒤가 아닌 이유: q는 "다음 응답을 위해 남은 질문"이라 마지막에 있어야 하고(STO 문항이
    "마지막에 한 질문"을 지칭한다), 무대지시가 가리키는 것은 u가 약속한 지원이다.
    """
    dossier = dossiers[participant_no]
    stimulus = dossier.stimulus
    note = dossier.uptake_note
    # A0은 문면이 없다 — 자리도 없다(D-47). 빈 조각을 끼워 공백이 남지 않는지까지 본다.
    tail = f" {note}" if note else ""
    assert dossier.presented("C3") == f"{stimulus.r} {stimulus.u}{tail}"
    assert dossier.presented("C4") == f"{stimulus.r} {stimulus.u}{tail} {stimulus.q}"


@pytest.mark.parametrize("participant_no", ALL)
def test_assemble_is_untouched_by_the_note(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-40 — 무대지시는 **자산의 조립 결과에 들어가지 않는다**.

    `assemble()`에 들어가면 `stimulus_hash`·`stimuli_meta`·lock hash가 전부 흔들린다.
    표시·전달본과 자산 조립을 나눈 이유가 그것이다.
    """
    dossier = dossiers[participant_no]
    note = dossier.uptake_note
    for condition in CONDITIONS:
        assert not note or note not in dossier.assemble(condition)
    # 무대지시는 질문 수 계약도 건드리지 않는다(물음표가 없다).
    assert count_questions(note) == 0


# --------------------------------------------------------------------------- #
# NT-47 — 무대지시 문안은 A-level이 고른다 (§4.4 · D-47)
# --------------------------------------------------------------------------- #


def test_uptake_note_table_covers_every_a_level() -> None:
    """A-level 하나가 표에서 빠지면 그 사건은 `presented()`에서 KeyError로 죽는다.

    자산 검증이 `a_level`을 A_LEVELS로 막고 있으므로, 표가 그 집합을 **정확히** 덮으면
    무대지시 조회는 실패할 수 없다.
    """
    assert set(dossier_loader.UPTAKE_NOTE_BY_A_LEVEL) == A_LEVELS


def test_uptake_note_wording_is_canonical() -> None:
    """[PI 확정 2026-08-29 · D-47] — 문안 3종. 윤문하려면 이 테스트를 먼저 고쳐야 한다.

    A0은 **무표시**다(빈 문자열). "(해당 없음)" 같은 placeholder를 붙이지 않는다 — 참가자
    화면에 연구 어휘가 들어가고, 그 자체가 사건 분류의 단서가 된다.
    """
    assert dossier_loader.UPTAKE_NOTE_BY_A_LEVEL["A0"] == ""
    assert dossier_loader.UPTAKE_NOTE_BY_A_LEVEL["A1"] == "(이후 응답은 위 범위 안에서 이어짐)"
    assert dossier_loader.UPTAKE_NOTE_BY_A_LEVEL["A2"] == "(그 후 적절한 답변 제공)"


@pytest.mark.parametrize("participant_no", ALL)
def test_uptake_note_follows_the_a_level(
    participant_no: str, dossiers: dict[str, Dossier]
) -> None:
    """D-47 — 문면 선택의 입력은 `a_level` 하나다. 사건별 예외는 없다(D-45 유지)."""
    dossier = dossiers[participant_no]
    assert dossier.uptake_note == dossier_loader.UPTAKE_NOTE_BY_A_LEVEL[
        dossier.evidence_code.a_level
    ]


def test_uptake_note_passes_the_same_text_rules_as_the_stimulus() -> None:
    """무대지시도 참가자가 본 AI1의 일부다 — 질문 0개·길이 상한(§6.4 R-3·R-4)을 지난다.

    C4는 `q`가 질문 1개를 쓰므로 무대지시가 질문을 하나라도 더 얹으면 조립 결과의 질문 수
    계약(NT-22)이 깨진다.
    """
    for note in dossier_loader.UPTAKE_NOTE_BY_A_LEVEL.values():
        assert check_text_rules(note) == []
        assert count_questions(note) == 0


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
