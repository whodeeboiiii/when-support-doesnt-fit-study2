"""NT-05 — 사전설문 자산 계약과 메타키 미노출 (구현명세서 §4.2 · §7.1).

    문항 ID·역채점 메타는 참가자 payload로 새지 않는다(v4.2 규율 승계 — NT-05).

자산 자체는 아직 placeholder다 `<TODO: PH-01>`. 그래서 이 테스트는 **원문**을 검사하지 않고
**구조와 경계**를 검사한다 — 실값이 들어오는 커밋에서 이 계약이 그대로 살아 있어야 한다
(§11.1 더미 자산 원칙: 실값 착지 커밋은 자산 계약 테스트를 동반한다).
"""

from __future__ import annotations

import json

import pytest

from app.assets import presurvey

ASSET = json.loads(presurvey.asset_path().read_text(encoding="utf-8"))

#: 자산에는 있지만 참가자에게 가면 안 되는 키 (NT-05).
RESEARCHER_META = ("id", "reverse", "_note", "section")


def test_asset_loads_and_is_not_empty() -> None:
    asset = presurvey.load()
    assert asset.version
    assert asset.items, "문항이 없다"


def test_sections_cover_the_four_spec_groups() -> None:
    """§4.2 구성 ①–④ — 빈도·빗나갔을 때 대응·disclosure 2문항·DDI 발췌 4문항."""
    sections = {item.section for item in presurvey.load().items}
    assert sections == {"ai_use_frequency", "misfit_response", "study_disclosure", "ddi_excerpt"}
    counts = {section: 0 for section in sections}
    for item in presurvey.load().items:
        counts[item.section] += 1
    assert counts["study_disclosure"] == 2
    assert counts["ddi_excerpt"] == 4


def test_item_ids_are_unique() -> None:
    ids = [item.item_id for item in presurvey.load().items]
    assert len(ids) == len(set(ids))


def test_asset_actually_contains_researcher_meta() -> None:
    """검사 대상이 없으면 NT-05는 공허하게 통과한다 — 메타키의 존재를 먼저 고정한다."""
    assert any("_note" in item for item in ASSET["items"])
    assert any(item.get("reverse") is True for item in ASSET["items"])


def test_nt05_participant_payload_has_no_researcher_meta() -> None:
    payload = presurvey.load().participant_payload()
    assert payload, "payload가 비었다"
    for view in payload:
        unknown = set(view) - presurvey.PARTICIPANT_FIELDS
        assert not unknown, f"허용되지 않은 필드가 참가자 payload에 있다: {sorted(unknown)}"
        for meta in RESEARCHER_META:
            assert meta not in view, f"메타키 노출: {meta}"


def test_nt05_serialized_payload_contains_no_item_id_string() -> None:
    """직렬화된 뒤에도 문항 ID 문자열이 섞이지 않는다(중첩 필드 우회 방지)."""
    serialized = json.dumps(presurvey.load().participant_payload(), ensure_ascii=False)
    for item in presurvey.load().items:
        assert item.item_id not in serialized, f"문항 ID 누출: {item.item_id}"
    assert "reverse" not in serialized
    assert "_note" not in serialized


def test_positions_are_one_based_and_dense() -> None:
    """위치가 곧 `presurvey_responses.display_order`다(§8.1)."""
    payload = presurvey.load().participant_payload()
    assert [view["position"] for view in payload] == list(range(1, len(payload) + 1))


def test_choice_items_carry_options_and_scales_carry_bounds() -> None:
    for view in presurvey.load().participant_payload():
        if view["type"] in presurvey.CHOICE_TYPES:
            assert view["options"], "선택형 문항에 선택지가 없다"
            assert all(set(option) == {"value", "label"} for option in view["options"])
        else:
            assert view["scale_min"] == 1 and view["scale_max"] == 7


def test_response_validation_by_type() -> None:
    asset = presurvey.load()
    for position, item in enumerate(asset.items, start=1):
        if item.type == "single_choice":
            asset.validate_response(position, item.options[0].value)
            with pytest.raises(ValueError):
                asset.validate_response(position, "없는_선택지")
        elif item.type == "multi_choice":
            asset.validate_response(position, [item.options[0].value])
            with pytest.raises(ValueError):
                asset.validate_response(position, ["없는_선택지"])
        else:
            asset.validate_response(position, 4)
            with pytest.raises(ValueError):
                asset.validate_response(position, 8)
            with pytest.raises(ValueError):
                asset.validate_response(position, "4")


