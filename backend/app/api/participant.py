"""참가자 API — 세션 수준 (구현명세서 §8.2 · §3 · §4).

branch 수준 제출(§8.2의 `/branch/…`)은 `api/branch.py`에 있다. 여기는 접속·동의·사전설문·
checkpoint 확인·화면 전이·디브리핑, 그리고 beacon이다.

전 엔드포인트가 같은 세 겹을 지난다.

1. **세션 확인**(`deps.current_session`) — 쿠키 서명 → `sessions` 행.
2. **전이 검증**(`core.state_machine`) — 합법 전이만(NT-14). 위반은 409다.
3. **재제출 판정**(`core.idempotency`) — 이미 지난 단계면 200 + 저장 상태(NT-09).

2와 3의 순서가 중요하다. "이미 했다"를 먼저 보고 200으로 끊어야, 새로고침 후 중복 제출이
409로 튀지 않는다(§9.1 "중복 제출 → 무반응").
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api import store
from app.api.deps import CurrentSession, DbSession, require_active, set_session_cookie
from app.api.state_payload import build_state
from app.assets import presurvey, screen_copy
from app.core import access_code
from app.core.idempotency import is_replay_ss
from app.core.state_machine import (
    BState,
    IllegalTransition,
    SsState,
    assert_b_transition,
    assert_ss_transition,
)
from app.core.williams import condition as williams_condition
from app.models import tables
from app.security import fernet

router = APIRouter(prefix="/api", tags=["participant"])

#: §2.11 beacon 유형. 열린 쓰기 통로가 되지 않도록 목록을 고정한다.
EVENT_TYPES = frozenset(
    {"screen_enter", "screen_exit", "render_complete", "submit", "focus", "blur"}
)
#: 이벤트 payload는 **계량**이지 텍스트가 아니다(§4.6 keystroke·수정 이력 수집 금지).
EVENT_PAYLOAD_MAX_KEYS = 8
EVENT_PAYLOAD_MAX_LEN = 64


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(exc: IllegalTransition) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


async def _advance_ss(session: tables.Session, target: SsState) -> None:
    try:
        assert_ss_transition(SsState(session.ss_state), target)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    session.ss_state = target.value


async def open_branch(db: DbSession, session: tables.Session, branch_index: int) -> tables.Branch:
    """§3.2 B0(REENTRY)로 branch를 연다. 조건·자극은 아직 정하지 않는다 — B1 진입 시점이다."""
    branch = tables.Branch(
        session_id=session.id,
        branch_index=branch_index,
        b_state=BState.REENTRY.value,
    )
    db.add(branch)
    await db.flush()
    return branch


# --------------------------------------------------------------------------- #
# P0 접속 (§4.0 · §2.5)
# --------------------------------------------------------------------------- #


class JoinRequest(BaseModel):
    participant_no: str
    access_code: str
    #: §4.0 저장 항목. `sessions`에 열이 없으므로 events로 남긴다(§8.1 표 유지).
    viewport: dict[str, int] | None = None


@router.post("/join")
async def join(
    payload: JoinRequest, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    """§8.2 `POST /join` — 번호+코드 검증 → 세션 토큰 발급, 상태 반환(신규/복원)."""
    participant_no = payload.participant_no.strip().upper()
    now = time.monotonic()

    delay = access_code.retry_after(participant_no, now)
    if delay:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            screen_copy.JOIN_FAILED,
            headers={"Retry-After": str(delay)},
        )

    code_hash = access_code.hash_code(participant_no, payload.access_code)
    result = await db.execute(
        select(tables.Session).where(
            tables.Session.participant_no == participant_no,
            tables.Session.access_code_hash == code_hash,
        )
    )
    session = result.scalars().first()
    if session is None:
        access_code.record_failure(participant_no, now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, screen_copy.JOIN_FAILED)

    if access_code.is_expired(session.code_expires_at):
        # §9.1 — 연구자 재발급으로 수렴한다. 실패 카운터에는 넣지 않는다(대입 시도가 아니다).
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, screen_copy.CODE_EXPIRED)

    access_code.record_success(participant_no)
    restored = SsState(session.ss_state) is not SsState.CREATED

    if not restored:
        await _advance_ss(session, SsState.JOINED_CONSENT)
        session.joined_at = _now()

    await store.record_event(
        db,
        session.id,
        "screen_enter",
        payload={
            "screen": "P0",
            "restored": restored,
            # §4.0 저장: user_agent·viewport
            "user_agent": (request.headers.get("user-agent") or "")[:200],
            "viewport": payload.viewport,
        },
    )
    await db.flush()
    set_session_cookie(response, session.id)
    state = await build_state(db, session)
    return {"restored": restored, **state}


@router.get("/state")
async def get_state(session: CurrentSession, db: DbSession) -> dict[str, Any]:
    """§8.2 `GET /state` — 새로고침·재접속의 복구 경로(§3.5 · NT-08)."""
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P1 동의 (§4.1)
# --------------------------------------------------------------------------- #


class ConsentRequest(BaseModel):
    items: dict[str, bool]


@router.post("/consent")
async def submit_consent(
    payload: ConsentRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    require_active(session)
    if is_replay_ss(SsState(session.ss_state), SsState.PRESURVEY):
        return await build_state(db, session)

    required = {item.field for item in screen_copy.CONSENT_ITEMS}
    if set(payload.items) != required or not all(payload.items.values()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "동의 항목 전부에 체크가 필요합니다 (§4.1)"
        )

    stamped = _now().isoformat()
    session.consent_items = {field: {"agreed": True, "at": stamped} for field in payload.items}
    session.consent_version = screen_copy.CONSENT_VERSION
    await _advance_ss(session, SsState.PRESURVEY)
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P2 사전 설문 (§4.2)
# --------------------------------------------------------------------------- #


class PresurveyAnswer(BaseModel):
    position: int = Field(ge=1)
    value: Any


class PresurveyRequest(BaseModel):
    responses: list[PresurveyAnswer]


@router.post("/presurvey")
async def submit_presurvey(
    payload: PresurveyRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    require_active(session)
    if is_replay_ss(SsState(session.ss_state), SsState.CHECKPOINT_REVIEW):
        return await build_state(db, session)
    if SsState(session.ss_state) is not SsState.PRESURVEY:
        raise HTTPException(status.HTTP_409_CONFLICT, "사전 설문 단계가 아닙니다")

    asset = presurvey.load()
    expected = set(range(1, len(asset.items) + 1))
    positions = [answer.position for answer in payload.responses]
    if sorted(positions) != sorted(expected):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "전 문항에 응답이 필요합니다")

    for answer in payload.responses:
        try:
            asset.validate_response(answer.position, answer.value)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    for answer in payload.responses:
        db.add(
            tables.PresurveyResponse(
                session_id=session.id,
                # 위치 → 문항 ID 매핑은 서버만 안다(§4.2 · NT-05).
                item_id=asset.item_at(answer.position).item_id,
                value=answer.value,
                display_order=answer.position,
            )
        )
    await _advance_ss(session, SsState.CHECKPOINT_REVIEW)
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P3 checkpoint 확인 (§4.3)
# --------------------------------------------------------------------------- #


@router.post("/checkpoint/confirm")
async def confirm_checkpoint(session: CurrentSession, db: DbSession) -> dict[str, Any]:
    """확인만 한다 — **수정 기능 없음**(D-08). branch 1을 열고 SS04로 넘어간다."""
    require_active(session)
    if is_replay_ss(SsState(session.ss_state), SsState.BRANCH_BLOCK):
        return await build_state(db, session)
    if SsState(session.ss_state) is not SsState.CHECKPOINT_REVIEW:
        raise HTTPException(status.HTTP_409_CONFLICT, "checkpoint 단계가 아닙니다")

    await _advance_ss(session, SsState.BRANCH_BLOCK)
    session.branch_index = 1
    await open_branch(db, session, 1)
    # §4.3 저장: checkpoint_viewed_at — `sessions`에 열이 없으므로 events에 남긴다(§8.1 표 유지).
    await store.record_event(db, session.id, "submit", payload={"screen": "P3"})
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# 화면 전이 (§8.2 `POST /advance`)
# --------------------------------------------------------------------------- #


class AdvanceRequest(BaseModel):
    #: 클라이언트가 **지금 보고 있다고 믿는** 화면. 서버 상태와 다르면 409다(NT-14).
    from_screen: str


@router.post("/advance")
async def advance(
    payload: AdvanceRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """자체 제출물이 없는 전이 — P4(branch 시작)·P7(AI2 확인)·P10(인터뷰 종료).

    `from_screen`을 받는 이유는 §3.5다: 뒤로가기·중복 클릭으로 **다음 화면에서 다시 누른**
    요청이 조용히 한 단계 더 밀어 버리면 안 된다.
    """
    require_active(session)
    state = await build_state(db, session)
    if payload.from_screen != state["screen"]:
        # 이미 지나간 화면에서 온 중복 요청 — 현재 상태를 그대로 돌려준다(§9.1 중복 제출).
        return state

    screen = state["screen"]
    if screen == "P4":
        return await _start_branch(db, session)
    if screen == "P7":
        return await _confirm_ai2(db, session)
    if screen == "P10":
        await _advance_ss(session, SsState.DEBRIEF)
        await db.flush()
        return await build_state(db, session)
    raise HTTPException(status.HTTP_409_CONFLICT, f"{screen}에서는 진행 버튼이 없습니다")


async def _start_branch(db: DbSession, session: tables.Session) -> dict[str, Any]:
    """B0 → B1. **조건·자극이 확정되는 유일한 지점**이다(§3.2 · NT-07)."""
    branch = await store.branch_by_index(db, session.id, session.branch_index or 0)
    if branch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "branch가 없습니다")
    try:
        assert_b_transition(BState(branch.b_state), BState.AI1_SHOWN)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc

    from app.assets import dossier_loader

    dossier = dossier_loader.load(session.participant_no)
    if branch.condition is None:
        # 최초 진입 — 결정론 매핑(§3.3)으로 조건을 정하고 자극 hash를 남긴다. 이후 불변.
        branch.condition = williams_condition(session.participant_no, branch.branch_index)
        branch.stimulus_hash = dossier.stimulus_hash(branch.condition)
        branch.started_at = _now()
        db.add(
            tables.Turn(
                branch_id=branch.id,
                role="ai1",
                text=fernet.encrypt(dossier.stimulus(branch.condition)),
                rendered_at=_now(),
            )
        )
    branch.b_state = BState.AI1_SHOWN.value
    await db.flush()
    return await build_state(db, session)


async def _confirm_ai2(db: DbSession, session: tables.Session) -> dict[str, Any]:
    """B4 → B5. AI2(또는 fallback)가 **표시된 뒤**에만 넘어간다(§3.2)."""
    branch = await store.branch_by_index(db, session.id, session.branch_index or 0)
    if branch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "branch가 없습니다")
    if await store.final_generation(db, branch.id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "표시할 AI2 산출물이 아직 없습니다")
    try:
        assert_b_transition(BState(branch.b_state), BState.DOWNSTREAM)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    branch.b_state = BState.DOWNSTREAM.value
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P11 디브리핑 (§4.11)
# --------------------------------------------------------------------------- #


@router.post("/debrief/confirm")
async def confirm_debrief(session: CurrentSession, db: DbSession) -> dict[str, Any]:
    if is_replay_ss(SsState(session.ss_state), SsState.DONE):
        return await build_state(db, session)
    require_active(session)
    await _advance_ss(session, SsState.DONE)
    session.status = "done"
    # §4.11 저장: debrief_confirmed_at — `sessions`에 열이 없으므로 events에 남긴다.
    await store.record_event(db, session.id, "submit", payload={"screen": "P11"})
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# beacon (§2.11 · §7.5 · NT-29)
# --------------------------------------------------------------------------- #


class EventRequest(BaseModel):
    type: str
    client_ts: datetime | None = None
    branch_index: int | None = None
    payload: dict[str, Any] | None = None


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def record_beacon(
    payload: EventRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """화면 진입·렌더 완료·제출·focus/blur (§2.11).

    파생 지표(체류·latency)는 **계산하지 않는다** — 이벤트 쌍만 남기고 분석 시점에 계산한다
    (§7.5 · NT-29). `render_complete`만 상태에 영향을 준다(B1 → B2, §3.2).
    """
    if payload.type not in EVENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"알 수 없는 이벤트: {payload.type}")
    body = payload.payload or {}
    if len(body) > EVENT_PAYLOAD_MAX_KEYS or any(
        isinstance(value, str) and len(value) > EVENT_PAYLOAD_MAX_LEN for value in body.values()
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이벤트 payload가 너무 큽니다")

    branch: tables.Branch | None = None
    if payload.branch_index is not None:
        branch = await store.branch_by_index(db, session.id, payload.branch_index)

    if (
        payload.type == "render_complete"
        and branch is not None
        and BState(branch.b_state) is BState.AI1_SHOWN
    ):
        # 렌더 beacon이 B1 → B2를 연다. beacon이 유실돼도 User1 제출이 같은 전이를 수행하므로
        # 시간 지표가 연구 상태의 게이트가 되지 않는다(§2.11 불변 원칙).
        branch.b_state = BState.USER1.value

    await store.record_event(
        db,
        session.id,
        payload.type,
        branch_id=branch.id if branch is not None else None,
        payload=body or None,
        client_ts=payload.client_ts,
    )
    await db.flush()
    return {"recorded": True}
