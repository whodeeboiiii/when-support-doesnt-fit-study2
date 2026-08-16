"""branch 평정 12문항 (구현명세서 §7.3 [정본, 초안 §7.10] · §4.9 2블록 · D-22).

**문항 원문은 [정본]이다 — 한 글자도 고치지 않는다**(§0.4 "윤문 금지"). 자산 계약 테스트가
명세서 원문과 글자 단위로 대조한다.

세 가지 규율이 여기에 걸린다.

1. **합산 금지**(§0.4·§7.3). 이 모듈에는 소계·척도·요인 구조가 없다. `ratings` 테이블에도
   합산 열이 없다(§8.1). 12개는 12개로 남는다.
2. **전 종결 유형 동일**(D-22). reply·no_reply·end가 같은 12문항·같은 2블록을 받는다.
   축소형이 없으므로 이 모듈에 종결 유형 인자가 없다.
3. **문항 ID를 참가자에게 내리지 않는다.** `overreach`·`premature_withdrawal` 같은 변수명은
   구성개념 라벨이고, §4.10이 금지하는 construct label 노출과 같은 종류다. 화면에는 **제시
   위치**(display_order)만 내려가고 위치 → 문항 ID 매핑은 서버가 갖는다(§4.2 렌더 규율의 확장).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.randomization import seeded_order

#: §0.5 — 전 문항 1(전혀 그렇지 않다)–7(매우 그렇다)
SCALE_MIN = 1
SCALE_MAX = 7

#: §4.9 — 블록 1은 문항 1·2(AI1 앵커), 블록 2는 문항 3–12(상호작용 전체). 블록 순서는 1→2 고정.
BLOCK_ANCHOR = 1
BLOCK_INTERACTION = 2


@dataclass(frozen=True, slots=True)
class RatingItem:
    """§7.3 표의 한 행. `role`은 분석 문서용 주석이며 참가자 화면에 내려가지 않는다."""

    number: int
    item_id: str
    text: str
    block: int
    role: str


#: §7.3 표 — 순서는 표의 번호 순이다. **제시 순서가 아니다**(제시는 블록 내 무작위 — D-13).
RATING_ITEMS: tuple[RatingItem, ...] = (
    RatingItem(
        1,
        "recognition",
        "AI가 내가 문제 삼은 지점을 알아차렸다고 느꼈다.",
        BLOCK_ANCHOR,
        "manipulation/fidelity check",
    ),
    RatingItem(
        2,
        "substantive_uptake",
        "AI가 그 문제를 실제 다음 반응에 반영했다고 느꼈다.",
        BLOCK_ANCHOR,
        "enacted uptake check",
    ),
    RatingItem(
        3,
        "grounding_sufficiency_1",
        "AI가 다음 지원을 적절히 이어가기 위해 필요한 내용을 충분히 이해했다고 느꼈다.",
        BLOCK_INTERACTION,
        "grounding sufficiency",
    ),
    RatingItem(
        4,
        "grounding_sufficiency_2",
        "다음 지원의 방향과 범위가 충분히 좁혀졌다고 느꼈다.",
        BLOCK_INTERACTION,
        "grounding sufficiency",
    ),
    RatingItem(
        5,
        "correction_effort_1",
        "이 AI와 대화를 다시 맞추기 위해 내가 들여야 할 노력이 크게 느껴졌다.",
        BLOCK_INTERACTION,
        "correction effort",
    ),
    RatingItem(
        6,
        "correction_effort_2",
        "AI가 이해할 수 있도록 맥락을 다시 정리하고 표현하는 일이 부담스럽게 느껴졌다.",
        BLOCK_INTERACTION,
        "correction effort",
    ),
    RatingItem(
        7,
        "reinvestment",
        "이 AI에게 조금 더 설명하면 다음 반응이 나아질 것 같았다.",
        BLOCK_INTERACTION,
        "mechanism probe",
    ),
    RatingItem(
        8,
        "clarification_need",
        "다음 지원을 하기 전에 AI가 나에게 추가로 확인해야 할 것이 남아 있다고 느꼈다.",
        BLOCK_INTERACTION,
        "evidence state probe",
    ),
    RatingItem(
        9,
        "overreach",
        "AI가 내가 표현하지 않은 것을 지나치게 추론했다고 느꼈다.",
        BLOCK_INTERACTION,
        "boundary failure ①",
    ),
    RatingItem(
        10,
        "premature_withdrawal",
        "AI가 내가 여전히 원할 수 있는 도움까지 너무 빨리 거두었다고 느꼈다.",
        BLOCK_INTERACTION,
        "boundary failure ②",
    ),
    RatingItem(
        11,
        "autonomy",
        "대화의 다음 방향을 내가 원하는 만큼 결정할 수 있다고 느꼈다.",
        BLOCK_INTERACTION,
        "exploratory",
    ),
    RatingItem(
        12,
        "support_purpose_clarity",
        "이 반응을 거치면서 지금 AI에게 어떤 도움을 받고 싶은지가 더 분명해졌다.",
        BLOCK_INTERACTION,
        "exploratory",
    ),
)

ITEM_COUNT = len(RATING_ITEMS)
ITEMS_BY_ID = {item.item_id: item for item in RATING_ITEMS}


def items_in_block(block: int) -> tuple[RatingItem, ...]:
    return tuple(item for item in RATING_ITEMS if item.block == block)


@dataclass(frozen=True, slots=True)
class PresentedRatingItem:
    """제시 1건 — 위치·블록·문항. `position`이 `ratings.display_order`가 된다(§8.1)."""

    position: int
    block: int
    item: RatingItem


def presentation_order(*seed_parts: object) -> tuple[PresentedRatingItem, ...]:
    """§4.9·D-13 — **블록 순서는 1→2 고정, 무작위는 블록 내에서만**.

    같은 시드(세션·branch)에는 항상 같은 순서다 — 새로고침이 순서를 다시 뽑지 않는다(NT-08).
    """
    presented: list[PresentedRatingItem] = []
    position = 0
    for block in (BLOCK_ANCHOR, BLOCK_INTERACTION):
        for item in seeded_order(items_in_block(block), *seed_parts, block):
            position += 1
            presented.append(PresentedRatingItem(position=position, block=block, item=item))
    return tuple(presented)


def is_valid_value(value: object) -> bool:
    """1–7 정수. bool은 int의 하위형이라 따로 막는다."""
    return isinstance(value, int) and not isinstance(value, bool) and SCALE_MIN <= value <= SCALE_MAX
