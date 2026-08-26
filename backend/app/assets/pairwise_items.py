"""pairwise boundary measures 자산 로더 (구현명세서 §4.10 · §7.5 · 부록 A.5).

세 contrast만 존재한다 — `sequence`(C2 vs C4) · `scope`(C1 vs C3) · `stopping`(C3 vs C4).
**코드에 다른 pair를 만들지 않는다**(§1.5-6). 이 모듈이 그 목록의 유일한 출처는 아니고
(`core/assignment.CONTRAST_PAIR`가 배정 쪽 정본이다), 여기서는 자산이 그 목록과 일치하는지를
검증한다 — 두 곳이 갈라지면 배정표의 좌우와 문항의 A/B 지칭이 어긋난다.

**A/B 치환이 이 모듈의 핵심**이다(부록 A.5 말미). 어떤 문항은 두 응답 중 **한쪽**을 지칭한다
("{side}의 조정은 … 정당했다"). 어떤 문항은 양쪽을 함께 지칭하며, 그때 나머지 한쪽은
`{other}`로 적는다("{side}의 방식이 {other}의 방식보다 …"). 자산은 지칭하는 쪽을 조건이
아니라 **성질**로 적는다:

    target ∈ {with_u, without_u, with_q, without_q}

서버가 배정된 좌우를 보고 그 성질을 가진 조건이 좌인지 우인지 판정해 "응답 A"/"응답 B"로
치환한다. 클라이언트는 조건을 모르고 치환된 문면만 받는다(§1.2 · NT-38).

⚠ `llm/`은 이 모듈을 import할 수 없다(NT-04) — pairwise 문항·응답은 §1.2 표에서 AI2·checker
전부 금지다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from app.core.assignment import CONTRAST_PAIR, CONTRASTS
from app.core.randomization import seeded_order

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "fixtures"

#: §4.10 — **앞의 것이 우선**. `_v1`이 2026-08-24 착지한 실값이고(PH-07 해소), `_v0`은
#: 기록으로 남긴 placeholder다(회귀 감지 — `rating_items`와 같은 규율).
ASSET_CANDIDATES: tuple[str, ...] = ("pairwise_items_v1.json", "pairwise_items_v0.json")
PLACEHOLDER_SUFFIX = "_v0.json"

#: §4.10 — 두 열의 라벨. 조건명이 아니라 **위치**다(어느 쪽이 focal인지 라벨링하지 않는다).
SIDE_LABELS: tuple[str, str] = ("응답 A", "응답 B")

#: 부록 A.5 — 문항이 지칭하는 한쪽의 **성질**. 조건 라벨이 아니다.
TARGET_TOKENS: frozenset[str] = frozenset({"with_u", "without_u", "with_q", "without_q"})

#: 성질 → 그 성질을 가진 조건. §0.4의 조건 구성(C1=R / C2=R+Q / C3=R+U / C4=R+U+Q)에서 나온다.
TARGET_CONDITIONS: Mapping[str, frozenset[str]] = {
    "with_u": frozenset({"C3", "C4"}),
    "without_u": frozenset({"C1", "C2"}),
    "with_q": frozenset({"C2", "C4"}),
    "without_q": frozenset({"C1", "C3"}),
}

#: 자산 문면의 치환 자리. `{side}`는 target이 가리키는 쪽, `{other}`는 반대쪽이다
#: (`{other}`는 양쪽을 함께 지칭하는 문항 — 예: 순서 선호 — 에만 쓴다).
SIDE_PLACEHOLDER = "{side}"
OTHER_PLACEHOLDER = "{other}"


class PairwiseAssetError(ValueError):
    """pairwise 문항 자산 계약 위반 — 기동 게이트(§5.4)가 이 예외로 기동을 끊는다."""


@dataclass(frozen=True, slots=True)
class PairwiseItem:
    """§7.5 `{item_id, contrast, text}` + 부록 A.5의 `target`."""

    item_id: str
    contrast: str
    text: str
    #: None이면 두 응답을 함께 묻는 문항이다(치환 없음).
    target: str | None

    def render(self, left_condition: str, right_condition: str) -> str:
        """§4.10 — `{side}`(target 쪽)·`{other}`(반대쪽)를 배정된 좌우에 맞춰
        "응답 A"/"응답 B"로 치환한다.

        치환이 **서버에서** 일어나는 것이 요점이다: 클라이언트가 조건을 받아 스스로 고르면
        조건 라벨이 참가자 번들에 실린다(§1.2 · NT-13).
        """
        if self.target is None:
            return self.text
        holders = TARGET_CONDITIONS[self.target]
        if left_condition in holders:
            side, other = SIDE_LABELS
        elif right_condition in holders:
            other, side = SIDE_LABELS
        else:  # pragma: no cover — 자산 계약이 이미 막는다
            raise PairwiseAssetError(
                f"{self.item_id}: target={self.target}를 가진 조건이 "
                f"({left_condition}, {right_condition}) 어느 쪽에도 없다"
            )
        return self.text.replace(SIDE_PLACEHOLDER, side).replace(OTHER_PLACEHOLDER, other)


@dataclass(frozen=True, slots=True)
class ContrastSet:
    contrast: str
    pair: frozenset[str]
    items: tuple[PairwiseItem, ...]


@dataclass(frozen=True, slots=True)
class PairwiseAsset:
    version: str
    source_path: Path
    is_placeholder: bool
    scale_min: int
    scale_max: int
    sets: Mapping[str, ContrastSet]

    def items_for(self, contrast: str) -> tuple[PairwiseItem, ...]:
        try:
            return self.sets[contrast].items
        except KeyError as exc:
            raise KeyError(f"알 수 없는 contrast: {contrast!r} (§1.5-6)") from exc

    def is_valid_value(self, value: object) -> bool:
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
    raise PairwiseAssetError(
        f"pairwise 문항 자산이 없다: {[str(FIXTURES_DIR / name) for name in ASSET_CANDIDATES]} "
        "(PH-07 자산 — `_v1`·`_v0` 어느 쪽도 없다)"
    )


def _parse_item(raw: Any, contrast: str, index: int, problems: list[str]) -> PairwiseItem | None:
    label = f"contrasts[{contrast}].items[{index}]"
    if not isinstance(raw, dict):
        problems.append(f"{label}: 객체여야 한다")
        return None

    item_id = str(raw.get("item_id", "")).strip()
    text = str(raw.get("text", "")).strip()
    if not item_id:
        problems.append(f"{label}.item_id: 필수")
    if not text:
        problems.append(f"{label}.text: 필수")

    target = raw.get("target")
    if target is not None:
        target = str(target)
        if target not in TARGET_TOKENS:
            problems.append(f"{label}.target: {sorted(TARGET_TOKENS)} 중 하나이거나 null이어야 한다")
            target = None
        elif SIDE_PLACEHOLDER not in text:
            problems.append(f"{label}: target이 있으면 문면에 {SIDE_PLACEHOLDER}가 있어야 한다 (부록 A.5)")
        else:
            # 이 contrast의 두 조건 중 **정확히 하나만** 그 성질을 가져야 A/B가 결정된다.
            holders = TARGET_CONDITIONS[target] & CONTRAST_PAIR.get(contrast, frozenset())
            if len(holders) != 1:
                problems.append(
                    f"{label}.target={target}: contrast {contrast}의 두 조건 중 정확히 하나여야 "
                    f"한쪽을 지칭할 수 있다 — 해당 조건 {sorted(holders)}"
                )
    elif SIDE_PLACEHOLDER in text or OTHER_PLACEHOLDER in text:
        problems.append(
            f"{label}: {SIDE_PLACEHOLDER}·{OTHER_PLACEHOLDER}가 있는데 target이 없다 (치환 불가)"
        )

    return PairwiseItem(item_id=item_id, contrast=contrast, text=text, target=target)


@lru_cache
def load() -> PairwiseAsset:
    """§4.10 문항 자산. 계약 위반이면 `PairwiseAssetError`."""
    path = asset_path()
    document = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    scale = document.get("scale") or {}
    scale_min = int(scale.get("min", 1))
    scale_max = int(scale.get("max", 7))
    if (scale_min, scale_max) != (1, 7):
        problems.append(f"scale: §0.5는 전 문항 1–7이다 — 실제 {scale_min}–{scale_max}")

    raw_sets = document.get("contrasts")
    if not isinstance(raw_sets, list):
        raise PairwiseAssetError(f"{path}: contrasts 배열이 없다 (§4.10)")

    sets: dict[str, ContrastSet] = {}
    for raw in raw_sets:
        contrast = str(raw.get("contrast", ""))
        if contrast not in CONTRASTS:
            problems.append(f"contrasts: {list(CONTRASTS)} 밖의 contrast — {contrast!r} (§1.5-6)")
            continue
        pair = frozenset(str(item) for item in raw.get("pair") or ())
        if pair != CONTRAST_PAIR[contrast]:
            problems.append(
                f"contrasts[{contrast}].pair: {sorted(CONTRAST_PAIR[contrast])}여야 한다 — 실제 {sorted(pair)}"
            )
        items = tuple(
            item
            for item in (
                _parse_item(entry, contrast, index, problems)
                for index, entry in enumerate(raw.get("items") or [])
            )
            if item is not None
        )
        if not items:
            problems.append(f"contrasts[{contrast}]: 문항이 비어 있다")
        sets[contrast] = ContrastSet(contrast=contrast, pair=CONTRAST_PAIR[contrast], items=items)

    missing = sorted(set(CONTRASTS) - set(sets))
    if missing:
        problems.append(f"contrasts: 누락 — {missing} (§0.4 세 pair만 존재한다)")

    all_ids = [item.item_id for entry in sets.values() for item in entry.items]
    duplicates = sorted({item for item in all_ids if all_ids.count(item) > 1})
    if duplicates:
        problems.append(f"item_id 중복: {duplicates}")

    # §7.5 — overall preference index 산출 금지. 자산에 총점 키가 생기면 여기서 끊는다.
    for banned in ("overall", "index", "total", "score", "ranking"):
        if banned in document:
            problems.append(f"{banned}: 종합 선호 지표는 산출하지 않는다 (§0.3 · §7.5)")

    if problems:
        joined = "\n  - ".join(problems)
        raise PairwiseAssetError(f"{path} pairwise 자산 계약 위반 (§4.10·§7.5):\n  - {joined}")

    return PairwiseAsset(
        version=str(document.get("version", "")),
        source_path=path,
        is_placeholder=path.name.endswith(PLACEHOLDER_SUFFIX),
        scale_min=scale_min,
        scale_max=scale_max,
        sets=sets,
    )


def validate() -> PairwiseAsset:
    """§5.4 기동 게이트."""
    return load()


@dataclass(frozen=True, slots=True)
class PresentedPairwiseItem:
    position: int
    item: PairwiseItem
    #: 좌우에 맞춰 치환된 문면. **이 문자열만** 클라이언트로 나간다.
    text: str


def presentation_order(
    contrast: str, left_condition: str, right_condition: str, *seed_parts: object
) -> tuple[PresentedPairwiseItem, ...]:
    """§4.10·§0.5 — contrast 내 무작위. contrast 순서·좌우는 배정표가 정한다(무작위 아님).

    같은 시드에는 항상 같은 순서다(NT-08). 시드에 contrast를 섞어 세 pair가 같은 순열을
    쓰지 않게 한다.
    """
    items = load().items_for(contrast)
    return tuple(
        PresentedPairwiseItem(
            position=position,
            item=item,
            text=item.render(left_condition, right_condition),
        )
        for position, item in enumerate(seeded_order(items, *seed_parts, contrast), start=1)
    )


def reset_cache() -> None:
    load.cache_clear()
