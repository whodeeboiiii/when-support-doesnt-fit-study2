"""focal 평정 + manipulation check 자산 로더 (구현명세서 §4.8 · §7.1 · §7.2 · 부록 A.4).

v1.0.1의 "코드 상수 12문항"에서 **자산 파일 로더**로 바뀌었다(부록 H.2). 이유는 §7.1·§7.2가
문항을 `fixtures/focal_items_v0.json`으로 지정했고 그 파일이 `<TODO: PH-06>` placeholder라
PI 승인 시 **코드 변경 없이** 교체되어야 하기 때문이다.

세 가지 규율이 걸린다.

1. **합산 금지**(§4.8·§7.1). 이 모듈에는 소계·척도·요인 구조가 없고 `ratings` 테이블에도
   합산 열이 없다(§8.1). construct는 라벨이지 점수가 아니다.
2. **블록 순서 1→2 고정, 무작위는 블록 내에서만**(§0.5·§4.8). 블록 2(MC)가 마지막인 것은
   §0.4의 동결 항목이다(D-37) — 순서를 흔들면 MC가 focal 경험 평정을 오염시킨다.
3. **문항 ID를 참가자에게 내리지 않는다.** `grounding_sufficiency`·`manipulation_check`는
   구성개념 라벨이고, 화면에는 **제시 위치**만 내려간다. 위치 → 문항 ID 매핑은 서버가 갖는다.

블록 2에는 **focal AI1 원문을 회색 카드로 재표시**한다(§4.8 · D-37 — referent = "재구성 직후의
첫 번째 AI 응답"). 카드 문자열은 이 모듈이 아니라 화면 조립기가 넣는다 — 자산은 어느 조건이
focal인지 모른다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.randomization import seeded_order

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "fixtures"

#: §4.8 — 실값 착지 시 `focal_items_v1.json`. v0은 placeholder다(모집 게이트 PH-06).
ASSET_CANDIDATES: tuple[str, ...] = ("focal_items_v1.json", "focal_items_v0.json")
PLACEHOLDER_SUFFIX = "_v0.json"

#: §8.1 `ratings.scope` — focal(블록 1) · mc(블록 2). 블록 순서는 이 튜플이 정본이다.
SCOPE_FOCAL = "focal"
SCOPE_MC = "mc"
BLOCK_ORDER: tuple[str, ...] = (SCOPE_FOCAL, SCOPE_MC)

#: §7.2 — MC 2문항의 고정 ID. 자산이 이 둘을 가져야 한다(§0.4 D-37).
MC_ITEM_IDS: frozenset[str] = frozenset({"mc_recognition", "mc_uptake"})


class RatingAssetError(ValueError):
    """문항 자산 계약 위반 — 기동 게이트(§5.4)가 이 예외로 기동을 끊는다."""


@dataclass(frozen=True, slots=True)
class RatingItem:
    """§7.1 `{item_id, construct, text, referent}`."""

    item_id: str
    construct: str
    text: str
    referent: str
    scope: str


@dataclass(frozen=True, slots=True)
class RatingBlock:
    scope: str
    instruction: str
    #: 블록 상단에 focal AI1 원문을 회색 카드로 재표시하는가 (§4.8 — MC 블록만 True).
    ai1_card: bool
    items: tuple[RatingItem, ...]


@dataclass(frozen=True, slots=True)
class RatingAsset:
    version: str
    source_path: Path
    is_placeholder: bool
    scale_min: int
    scale_max: int
    blocks: tuple[RatingBlock, ...]

    @property
    def items(self) -> tuple[RatingItem, ...]:
        return tuple(item for block in self.blocks for item in block.items)

    @property
    def item_count(self) -> int:
        return len(self.items)

    def block(self, scope: str) -> RatingBlock:
        for block in self.blocks:
            if block.scope == scope:
                return block
        raise KeyError(f"블록이 없다: {scope!r}")

    def by_id(self, item_id: str) -> RatingItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(f"문항이 없다: {item_id!r}")

    def is_valid_value(self, value: object) -> bool:
        """1–7 정수. bool은 int의 하위형이라 따로 막는다."""
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and self.scale_min <= value <= self.scale_max
        )


def asset_path() -> Path:
    for name in ASSET_CANDIDATES:
        candidate = FIXTURES_DIR / name
        if candidate.is_file():
            return candidate
    raise RatingAssetError(
        f"focal 문항 자산이 없다: {[str(FIXTURES_DIR / name) for name in ASSET_CANDIDATES]} "
        "(<TODO: PH-06>)"
    )


def _parse_item(raw: Any, scope: str, problems: list[str], index: int) -> RatingItem | None:
    label = f"blocks[{scope}].items[{index}]"
    if not isinstance(raw, dict):
        problems.append(f"{label}: 객체여야 한다")
        return None
    for key in ("item_id", "construct", "text", "referent"):
        if not str(raw.get(key, "")).strip():
            problems.append(f"{label}.{key}: 비어 있지 않은 문자열이어야 한다")
    return RatingItem(
        item_id=str(raw.get("item_id", "")),
        construct=str(raw.get("construct", "")),
        text=str(raw.get("text", "")),
        referent=str(raw.get("referent", "")),
        scope=scope,
    )


@lru_cache
def load() -> RatingAsset:
    """§4.8 문항 자산. 계약 위반이면 `RatingAssetError`."""
    path = asset_path()
    document = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    scale = document.get("scale") or {}
    scale_min = int(scale.get("min", 1))
    scale_max = int(scale.get("max", 7))
    if (scale_min, scale_max) != (1, 7):
        problems.append(f"scale: §0.5는 전 문항 1–7이다 — 실제 {scale_min}–{scale_max}")

    raw_blocks = document.get("blocks")
    if not isinstance(raw_blocks, list):
        raise RatingAssetError(f"{path}: blocks 배열이 없다 (§4.8)")

    blocks: list[RatingBlock] = []
    for raw in raw_blocks:
        scope = str(raw.get("scope", ""))
        items = tuple(
            item
            for item in (
                _parse_item(entry, scope, problems, index)
                for index, entry in enumerate(raw.get("items") or [])
            )
            if item is not None
        )
        if not items:
            problems.append(f"blocks[{scope}]: 문항이 비어 있다")
        blocks.append(
            RatingBlock(
                scope=scope,
                instruction=str(raw.get("instruction", "")),
                ai1_card=bool(raw.get("ai1_card", False)),
                items=items,
            )
        )

    # §4.8 · D-37 — 블록 순서 1(focal) → 2(mc) 고정. MC가 battery **마지막**이다.
    if tuple(block.scope for block in blocks) != BLOCK_ORDER:
        problems.append(
            f"blocks: 순서가 {list(BLOCK_ORDER)}여야 한다 (MC 마지막 — §0.4 D-37) — "
            f"실제 {[block.scope for block in blocks]}"
        )

    mc_block = next((block for block in blocks if block.scope == SCOPE_MC), None)
    if mc_block is not None:
        ids = {item.item_id for item in mc_block.items}
        if ids != MC_ITEM_IDS:
            problems.append(f"blocks[mc]: 문항 ID가 {sorted(MC_ITEM_IDS)}여야 한다 — 실제 {sorted(ids)}")
        if not mc_block.ai1_card:
            problems.append("blocks[mc].ai1_card: MC 블록은 AI1 카드 앵커가 필요하다 (§4.8 · D-37)")

    focal_block = next((block for block in blocks if block.scope == SCOPE_FOCAL), None)
    if focal_block is not None and focal_block.ai1_card:
        # 블록 1은 "대화 전체"가 referent다 — AI1 카드를 붙이면 referent가 흐려진다(§4.8).
        problems.append("blocks[focal].ai1_card: 블록 1에는 AI1 카드를 두지 않는다 (§4.8)")

    all_ids = [item.item_id for block in blocks for item in block.items]
    duplicates = sorted({item for item in all_ids if all_ids.count(item) > 1})
    if duplicates:
        problems.append(f"item_id 중복: {duplicates}")

    # §7.1 — 합산 금지. 자산에 소계·총점 키가 생기면 여기서 끊는다.
    for banned in ("total", "subscales", "score", "sum"):
        if banned in document:
            problems.append(f"{banned}: 합산 필드는 두지 않는다 (§0.4 · §7.1)")

    if problems:
        joined = "\n  - ".join(problems)
        raise RatingAssetError(f"{path} 문항 자산 계약 위반 (§4.8·§7.1·§7.2):\n  - {joined}")

    return RatingAsset(
        version=str(document.get("version", "")),
        source_path=path,
        is_placeholder=path.name.endswith(PLACEHOLDER_SUFFIX),
        scale_min=scale_min,
        scale_max=scale_max,
        blocks=tuple(blocks),
    )


def validate() -> RatingAsset:
    """§5.4 기동 게이트."""
    return load()


@dataclass(frozen=True, slots=True)
class PresentedRatingItem:
    """제시 1건 — 위치·블록·문항. `position`이 `ratings.display_order`가 된다(§8.1)."""

    position: int
    scope: str
    item: RatingItem


def presentation_order(*seed_parts: object) -> tuple[PresentedRatingItem, ...]:
    """§4.8·§0.5 — **블록 순서는 focal→mc 고정, 무작위는 블록 내에서만**.

    같은 시드(세션)에는 항상 같은 순서다 — 새로고침이 순서를 다시 뽑지 않는다(NT-08).
    시드에 블록 scope를 섞어 두 블록이 같은 순열을 쓰지 않게 한다.
    """
    asset = load()
    presented: list[PresentedRatingItem] = []
    position = 0
    for block in asset.blocks:
        for item in seeded_order(block.items, *seed_parts, block.scope):
            position += 1
            presented.append(
                PresentedRatingItem(position=position, scope=block.scope, item=item)
            )
    return tuple(presented)


def reset_cache() -> None:
    load.cache_clear()
