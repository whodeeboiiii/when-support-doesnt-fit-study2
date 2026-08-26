"""문항 자산 계약 — focal 5 construct + MC 2 · pairwise 3 contrast (§4.8 · §4.10 · §7).

두 자산 모두 **`_v1` 실값이 착지했다**(PH-06·PH-07, 2026-08-24 — 문면 출처는 프로젝트 문서
『연구7_PH06_focal문항_후보_v1』·『연구7_PH07_pairwise문항_후보_v1』 추천 세트). 계약의 역할은
그대로다: 문면이 바뀌어도 **구조는 바뀌지 않게** 한다 — 구조가 같이 바뀌면 그건 설계 변경이고
§1.4의 승인 절차를 지나야 한다.

핵심 계약 셋.
1. **블록 순서 focal → mc 고정, MC가 마지막**(§0.4 D-37). MC가 앞에 오면 그 문항이
   focal 경험 평정의 referent를 흐린다.
2. **합산 필드 부재**(§7.1·§7.5). construct·contrast는 라벨이지 점수가 아니다.
3. **A/B 치환이 좌우와 정합**(부록 A.5 · NT-38). 클라이언트는 조건을 모른다.
"""

from __future__ import annotations

import json

import pytest

from app.assets import pairwise_items, rating_items
from app.assets.pairwise_items import (
    SIDE_LABELS,
    TARGET_CONDITIONS,
    PairwiseAssetError,
)
from app.assets.rating_items import MC_ITEM_IDS, SCOPE_FOCAL, SCOPE_MC, RatingAssetError
from app.core.assignment import CONTRAST_PAIR, CONTRASTS


@pytest.fixture(scope="module")
def focal() -> rating_items.RatingAsset:
    rating_items.reset_cache()
    return rating_items.load()


@pytest.fixture(scope="module")
def pairwise() -> pairwise_items.PairwiseAsset:
    pairwise_items.reset_cache()
    return pairwise_items.load()


# --------------------------------------------------------------------------- #
# focal 문항 (§4.8 · §7.1 · §7.2)
# --------------------------------------------------------------------------- #


def test_two_blocks_in_fixed_order_with_mc_last(focal: rating_items.RatingAsset) -> None:
    """§4.8 · D-37 — 블록 1 focal → 블록 2 MC. **MC가 battery 마지막**이다."""
    assert [block.scope for block in focal.blocks] == [SCOPE_FOCAL, SCOPE_MC]


def test_mc_block_has_exactly_two_items_with_ai1_card(
    focal: rating_items.RatingAsset,
) -> None:
    """§4.8 — MC 2문항 + **AI1 카드 앵커**(referent = 첫 번째 AI 응답)."""
    mc = focal.block(SCOPE_MC)
    assert {item.item_id for item in mc.items} == MC_ITEM_IDS
    assert mc.ai1_card is True
    for item in mc.items:
        assert item.construct == "manipulation_check"
        assert item.referent == "first_ai_response"


def test_focal_block_has_five_constructs(focal: rating_items.RatingAsset) -> None:
    """§4.8 — Grounding Sufficiency · Correction Effort · Reinvestment · Clarification Need ·
    Retrospective Continuation Intention (construct당 1–2문항)."""
    block = focal.block(SCOPE_FOCAL)
    constructs = {item.construct for item in block.items}
    assert constructs == {
        "grounding_sufficiency",
        "correction_effort",
        "reinvestment",
        "clarification_need",
        "retrospective_continuation_intention",
    }
    assert block.ai1_card is False, "블록 1의 referent는 대화 전체다 — 카드를 붙이지 않는다"
    for item in block.items:
        assert item.referent == "interaction"


def test_scale_is_one_to_seven(focal: rating_items.RatingAsset) -> None:
    """§0.5 — 전 문항 1–7."""
    assert (focal.scale_min, focal.scale_max) == (1, 7)
    assert focal.is_valid_value(1) and focal.is_valid_value(7)
    assert not focal.is_valid_value(0) and not focal.is_valid_value(8)
    assert not focal.is_valid_value(True), "bool은 int의 하위형이라 따로 막는다"


