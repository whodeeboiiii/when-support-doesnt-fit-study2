"""참가자 API — branch 수준 (구현명세서 §8.2 · §3.2 · §4.5–§4.9).

한 branch의 인과 창은 **AI1 → User1 → (sidecar) → AI2 → downstream 1회 → 평정**이고, AI3는
없다(§0.4). 이 파일의 엔드포인트 순서가 그 창 자체다.

no_reply/end branch는 sidecar 다음이 곧 평정이다(§3.2 · NT-17). 그것은 미완이 아니라 다른
trajectory이므로, 여기에 "AI2를 못 받은 branch" 같은 보정 경로를 만들지 않는다.

⚠ 이 라우터는 타 branch의 데이터를 한 번도 읽지 않는다(§3.4 · NT-10). branch 격리는 AI2
payload 조립기(NS3)만의 문제가 아니라 화면·저장 경로 전체의 불변식이다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api import store
from app.api.deps import CurrentSession, DbSession, require_active
from app.api.participant import open_branch
from app.api.state_payload import build_state
from app.assets import rating_items, screen_copy
from app.core.idempotency import is_replay_b
from app.core.state_machine import (
    BState,
    Disposition,
    IllegalTransition,
    SsState,
    assert_b_transition,
    assert_ss_transition,
    b_state_after_sidecar,
    has_ai2,
)
from app.llm import ai2_pipeline
from app.models import tables
from app.security import fernet

router = APIRouter(prefix="/api/branch", tags=["participant"])

BRANCH_COUNT = 4


def _now() -> datetime:
    return datetime.now(UTC)


async def _resolve(
    db: DbSession, session: tables.Session, branch_index: int
) -> tables.Branch:
    require_active(session)
    if SsState(session.ss_state) is not SsState.BRANCH_BLOCK:
        raise HTTPException(status.HTTP_409_CONFLICT, "branch 단계가 아닙니다")
    branch = await store.branch_by_index(db, session.id, branch_index)
    if branch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"branch {branch_index}가 없습니다")
    return branch


def _require_b(branch: tables.Branch, target: BState) -> None:
    try:
        assert_b_transition(BState(branch.b_state), target)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


async def _reply(db: DbSession, session: tables.Session, replayed: bool) -> dict[str, Any]:
    await db.flush()
    return {"replayed": replayed, **await build_state(db, session)}


# --------------------------------------------------------------------------- #
# P5 User1 (§4.5 · B2)
# --------------------------------------------------------------------------- #


class User1Request(BaseModel):
    disposition: Literal["reply", "no_reply", "end"]
    text: str | None = None


@router.post("/{branch_index}/user1")
async def submit_user1(
    branch_index: int, payload: User1Request, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — B2 종결. 세 분기 모두 유효한 종결이다(§3.2)."""
    branch = await _resolve(db, session, branch_index)
    if is_replay_b(BState(branch.b_state), BState.SIDECAR):
        return await _reply(db, session, replayed=True)

    if BState(branch.b_state) is BState.AI1_SHOWN:
        # 렌더 beacon이 유실된 경우 — 시간 beacon이 연구 상태를 막지 않는다(§2.11).
        branch.b_state = BState.USER1.value
    _require_b(branch, BState.SIDECAR)

    disposition = Disposition(payload.disposition)
    text = (payload.text or "").strip()
    if disposition is Disposition.REPLY and not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "보낼 내용을 적어주세요")
    if disposition is not Disposition.REPLY and text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "답장하지 않는 선택에는 본문이 없습니다")

    if text:
        db.add(
            tables.Turn(
                branch_id=branch.id,
                role="user1",
                text=fernet.encrypt(text),
                # `<TODO: NS3 — §6.4 referential normalization 결과를 text_normalized에 저장>`
                text_normalized=None,
                submitted_at=_now(),
            )
        )
    branch.user1_disposition = disposition.value
    branch.b_state = BState.SIDECAR.value
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P6 private sidecar (§4.6 · B3)
# --------------------------------------------------------------------------- #