def test_unknown_position_is_refused() -> None:
    asset = presurvey.load()
    with pytest.raises(KeyError):
        asset.item_at(0)
    with pytest.raises(KeyError):
        asset.item_at(len(asset.items) + 1)


def test_contract_violations_fail_loudly(tmp_path, monkeypatch) -> None:
    """계약 위반은 기동 게이트에서 끊긴다 — 조용한 부분 로드가 없다."""
    broken = tmp_path / "presurvey_items_v0.json"
    broken.write_text(
        json.dumps({"version": "x", "items": [{"id": "a", "type": "unknown", "text": "t"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(presurvey, "ASSET_PATH", broken)
    presurvey.reset_cache()
    try:
        with pytest.raises(presurvey.PresurveyContractError):
            presurvey.load()
    finally:
        presurvey.reset_cache()


def test_no_placeholder_tokens_remain_in_participant_facing_text() -> None:
    """문항 원문 초안이 착지했다 — 참가자가 보는 문자열에 `<TODO>`가 남아 있으면 안 된다.

    연구자 메타(`_note`)에는 남아 있어도 된다(출처·번안 이력을 적는 자리다).
    """
    for item in presurvey.load().items:
        assert "<TODO" not in item.text, f"{item.item_id}: 문항 원문이 아직 placeholder다"
        for option in item.options:
            assert "<TODO" not in option.label, f"{item.item_id}: 선택지가 아직 placeholder다"


def test_ddi_excerpt_keeps_the_instrument_reverse_keying() -> None:
    """DDI 발췌 4문항 중 역채점은 2문항이다 (Kahn & Hessling 2001의 해당 문항).

    역채점 표시가 어긋나면 기술 통계가 조용히 뒤집힌다 — 자산에서 고정한다.
    """
    ddi = {item.item_id: item for item in presurvey.load().items if item.section == "ddi_excerpt"}
    assert {item_id for item_id, item in ddi.items() if item.reverse} == {"ddi_2", "ddi_4"}


def test_frequency_items_share_one_option_set() -> None:
    """§7.4 — 전반·영역별 빈도는 같은 척도로 비교한다."""
    items = [item for item in presurvey.load().items if item.section == "ai_use_frequency"]
    assert len(items) == 5
    option_sets = {tuple((option.value, option.label) for option in item.options) for item in items}
    assert len(option_sets) == 1, "빈도 문항의 보기가 서로 다르다"


def test_misfit_options_are_the_five_spec_behaviours() -> None:
    """§4.2 ② — 같은 대화 재설명 / 새 채팅 / 다른 AI / 사람 / 중단."""
    item = next(item for item in presurvey.load().items if item.section == "misfit_response")
    assert [option.value for option in item.options] == [
        "re_explain_same_chat",
        "new_chat",
        "other_ai",
        "human",
        "stop",
    ]


def test_likert_items_carry_scale_anchors() -> None:
    """숫자 7칸만 그리면 문항에 답할 수 없다 — 앵커가 payload에 실린다."""
    for view in presurvey.load().participant_payload():
        if view["type"] in presurvey.LIKERT_TYPES:
            assert view["scale_min_label"] and view["scale_max_label"]


def test_presurvey_copy_avoids_normative_disclosure_language() -> None:
    """§7.8 중립성 — '말했어야 한다'·'빠뜨린 정보' 류 규범적 어휘를 쓰지 않는다."""
    text = " ".join(
        [item.text for item in presurvey.load().items]
        + [option.label for item in presurvey.load().items for option in item.options]
    )
    for banned in ("했어야", "빠뜨", "알려줬어야", "제대로 말"):
        assert banned not in text, f"규범적 어휘: {banned}"


def test_excluded_instruments_are_not_present() -> None:
    """§7.1 — Mind Perception·reactance·perceived stress·Brief COPE는 **포함하지 않는다**."""
    serialized = json.dumps(ASSET, ensure_ascii=False).lower()
    for banned in ("mind perception", "reactance", "brief cope", "perceived stress"):
        assert banned not in serialized, f"배제 결정 위반: {banned} (§7.1)"