def test_presentation_order_is_stable_and_block_bounded(
    focal: rating_items.RatingAsset,
) -> None:
    """§4.8 · NT-08 — 블록 내 무작위, 블록 순서 고정, 같은 시드에 같은 순서."""
    first = rating_items.presentation_order("session-a")
    second = rating_items.presentation_order("session-a")
    assert [entry.item.item_id for entry in first] == [entry.item.item_id for entry in second]

    # 위치는 1..N 연속이고, 블록 경계를 넘지 않는다.
    assert [entry.position for entry in first] == list(range(1, focal.item_count + 1))
    scopes = [entry.scope for entry in first]
    assert scopes == sorted(scopes, key=lambda scope: 0 if scope == SCOPE_FOCAL else 1)

    # 시드가 다르면 순서가 달라진다(무작위가 실제로 걸려 있다).
    other = rating_items.presentation_order("session-b")
    assert [entry.item.item_id for entry in first] != [entry.item.item_id for entry in other] or (
        focal.item_count < 3
    )


def test_no_aggregate_field_in_asset() -> None:
    """§0.4 · §7.1 — 합산 금지. 자산에 총점 키가 생기면 로더가 끊는다."""
    document = json.loads(rating_items.asset_path().read_text(encoding="utf-8"))
    for banned in ("total", "subscales", "score", "sum"):
        assert banned not in document


def test_rejects_mc_first(tmp_path, monkeypatch) -> None:
    """D-37 — MC를 앞으로 옮기면 자산 계약이 거부한다."""
    document = json.loads(rating_items.asset_path().read_text(encoding="utf-8"))
    document["blocks"] = list(reversed(document["blocks"]))
    _reject_focal(document, "MC 마지막", tmp_path, monkeypatch)


def test_rejects_mc_without_card(tmp_path, monkeypatch) -> None:
    """§4.8 — MC의 referent는 AI1 카드다. 카드가 없으면 referent가 사라진다."""
    document = json.loads(rating_items.asset_path().read_text(encoding="utf-8"))
    next(block for block in document["blocks"] if block["scope"] == "mc")["ai1_card"] = False
    _reject_focal(document, "카드 앵커", tmp_path, monkeypatch)


def _reject_focal(document: dict, match: str, tmp_path, monkeypatch) -> None:
    path = tmp_path / "focal_items_v0.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rating_items, "asset_path", lambda: path)
    rating_items.reset_cache()
    try:
        with pytest.raises(RatingAssetError, match=match):
            rating_items.load()
    finally:
        monkeypatch.undo()
        rating_items.reset_cache()


# --------------------------------------------------------------------------- #
# pairwise 문항 (§4.10 · §7.5)
# --------------------------------------------------------------------------- #


def test_exactly_three_contrasts(pairwise: pairwise_items.PairwiseAsset) -> None:
    """§1.5-6 — sequence · scope · stopping. 코드에 다른 pair를 만들지 않는다."""
    assert set(pairwise.sets) == set(CONTRASTS)
    for contrast, entry in pairwise.sets.items():
        assert entry.pair == CONTRAST_PAIR[contrast]
        assert entry.items, f"{contrast}: 문항이 비어 있다"


def test_targets_designate_exactly_one_side(pairwise: pairwise_items.PairwiseAsset) -> None:
    """부록 A.5 — target이 있으면 그 contrast의 두 조건 중 **정확히 하나**여야 한다."""
    for contrast, entry in pairwise.sets.items():
        for item in entry.items:
            if item.target is None:
                continue
            holders = TARGET_CONDITIONS[item.target] & CONTRAST_PAIR[contrast]
            assert len(holders) == 1, f"{item.item_id}: {item.target}가 한쪽을 지칭하지 않는다"


def test_ab_substitution_follows_assigned_sides(
    pairwise: pairwise_items.PairwiseAsset,
) -> None:
    """NT-38 — 좌우가 뒤집히면 A/B도 뒤집힌다. 클라이언트는 조건을 모른다."""
    for contrast, entry in pairwise.sets.items():
        left, right = sorted(CONTRAST_PAIR[contrast])
        for item in entry.items:
            if item.target is None:
                assert item.render(left, right) == item.text
                continue
            forward = item.render(left, right)
            reversed_ = item.render(right, left)
            assert forward != reversed_, f"{item.item_id}: 좌우를 뒤집었는데 문면이 같다"
            assert {forward, reversed_} == {
                item.text.replace("{side}", SIDE_LABELS[0]).replace("{other}", SIDE_LABELS[1]),
                item.text.replace("{side}", SIDE_LABELS[1]).replace("{other}", SIDE_LABELS[0]),
            }
            assert "{side}" not in forward and "{other}" not in forward


def test_rendered_text_never_leaks_condition_labels(
    pairwise: pairwise_items.PairwiseAsset,
) -> None:
    """§1.2 — 참가자에게 조건 라벨이 가지 않는다."""
    for contrast, entry in pairwise.sets.items():
        left, right = sorted(CONTRAST_PAIR[contrast])
        for item in entry.items:
            text = item.render(left, right)
            for label in ("C1", "C2", "C3", "C4"):
                assert label not in text