class SidecarRequest(BaseModel):
    choice: Literal["none", "has", "skip"]
    free_text: str | None = None
    relevance: int | None = Field(default=None, ge=1, le=7)
    reason: str | None = None


@router.post("/{branch_index}/sidecar")
async def submit_sidecar(
    branch_index: int, payload: SidecarRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — B3 제출·건너뛰기. **이 내용은 어떤 LLM payload에도 들어가지 않는다**(§1.2)."""
    branch = await _resolve(db, session, branch_index)
    if is_replay_b(BState(branch.b_state), BState.AI2):
        return await _reply(db, session, replayed=True)
    if BState(branch.b_state) is not BState.SIDECAR:
        raise HTTPException(status.HTTP_409_CONFLICT, "sidecar 단계가 아닙니다")

    free_text = (payload.free_text or "").strip()
    reason = (payload.reason or "").strip()
    if payload.choice == "has":
        if not free_text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "내용을 적어주세요")
        if payload.relevance is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "관련성 평정이 필요합니다")
    elif free_text or reason or payload.relevance is not None:
        # "없음"·"건너뛰기"에 본문이 딸려 오면 화면과 저장이 어긋난 것이다 — 저장하지 않는다.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택과 입력이 맞지 않습니다")

    db.add(
        tables.SidecarEntry(
            branch_id=branch.id,
            choice=payload.choice,
            free_text=fernet.encrypt(free_text) if free_text else None,
            relevance_1_7=payload.relevance,
            reason_text=fernet.encrypt(reason) if reason else None,
        )
    )
    target = b_state_after_sidecar(Disposition(branch.user1_disposition))
    _require_b(branch, target)
    branch.b_state = target.value
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P7 AI2 (§4.7 · §6 · B4)
# --------------------------------------------------------------------------- #


@router.post("/{branch_index}/ai2")
async def run_ai2(
    branch_index: int, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — B4 트리거(**reply branch만**). 재호출은 저장된 산출물을 그대로 돌려준다.

    §8.3-2가 요구하는 시간 순서(sidecar 제출 후에만 AI2 호출)는 상태로 강제된다: B4는 sidecar
    제출로만 도달하고, 그 전에는 이 엔드포인트가 409다(NT-16의 구조적 근거).
    """
    branch = await _resolve(db, session, branch_index)
    if not has_ai2(branch.user1_disposition):
        # NT-17 — no_reply/end branch에는 AI2가 없다. 상태 검사만으로도 막히지만,
        # "이 branch에는 AI2 단계가 존재하지 않는다"를 명시적으로 거절한다.
        raise HTTPException(status.HTTP_409_CONFLICT, "이 branch에는 AI2 단계가 없습니다")
    if BState(branch.b_state) is not BState.AI2:
        raise HTTPException(status.HTTP_409_CONFLICT, "AI2 단계가 아닙니다")

    existing = await store.final_generation(db, branch.id)
    if existing is not None:
        # 새로고침·중복 요청 — **재생성 0건**(§8.3-4 · NT-08).
        return await _reply(db, session, replayed=True)

    user1 = await store.turn(db, branch.id, "user1")
    outcome = await ai2_pipeline.generate(
        participant_no=session.participant_no,
        user1_text=fernet.decrypt(user1.text) if user1 and user1.text else "",
    )
    generation = tables.Generation(
        branch_id=branch.id,
        attempt=outcome.attempt,
        output_text=fernet.encrypt(outcome.text),
        rule_violations=outcome.rule_violations,
        checker_result=outcome.checker_result,
        checker_skipped=outcome.checker_skipped,
        fallback_used=outcome.fallback_used,
        final=True,
    )
    db.add(generation)
    await db.flush()
    db.add(
        tables.Turn(
            branch_id=branch.id,
            role="ai2",
            text=fernet.encrypt(outcome.text),
            rendered_at=_now(),
            generation_id=generation.id,
        )
    )
    # b_state는 B4에 머문다 — 표시가 끝나고 참가자가 진행할 때 `POST /advance`가 B5로 옮긴다.
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P8 downstream action (§4.8 · B5)
# --------------------------------------------------------------------------- #


class DownstreamRequest(BaseModel):
    code: str


@router.post("/{branch_index}/downstream")
async def submit_downstream(
    branch_index: int, payload: DownstreamRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — B5 7선택 1회. enacted behavioral choice이고 실제 실행은 요구하지 않는다(§4.8)."""
    branch = await _resolve(db, session, branch_index)
    if not has_ai2(branch.user1_disposition):
        # NT-17 — downstream은 AI2가 표시된 branch만의 화면이다(§4.8).
        raise HTTPException(status.HTTP_409_CONFLICT, "이 branch에는 downstream 단계가 없습니다")
    if is_replay_b(BState(branch.b_state), BState.RATINGS):
        return await _reply(db, session, replayed=True)
    if BState(branch.b_state) is not BState.DOWNSTREAM:
        raise HTTPException(status.HTTP_409_CONFLICT, "downstream 단계가 아닙니다")
    if payload.code not in screen_copy.DOWNSTREAM_CODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택지에 없는 코드입니다")

    db.add(
        tables.DownstreamAction(
            branch_id=branch.id,
            code=payload.code,
            # §4.8 "표시 순서" — 화면에 제시된 7코드의 순서 그대로(선택 위치는 여기서 파생).
            display_order=list(screen_copy.DOWNSTREAM_CODES),
            selected_at=_now(),
        )
    )
    _require_b(branch, BState.RATINGS)
    branch.b_state = BState.RATINGS.value
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P9 평정 12문항 (§4.9 · §7.3 · B6)
# --------------------------------------------------------------------------- #


class RatingAnswer(BaseModel):
    position: int = Field(ge=1, le=rating_items.ITEM_COUNT)
    value: int = Field(ge=rating_items.SCALE_MIN, le=rating_items.SCALE_MAX)


class RatingsRequest(BaseModel):
    items: list[RatingAnswer]


@router.post("/{branch_index}/ratings")
async def submit_ratings(
    branch_index: int, payload: RatingsRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — B6 제출. 12문항 전부·2블록, **합산 없음**(§0.4·§7.3)."""
    branch = await _resolve(db, session, branch_index)
    if is_replay_b(BState(branch.b_state), BState.RESET_DONE):
        return await _reply(db, session, replayed=True)
    if BState(branch.b_state) is not BState.RATINGS:
        raise HTTPException(status.HTTP_409_CONFLICT, "평정 단계가 아닙니다")

    positions = sorted(answer.position for answer in payload.items)
    if positions != list(range(1, rating_items.ITEM_COUNT + 1)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{rating_items.ITEM_COUNT}문항 전부에 응답이 필요합니다",
        )

    # 화면에 내려간 순서를 그대로 재현해 위치 → 문항 ID를 되돌린다(§4.9 · NT-08).
    presented = {
        entry.position: entry
        for entry in rating_items.presentation_order(session.id, branch.branch_index)
    }
    values = {answer.position: answer.value for answer in payload.items}
    for position, entry in presented.items():
        db.add(
            tables.Rating(
                branch_id=branch.id,
                item_id=entry.item.item_id,
                value=values[position],
                block=entry.block,
                display_order=position,
            )
        )

    _require_b(branch, BState.RESET_DONE)
    branch.b_state = BState.RESET_DONE.value
    branch.completed_at = _now()
    await _close_branch(db, session, branch)
    return await _reply(db, session, replayed=False)


async def _close_branch(
    db: DbSession, session: tables.Session, branch: tables.Branch
) -> None:
    """§3.2 B7 — b<4면 다음 branch의 B0로, b=4면 SS05로.

    §3.4의 reset은 **새 조립**이지 이력 이어붙이기가 아니다. 다음 branch는 빈 B0로 열리고,
    이전 branch의 어떤 값도 넘어가지 않는다.
    """
    if branch.branch_index < BRANCH_COUNT:
        session.branch_index = branch.branch_index + 1
        await open_branch(db, session, session.branch_index)
        return
    assert_ss_transition(SsState(session.ss_state), SsState.CROSS_REVIEW)
    session.ss_state = SsState.CROSS_REVIEW.value
    session.branch_index = None
