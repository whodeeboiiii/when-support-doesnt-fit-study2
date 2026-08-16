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


def test_excluded_instruments_are_not_present() -> None:
    """§7.1 — Mind Perception·reactance·perceived stress·Brief COPE는 **포함하지 않는다**."""
    serialized = json.dumps(ASSET, ensure_ascii=False).lower()
    for banned in ("mind perception", "reactance", "brief cope", "perceived stress"):
        assert banned not in serialized, f"배제 결정 위반: {banned} (§7.1)"
