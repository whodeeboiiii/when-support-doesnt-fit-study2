"""저장 상태 조회·기록 헬퍼 (구현명세서 §8.1 · §3.5).

라우터와 화면 payload 조립기가 같은 조회를 쓴다. 여기 모아 두는 이유는 §3.5의 복구 규율
때문이다 — "저장 지점 복원"이 성립하려면 **화면을 그리는 조회**와 **제출을 판정하는 조회**가
같은 행을 봐야 한다. 두 곳에 각각 쿼리를 쓰면 언젠가 한쪽만 조건이 바뀐다.

`turns`·`generations`처럼 branch당 여러 행이 생길 수 있는 테이블은 **최신 1행**이 아니라
의미가 정해진 1행을 돌려준다(예: `final=True` 생성물). 사후 재구성(NT-15)은 전 행을 보지만
화면·판정은 확정된 것만 본다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import tables


async def branch_by_index(
    db: AsyncSession, session_id: uuid.UUID, branch_index: int
) -> tables.Branch | None:
    result = await db.execute(
        select(tables.Branch).where(
            tables.Branch.session_id == session_id,
            tables.Branch.branch_index == branch_index,
        )
    )
    return result.scalars().one_or_none()


async def branches_of(db: AsyncSession, session_id: uuid.UUID) -> list[tables.Branch]:
    result = await db.execute(
        select(tables.Branch)
        .where(tables.Branch.session_id == session_id)
        .order_by(tables.Branch.branch_index)
    )
    return list(result.scalars().all())


async def turn(db: AsyncSession, branch_id: uuid.UUID, role: str) -> tables.Turn | None:
    result = await db.execute(
        select(tables.Turn).where(tables.Turn.branch_id == branch_id, tables.Turn.role == role)
    )
    return result.scalars().first()


async def sidecar(db: AsyncSession, branch_id: uuid.UUID) -> tables.SidecarEntry | None:
    result = await db.execute(
        select(tables.SidecarEntry).where(tables.SidecarEntry.branch_id == branch_id)
    )
    return result.scalars().one_or_none()


async def downstream(db: AsyncSession, branch_id: uuid.UUID) -> tables.DownstreamAction | None:
    result = await db.execute(
        select(tables.DownstreamAction).where(tables.DownstreamAction.branch_id == branch_id)
    )
    return result.scalars().one_or_none()


async def final_generation(db: AsyncSession, branch_id: uuid.UUID) -> tables.Generation | None:
    """§9.1 — 표시된 산출물은 `final=True` 1건뿐이다(정상·재생성·fallback 무관)."""
    result = await db.execute(
        select(tables.Generation).where(
            tables.Generation.branch_id == branch_id,
            tables.Generation.final.is_(True),
        )
    )
    return result.scalars().first()


async def ratings(db: AsyncSession, branch_id: uuid.UUID) -> list[tables.Rating]:
    result = await db.execute(
        select(tables.Rating)
        .where(tables.Rating.branch_id == branch_id)
        .order_by(tables.Rating.display_order)
    )
    return list(result.scalars().all())


async def presurvey_rows(
    db: AsyncSession, session_id: uuid.UUID
) -> list[tables.PresurveyResponse]:
    result = await db.execute(
        select(tables.PresurveyResponse)
        .where(tables.PresurveyResponse.session_id == session_id)
        .order_by(tables.PresurveyResponse.display_order)
    )
    return list(result.scalars().all())


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
    branch_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    client_ts: datetime | None = None,
) -> tables.Event:
    """§2.11·§7.5 — beacon·상태 기록. 파생 지표는 계산하지 않는다(분석 시점 계산)."""
    row = tables.Event(
        session_id=session_id,
        branch_id=branch_id,
        type=event_type,
        payload=payload,
        client_ts=client_ts,
    )
    db.add(row)
    await db.flush()
    return row
