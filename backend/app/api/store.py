"""저장 상태 조회·기록 헬퍼 (구현명세서 §8.1 · §3.5).

라우터와 화면 payload 조립기가 같은 조회를 쓴다. 여기 모아 두는 이유는 §3.5의 복구 규율
때문이다 — "저장 지점 복원"이 성립하려면 **화면을 그리는 조회**와 **제출을 판정하는 조회**가
같은 행을 봐야 한다. 두 곳에 각각 쿼리를 쓰면 언젠가 한쪽만 조건이 바뀐다.

`turns`·`generations`처럼 여러 행이 생길 수 있는 테이블은 **최신 1행**이 아니라 의미가
정해진 1행을 돌려준다(예: `final=True` 생성물). 사후 재구성(NT-15)은 전 행을 보지만 화면·
판정은 확정된 것만 본다.

`checkpoint_edits`만 성격이 다르다 — **누적**이므로(§3.4) 조회도 "segment별 마지막 행"이라는
의미를 담아야 한다. `effective_edits()`가 그 자리다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import tables
from app.security import fernet


async def focal_run(db: AsyncSession, session_id: uuid.UUID) -> tables.FocalRun | None:
    """§8.1 — 세션당 1행 (D-23). 없으면 아직 F0에 들어오지 않은 것이다."""
    result = await db.execute(
        select(tables.FocalRun).where(tables.FocalRun.session_id == session_id)
    )
    return result.scalars().one_or_none()


async def turn(db: AsyncSession, focal_run_id: uuid.UUID, role: str) -> tables.Turn | None:
    result = await db.execute(
        select(tables.Turn).where(
            tables.Turn.focal_run_id == focal_run_id, tables.Turn.role == role
        )
    )
    return result.scalars().first()


async def turns(db: AsyncSession, focal_run_id: uuid.UUID) -> list[tables.Turn]:
    """§3.2 인과 창 순서대로 — ai1 → user1 → ai2 → user2.

    정렬 키를 `coalesce(rendered_at, submitted_at)`로 잡는 이유: AI 턴은 `rendered_at`만,
    참가자 턴은 `submitted_at`만 채워진다. 두 열을 나란히 쓰면 NULL 정렬 규칙에 따라
    순서가 뒤집히고, 그러면 R2 transcript가 대화가 아니라 목록이 된다.
    """
    when = func.coalesce(tables.Turn.rendered_at, tables.Turn.submitted_at)
    result = await db.execute(
        select(tables.Turn)
        .where(tables.Turn.focal_run_id == focal_run_id)
        .order_by(when, tables.Turn.id)
    )
    return list(result.scalars().all())


async def sidecar(db: AsyncSession, focal_run_id: uuid.UUID) -> tables.SidecarEntry | None:
    result = await db.execute(
        select(tables.SidecarEntry).where(tables.SidecarEntry.focal_run_id == focal_run_id)
    )
    return result.scalars().one_or_none()


async def downstream(db: AsyncSession, focal_run_id: uuid.UUID) -> tables.DownstreamAction | None:
    result = await db.execute(
        select(tables.DownstreamAction).where(
            tables.DownstreamAction.focal_run_id == focal_run_id
        )
    )
    return result.scalars().one_or_none()


async def final_generation(
    db: AsyncSession, focal_run_id: uuid.UUID
) -> tables.Generation | None:
    """§9.1 — 표시된 산출물은 `final=True` 1건뿐이다(정상·재생성·fallback 무관)."""
    result = await db.execute(
        select(tables.Generation).where(
            tables.Generation.focal_run_id == focal_run_id,
            tables.Generation.final.is_(True),
        )
    )
    return result.scalars().first()


async def generations(db: AsyncSession, focal_run_id: uuid.UUID) -> list[tables.Generation]:
    """§8.4 audit 재구성용 — 전 시도 (NT-15)."""
    result = await db.execute(
        select(tables.Generation)
        .where(tables.Generation.focal_run_id == focal_run_id)
        .order_by(tables.Generation.attempt, tables.Generation.created_at)
    )
    return list(result.scalars().all())


async def ratings(db: AsyncSession, session_id: uuid.UUID) -> list[tables.Rating]:
    result = await db.execute(
        select(tables.Rating)
        .where(tables.Rating.session_id == session_id)
        .order_by(tables.Rating.display_order)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------- #
# checkpoint 수정 (§3.4 — 누적 저장, 최종본 = segment별 마지막 행)
# --------------------------------------------------------------------------- #


async def checkpoint_edits(
    db: AsyncSession, session_id: uuid.UUID
) -> list[tables.CheckpointEdit]:
    """전 행 — 시간순. 콘솔 R2의 diff와 export가 이 목록을 그대로 쓴다."""
    result = await db.execute(
        select(tables.CheckpointEdit)
        .where(tables.CheckpointEdit.session_id == session_id)
        .order_by(tables.CheckpointEdit.edited_at, tables.CheckpointEdit.id)
    )
    return list(result.scalars().all())


async def effective_edits(db: AsyncSession, session_id: uuid.UUID) -> dict[str, str]:
    """§3.4 — segment → **최종 수정본**(마지막 행). effective checkpoint 조립의 입력이다.

    복호화가 여기서 일어난다(§2.9 지점 목록의 "AI2 payload용 수정본 읽기"·"참가자 화면
    재표시"). 평문은 호출부가 조립에만 쓰고 audit에는 값을 남기지 않는다.
    """
    latest: dict[str, str] = {}
    for row in await checkpoint_edits(db, session_id):
        if row.edited:
            latest[row.segment] = fernet.decrypt(row.edited)
    return latest


# --------------------------------------------------------------------------- #
# 대안 노출 · pairwise (§3.3)
# --------------------------------------------------------------------------- #


async def alt_exposure(
    db: AsyncSession, session_id: uuid.UUID, position: int
) -> tables.AltExposure | None:
    result = await db.execute(
        select(tables.AltExposure).where(
            tables.AltExposure.session_id == session_id,
            tables.AltExposure.position == position,
        )
    )
    return result.scalars().one_or_none()


async def alt_exposures(db: AsyncSession, session_id: uuid.UUID) -> list[tables.AltExposure]:
    result = await db.execute(
        select(tables.AltExposure)
        .where(tables.AltExposure.session_id == session_id)
        .order_by(tables.AltExposure.position)
    )
    return list(result.scalars().all())


async def pairwise_view(
    db: AsyncSession, session_id: uuid.UUID, position: int
) -> tables.PairwiseView | None:
    result = await db.execute(
        select(tables.PairwiseView).where(
            tables.PairwiseView.session_id == session_id,
            tables.PairwiseView.position == position,
        )
    )
    return result.scalars().one_or_none()


async def pairwise_views(db: AsyncSession, session_id: uuid.UUID) -> list[tables.PairwiseView]:
    result = await db.execute(
        select(tables.PairwiseView)
        .where(tables.PairwiseView.session_id == session_id)
        .order_by(tables.PairwiseView.position)
    )
    return list(result.scalars().all())


async def pairwise_responses(
    db: AsyncSession, view_id: uuid.UUID
) -> list[tables.PairwiseResponse]:
    result = await db.execute(
        select(tables.PairwiseResponse)
        .where(tables.PairwiseResponse.pairwise_view_id == view_id)
        .order_by(tables.PairwiseResponse.display_order)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------- #
# 세션·이벤트
# --------------------------------------------------------------------------- #


async def sessions_of_participant(
    db: AsyncSession, participant_no: str, statuses: Sequence[str] | None = None
) -> list[tables.Session]:
    query = select(tables.Session).where(tables.Session.participant_no == participant_no)
    if statuses is not None:
        query = query.where(tables.Session.status.in_(list(statuses)))
    result = await db.execute(query.order_by(tables.Session.created_at))
    return list(result.scalars().all())


async def record_event(
    db: AsyncSession,
    session_id: uuid.UUID,
    event_type: str,
    *,
    payload: dict[str, Any] | None = None,
    client_ts: datetime | None = None,
) -> tables.Event:
    """§2.11 — beacon·상태 기록. **파생 지표는 계산하지 않는다**(`response_latency` 폐기)."""
    row = tables.Event(
        session_id=session_id,
        type=event_type,
        payload=payload,
        client_ts=client_ts,
    )
    db.add(row)
    await db.flush()
    return row