def test_presentation_order_is_stable_within_contrast() -> None:
    """§4.10 · §0.5 — contrast 내 무작위, 같은 시드에 같은 순서(NT-08)."""
    first = pairwise_items.presentation_order("scope", "C1", "C3", "session-a")
    second = pairwise_items.presentation_order("scope", "C1", "C3", "session-a")
    assert [entry.item.item_id for entry in first] == [entry.item.item_id for entry in second]
    assert [entry.position for entry in first] == list(range(1, len(first) + 1))


def test_no_overall_index_in_asset() -> None:
    """§0.3 · §7.5 — 네 AI1의 종합 선호 순위·overall preference index를 산출하지 않는다."""
    document = json.loads(pairwise_items.asset_path().read_text(encoding="utf-8"))
    for banned in ("overall", "index", "total", "score", "ranking"):
        assert banned not in document


def test_rejects_fourth_contrast(tmp_path, monkeypatch) -> None:
    """§1.5-6 — 네 번째 pair를 자산에 넣으면 거부."""
    document = json.loads(pairwise_items.asset_path().read_text(encoding="utf-8"))
    document["contrasts"].append(
        {"contrast": "warmth", "pair": ["C1", "C4"], "items": [{"item_id": "w1", "text": "x"}]}
    )
    path = tmp_path / "pairwise_items_v0.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(pairwise_items, "asset_path", lambda: path)
    pairwise_items.reset_cache()
    try:
        with pytest.raises(PairwiseAssetError, match="contrast"):
            pairwise_items.load()
    finally:
        monkeypatch.undo()
        pairwise_items.reset_cache()


def test_each_contrast_has_two_to_three_items(
    pairwise: pairwise_items.PairwiseAsset,
) -> None:
    """부록 A.5 — contrast당 2–3문항 (PH-07 착지 계약)."""
    for contrast, entry in pairwise.sets.items():
        assert 2 <= len(entry.items) <= 3, f"{contrast}: {len(entry.items)}문항"


# --------------------------------------------------------------------------- #
# 모집 게이트 (PH-06 · PH-07) — 2026-08-24 `_v1` 착지
# --------------------------------------------------------------------------- #


def test_realvalue_assets_open_the_recruitment_gate(
    focal: rating_items.RatingAsset, pairwise: pairwise_items.PairwiseAsset
) -> None:
    """§11.2 — `_v1` 실값이 로더에 잡히고(`_v0`보다 우선), 게이트(`core/freeze.py`)가
    PH-06·PH-07을 더 이상 보고하지 않는다. `_v0`은 기록용으로 남아 있어도 무해하다."""
    assert focal.is_placeholder is False
    assert pairwise.is_placeholder is False
    assert focal.version == "focal_items_v1"
    assert pairwise.version == "pairwise_items_v1"


#: §4 서두(조건명·구성 원리 비공개) · §4.5(규범 어휘 금지) · 부록 D.3(선호 재활성화 금지)
#: — `screen_copy` 금지 목록과 같은 규율을 문항 자산에도 건다. `<TODO`는 착지 완료 표식이다.
BANNED_IN_ITEM_COPY: tuple[str, ...] = (
    "C1",
    "C2",
    "C3",
    "C4",
    "uptake",
    "elicitation",
    "actionability",
    "focal",
    "빠뜨린",
    "알아야 했던",
    "말했어야",
    "withholding",
    "무엇을 원했",
    "뭘 원했",
    "<TODO",
)


def test_item_copy_has_no_banned_expression(
    focal: rating_items.RatingAsset, pairwise: pairwise_items.PairwiseAsset
) -> None:
    """PH-06·07 착지 계약 — 참가자에게 나가는 문항 문자열(지시문·문면)에 금지 표현 0건.

    pairwise의 `pair` 키(조건명)는 서버 전용이라 검사 대상이 아니다 — 참가자에게는
    치환된 문면만 나간다(NT-38·`test_rendered_text_never_leaks_condition_labels`).
    """
    pieces: list[str] = []
    for block in focal.blocks:
        pieces.append(block.instruction)
        pieces.extend(item.text for item in block.items)
    for entry in pairwise.sets.values():
        pieces.extend(item.text for item in entry.items)
    joined = "\n".join(pieces)
    for banned in BANNED_IN_ITEM_COPY:
        assert banned not in joined, f"문항 자산에 금지 표현: {banned!r}"
