"""참가자 API — 대안 노출·pairwise (구현명세서 §8.2 · §3.3 · §4.9 · §4.10 · D-29).

v2.0 신설(부록 H.3). 이 구간의 불변식 셋.

1. **focal 측정(SS05) 완료 후에만 존재한다**(NT-31). 상태로 강제된다 — SS06·SS07은
   `POST /ratings`를 지나야 도달하고, 그 전에는 `alt_exposures`·`pairwise_views` 행 자체가
   없어서 화면 조립기가 대안 자극을 만들 자료를 갖지 못한다.
2. **순서·좌우는 배정표가 정한다**(NT-33·38). 이 파일에 무작위가 없다 — 무작위는 pairwise
   **문항 순서**뿐이고 그건 자산 로더가 시드로 재현한다.
3. **position 건너뛰기 불가**(NT-33). 서버가 `alt_index`·`pair_index`를 소유하고, 요청이
   그 값과 다르면 409다.

대안에 대해서는 **User1·sidecar·AI2·개별 평정을 받지 않는다**(§0.3 · 초안 §7.10). 그런
엔드포인트가 이 파일에 없다는 것이 그 결정이다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import store
from app.api.deps import CurrentSession, DbSession, require_active
from app.api.state_payload import build_state
from app.assets import pairwise_items
from app.core.idempotency import is_replay_position, is_replay_ss
from app.core.state_machine import (
    ALT_POSITIONS,
    PAIR_POSITIONS,
    IllegalTransition,
    SsState,
    assert_position,
    assert_ss_transition,
)
from app.models import tables

router = APIRouter(prefix="/api", tags=["participant"])


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(exc: IllegalTransition) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# --------------------------------------------------------------------------- #
# P9 대안 노출 ×3 (§4.9 · SS06)
# --------------------------------------------------------------------------- #


async def advance_alt(db: AsyncSession, session: tables.Session) -> dict[str, Any]:
    """§8.2 `POST /advance {from_screen:"P9"}` — `advanced_at` 기록 + index 증가.

    세 번째를 넘기면 SS07로 가고, 그 자리에서 pairwise 행 셋을 배정표대로 만든다.
    """
    position = session.alt_index or 1
    row = await store.alt_exposure(db, session.id, position)
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"대안 노출 {position}이 없습니다")

    if row.advanced_at is None:
        row.advanced_at = _now()

    if position < ALT_POSITIONS:
        session.alt_index = position + 1
        await db.flush()
        return await build_state(db, session)

    try:
        assert_ss_transition(SsState(session.ss_state), SsState.PAIRWISE)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    session.ss_state = SsState.PAIRWISE.value
    session.alt_index = None
    session.pair_index = 1
    await _open_pairwise_views(db, session)
    await db.flush()
    return await build_state(db, session)


async def _open_pairwise_views(db: AsyncSession, session: tables.Session) -> None:
    """§3.3 — 세 pair를 배정표의 순서·좌우로 만든다. 최초 표시 후 불변(NT-38).

    `focal_included`·`focal_side`는 여기서 정해진다(초안 §7.12 sensitivity). 참가자에게는
    어느 쪽이 focal인지 라벨링하지 않지만 서버는 기록한다(§4.10).
    """
    participant = await db.get(tables.Participant, session.participant_no)
    if participant is None or not participant.pair_order:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{session.participant_no}의 pair 배정이 없습니다 (§5.2)",
        )
    pair_order = list(participant.pair_order)
    pair_sides = dict(participant.pair_sides or {})
    focal = participant.focal_condition

    for position, contrast in enumerate(pair_order, start=1):
        if await store.pairwise_view(db, session.id, position) is not None:
            continue
        sides = list(pair_sides.get(contrast) or ())
        if len(sides) != 2:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"{contrast}의 좌우 배정이 없습니다 (§5.2)"
            )
        left, right = str(sides[0]), str(sides[1])
        focal_side = "left" if focal == left else "right" if focal == right else None
        db.add(
            tables.PairwiseView(
                session_id=session.id,
                position=position,
                contrast=contrast,
                left_condition=left,
                right_condition=right,
                focal_included=focal_side is not None,
                focal_side=focal_side,
                rendered_at=_now(),
            )
        )
    await db.flush()


# --------------------------------------------------------------------------- #
# P10 pairwise ×3 (§4.10 · SS07)
# --------------------------------------------------------------------------- #


class PairwiseAnswer(BaseModel):
    position: int = Field(ge=1)
    value: int


class PairwiseRequest(BaseModel):
    items: list[PairwiseAnswer]


@router.post("/pairwise/{position}")
async def submit_pairwise(
    position: int, payload: PairwiseRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — position = `pair_index`. 전 문항 필수. 제출 → 다음 pair → 3 완료 시 SS08."""
    require_active(session)
    if is_replay_position(
        SsState(session.ss_state), session.pair_index, position, step_ss=SsState.PAIRWISE
    ):
        return {"replayed": True, **await build_state(db, session)}
    if SsState(session.ss_state) is not SsState.PAIRWISE:
        raise HTTPException(status.HTTP_409_CONFLICT, "비교 단계가 아닙니다")
    try:
        assert_position(session.pair_index, position, limit=PAIR_POSITIONS, label="pair")
    except IllegalTransition as exc:
        raise _conflict(exc) from exc

    view = await store.pairwise_view(db, session.id, position)
    if view is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"비교 {position}이 없습니다")

    asset = pairwise_items.load()
    presented = pairwise_items.presentation_order(
        view.contrast, view.left_condition, view.right_condition, session.id
    )
    positions = sorted(answer.position for answer in payload.items)
    if positions != list(range(1, len(presented) + 1)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{len(presented)}문항 전부에 응답이 필요합니다"
        )
    for answer in payload.items:
        if not asset.is_valid_value(answer.value):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"응답은 {asset.scale_min}–{asset.scale_max} 사이여야 합니다",
            )

    values = {answer.position: answer.value for answer in payload.items}
    for entry in presented:
        db.add(
            tables.PairwiseResponse(
                pairwise_view_id=view.id,
                # 위치 → 문항 ID 매핑은 서버만 안다(§4.10).
                item_id=entry.item.item_id,
                value=values[entry.position],
                display_order=entry.position,
            )
        )
    view.submitted_at = _now()

    if position < PAIR_POSITIONS:
        session.pair_index = position + 1
        await db.flush()
        return {"replayed": False, **await build_state(db, session)}

    try:
        assert_ss_transition(SsState(session.ss_state), SsState.INTERVIEW)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    session.ss_state = SsState.INTERVIEW.value
    session.pair_index = None
    await db.flush()
    return {"replayed": False, **await build_state(db, session)}
