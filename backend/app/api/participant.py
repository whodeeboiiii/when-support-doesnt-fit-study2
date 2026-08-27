"""참가자 API — 세션 수준 (구현명세서 §8.2 · §3 · §4).

focal 수준 제출(§8.2의 `/focal/…`)은 `api/focal.py`, 대안 노출·pairwise는 `api/exposure.py`에
있다. 여기는 접속·동의·사전설문·checkpoint 수정·확인·화면 전이·focal 평정·디브리핑, 그리고
beacon이다.

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
from app.api.state_payload import build_state, effective_checkpoint
from app.assets import dossier_loader, presurvey, rating_items, screen_copy
from app.core import access_code, assignment
from app.core.idempotency import is_replay_ss
from app.core.state_machine import (
    ALT_POSITIONS,
    FState,
    IllegalTransition,
    SsState,
    assert_ss_transition,
)
from app.models import tables
from app.notify.discord import NotifyEvent, notify
from app.security import fernet

router = APIRouter(prefix="/api", tags=["participant"])

#: §2.11 beacon 유형. 열린 쓰기 통로가 되지 않도록 목록을 고정한다.
EVENT_TYPES = frozenset(
    {"screen_enter", "screen_exit", "render_complete", "submit", "focus", "blur"}
)
#: 이벤트 payload는 **계량**이지 텍스트가 아니다(§4.5 keystroke·수정 이력 수집 금지).
EVENT_PAYLOAD_MAX_KEYS = 8
EVENT_PAYLOAD_MAX_LEN = 64


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(exc: IllegalTransition) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


async def advance_ss(session: tables.Session, target: SsState) -> None:
    try:
        assert_ss_transition(SsState(session.ss_state), target)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc
    session.ss_state = target.value


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
        await advance_ss(session, SsState.CONSENT)
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
    await advance_ss(session, SsState.PRESURVEY)
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P1S 사전 설문 (v1.0.1 §4.2 · §7.1 — D-44로 복원)
# --------------------------------------------------------------------------- #


class PresurveyAnswer(BaseModel):
    #: **위치**다. 문항 ID는 화면에 내려가지 않으므로 돌아올 수도 없다(NT-05).
    position: int = Field(ge=1)
    value: Any


class PresurveyRequest(BaseModel):
    responses: list[PresurveyAnswer]


@router.post("/presurvey")
async def submit_presurvey(
    payload: PresurveyRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — SS01S→SS02. **전 문항 필수**, 값 검증은 자산이 한다.

    응답은 checkpoint를 보기 **전에** 끝난다. 사전설문이 여기 있는 이유가 그것이다 —
    사건을 다시 읽은 뒤에 평소 사용 습관을 물으면 그 답이 사건에 물든다.

    저장은 (item_id, value, display_order)다. 위치 → 문항 ID 환원은 서버에서만 일어난다.
    """
    require_active(session)
    if is_replay_ss(SsState(session.ss_state), SsState.CHECKPOINT):
        return await build_state(db, session)
    if SsState(session.ss_state) is not SsState.PRESURVEY:
        raise HTTPException(status.HTTP_409_CONFLICT, "사전 설문 단계가 아닙니다")

    asset = presurvey.load()
    positions = sorted(answer.position for answer in payload.responses)
    if positions != list(range(1, asset.item_count + 1)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, screen_copy.PRESURVEY_INCOMPLETE)

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
    await advance_ss(session, SsState.CHECKPOINT)
    await store.record_event(db, session.id, "submit", payload={"screen": "P1S"})
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P2 checkpoint 확인·수정 (§4.2 · §3.4 · D-25)
# --------------------------------------------------------------------------- #


class CheckpointEditRequest(BaseModel):
    segment: str
    text: str


@router.post("/checkpoint/edit")
async def edit_checkpoint(
    payload: CheckpointEditRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — SS02에서만. **누적 저장**(§3.4), 확인 후에는 409(NT-35).

    `original`에는 **그 수정 시점의 직전 값**을 넣는다. dossier 원문이 아니라 직전 값인
    이유는 한 segment를 여러 번 고칠 수 있기 때문이다 — 각 행이 "무엇을 무엇으로 바꿨는가"의
    한 걸음이어야 R2 diff와 사후 코딩(§7.7)이 과정을 읽을 수 있다.
    """
    require_active(session)
    if SsState(session.ss_state) is not SsState.CHECKPOINT:
        # 확인 후 수정 불가 — §4.2가 명시한 409다.
        raise HTTPException(status.HTTP_409_CONFLICT, screen_copy.CHECKPOINT_EDIT_CLOSED)

    segment = payload.segment.strip()
    if segment not in dossier_loader.EDITABLE_SEGMENTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"수정할 수 없는 항목입니다: {segment} (§4.2)"
        )
    text = payload.text.strip()
    if not text:
        # §4.2 — 빈 문자열 저장은 거부(400).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, screen_copy.CHECKPOINT_EDIT_EMPTY)

    effective = await effective_checkpoint(db, session)
    previous = (
        "\n".join(effective.prior_evidence)
        if segment == "prior_evidence"
        else effective.as_dict()[segment]
    )
    if previous == text:
        # 같은 값 재저장은 수정이 아니다 — 행을 늘리지 않는다(§3.5 중복 제출).
        return await build_state(db, session)

    db.add(
        tables.CheckpointEdit(
            session_id=session.id,
            segment=segment,
            original=fernet.encrypt(previous),  # 🔒
            edited=fernet.encrypt(text),  # 🔒
            edited_at=_now(),
        )
    )
    await db.flush()

    if segment in dossier_loader.ALERT_SEGMENTS:
        # §2.8 신설 트리거 + §3.4 — 자극의 전제가 흔들릴 수 있다. 연구자가 Zoom에서 즉시
        # 구두 확인하고 계속/abort를 판단한다(부록 D.3). **시스템은 막지 않는다**.
        await notify(
            NotifyEvent.CHECKPOINT_CUE_EDITED,
            "checkpoint 자극 전제 segment가 수정됐다 — 구두 확인 필요",
            participant_no=session.participant_no,
            session_id=str(session.id),
            segment=segment,
        )
    return await build_state(db, session)


@router.post("/checkpoint/confirm")
async def confirm_checkpoint(session: CurrentSession, db: DbSession) -> dict[str, Any]:
    """§8.2 — SS02→SS03. 확인 시점에 수정이 종료된다(§3.4)."""
    require_active(session)
    if is_replay_ss(SsState(session.ss_state), SsState.REENTRY):
        return await build_state(db, session)
    if SsState(session.ss_state) is not SsState.CHECKPOINT:
        raise HTTPException(status.HTTP_409_CONFLICT, "checkpoint 단계가 아닙니다")

    await advance_ss(session, SsState.REENTRY)
    # §4.2 저장: checkpoint_viewed_at — `sessions`에 열이 없으므로 events에 남긴다.
    await store.record_event(db, session.id, "submit", payload={"screen": "P2"})
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# 화면 전이 (§8.2 `POST /advance`)
# --------------------------------------------------------------------------- #


class AdvanceRequest(BaseModel):
    #: 클라이언트가 **지금 보고 있다고 믿는** 화면. 서버 상태와 다르면 그대로 현재 상태를 준다.
    from_screen: str


@router.post("/advance")
async def advance(
    payload: AdvanceRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """자체 제출물이 없는 전이 — P3·P6·P7·P9·P11 (§8.2).

    `from_screen`을 받는 이유는 §3.5다: 뒤로가기·중복 클릭으로 **다음 화면에서 다시 누른**
    요청이 조용히 한 단계 더 밀어 버리면 안 된다.
    """
    require_active(session)
    state = await build_state(db, session)
    if payload.from_screen != state["screen"]:
        # 이미 지나간 화면에서 온 중복 요청 — 현재 상태를 그대로 돌려준다(§9.1 중복 제출).
        return state

    screen = state["screen"]
    if screen == "P3":
        return await _start_focal(db, session)
    if screen in {"P6", "P7"}:
        from app.api import focal

        return await focal.advance_focal(db, session, screen)
    if screen == "P9":
        from app.api import exposure

        return await exposure.advance_alt(db, session)
    if screen == "P11":
        await advance_ss(session, SsState.DEBRIEF)
        await db.flush()
        return await build_state(db, session)
    raise HTTPException(status.HTTP_409_CONFLICT, f"{screen}에서는 진행 버튼이 없습니다")


async def _start_focal(db: DbSession, session: tables.Session) -> dict[str, Any]:
    """SS03 → SS04·F0. **조건·자극이 확정되는 유일한 지점**이다(§3.2 · NT-07).

    조건은 **계산하지 않는다** — `participants`에 복사된 배정표 값을 읽는다(D-30). 그 복사는
    세션 생성 시점(`api/admin.py`)에 이미 끝나 있다.
    """
    await advance_ss(session, SsState.FOCAL)

    run = await store.focal_run(db, session.id)
    if run is None:
        participant = await db.get(tables.Participant, session.participant_no)
        if participant is None or not participant.focal_condition:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{session.participant_no}의 배정이 없습니다 (§5.2 배정표 확인)",
            )
        dossier = dossier_loader.load(session.participant_no)
        condition = participant.focal_condition
        edits = await store.effective_edits(db, session.id)
        run = tables.FocalRun(
            session_id=session.id,
            condition=condition,
            # AI1은 checkpoint 수정과 무관하다 — 조립에 수정본이 들어가지 않는다(§3.4·NT-34).
            stimulus_hash=dossier.stimulus_hash(condition),
            started_at=_now(),
            checkpoint_edited=bool(edits),
            edited_segments=sorted(edits),
        )
        db.add(run)
        await db.flush()
        db.add(
            tables.Turn(
                focal_run_id=run.id,
                role="ai1",
                # 화면·AI2 payload와 **같은** 문자열을 남긴다 — 기록이 참가자가 본 것과
                # 어긋나면 export·콘솔이 다른 대화를 보게 된다(D-40). `stimulus_hash`는
                # 위에서 locked 자산의 조립(`assemble`)으로 남는다 — 자산 대조는 그쪽이다.
                text=fernet.encrypt(dossier.presented(condition)),
                rendered_at=_now(),
            )
        )
    session.f_state = FState.AI1_PENDING.value
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# P8 focal measures + manipulation check (§4.8 · §7.1 · §7.2)
# --------------------------------------------------------------------------- #


class RatingAnswer(BaseModel):
    position: int = Field(ge=1)
    value: int


class RatingsRequest(BaseModel):
    items: list[RatingAnswer]


@router.post("/ratings")
async def submit_ratings(
    payload: RatingsRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — SS05→SS06. focal 5 construct(7문항) + MC 2, **전 문항 필수·합산 없음**(NT-37)."""
    require_active(session)
    if is_replay_ss(SsState(session.ss_state), SsState.ALT_EXPOSURE):
        return await build_state(db, session)
    if SsState(session.ss_state) is not SsState.FOCAL_MEASURES:
        raise HTTPException(status.HTTP_409_CONFLICT, "평정 단계가 아닙니다")

    asset = rating_items.load()
    positions = sorted(answer.position for answer in payload.items)
    if positions != list(range(1, asset.item_count + 1)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{asset.item_count}문항 전부에 응답이 필요합니다"
        )
    for answer in payload.items:
        if not asset.is_valid_value(answer.value):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"응답은 {asset.scale_min}–{asset.scale_max} 사이여야 합니다",
            )

    # 화면에 내려간 순서를 그대로 재현해 위치 → 문항 ID를 되돌린다(§4.8 · NT-08).
    presented = {entry.position: entry for entry in rating_items.presentation_order(session.id)}
    values = {answer.position: answer.value for answer in payload.items}
    for position, entry in presented.items():
        db.add(
            tables.Rating(
                session_id=session.id,
                scope=entry.scope,
                construct=entry.item.construct,
                item_id=entry.item.item_id,
                value=values[position],
                display_order=position,
            )
        )

    await advance_ss(session, SsState.ALT_EXPOSURE)
    session.alt_index = 1
    await _open_alt_exposures(db, session)
    await db.flush()
    return await build_state(db, session)


async def _open_alt_exposures(db: DbSession, session: tables.Session) -> None:
    """§3.3 — 세 대안의 노출 행을 배정표 순서대로 만든다.

    **여기가 focal 측정 완료 직후**다(NT-31). 이 시점 전에는 `alt_exposures` 행이 없고,
    따라서 화면 조립기가 대안 자극을 만들 자료 자체가 없다.

    행을 미리 셋 다 만드는 이유는 §3.3의 "최초 진입 시 생성 후 불변"이 position별로 성립해야
    하기 때문이다. 노출 시각(`rendered_at`)은 실제 표시 때 채워진다.
    """
    participant = await db.get(tables.Participant, session.participant_no)
    dossier = dossier_loader.load(session.participant_no)
    alt_order = list(participant.alt_order or []) if participant else []
    if len(alt_order) != ALT_POSITIONS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{session.participant_no}의 alt_order가 {ALT_POSITIONS}개가 아닙니다 (§5.2)",
        )
    for position, condition in enumerate(alt_order, start=1):
        if await store.alt_exposure(db, session.id, position) is not None:
            continue
        db.add(
            tables.AltExposure(
                session_id=session.id,
                position=position,
                condition=condition,
                stimulus_hash=dossier.stimulus_hash(condition),
                rendered_at=_now(),
            )
        )
    await db.flush()


# --------------------------------------------------------------------------- #
# P12 디브리핑 (§4.12)
# --------------------------------------------------------------------------- #


@router.post("/debrief/confirm")
async def confirm_debrief(session: CurrentSession, db: DbSession) -> dict[str, Any]:
    if is_replay_ss(SsState(session.ss_state), SsState.DONE):
        return await build_state(db, session)
    require_active(session)
    await advance_ss(session, SsState.DONE)
    session.status = "done"
    # §4.12 저장: debrief_confirmed_at — `sessions`에 열이 없으므로 events에 남긴다.
    await store.record_event(db, session.id, "submit", payload={"screen": "P12"})
    await db.flush()
    return await build_state(db, session)


# --------------------------------------------------------------------------- #
# beacon (§2.11 · NT-29)
# --------------------------------------------------------------------------- #


class EventRequest(BaseModel):
    type: str
    client_ts: datetime | None = None
    payload: dict[str, Any] | None = None


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def record_beacon(
    payload: EventRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """화면 진입·렌더 완료·제출·focus/blur (§2.11).

    파생 지표(체류·latency)는 **계산하지 않는다** — 이벤트 쌍만 남기고 분석 시점에 옵션으로
    계산한다(§2.11 — `response_latency`는 초안에서 삭제됐다). `render_complete`만 상태에
    영향을 준다(F0 → F1, §3.2).
    """
    if payload.type not in EVENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"알 수 없는 이벤트: {payload.type}")
    body = payload.payload or {}
    if len(body) > EVENT_PAYLOAD_MAX_KEYS or any(
        isinstance(value, str) and len(value) > EVENT_PAYLOAD_MAX_LEN for value in body.values()
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이벤트 payload가 너무 큽니다")

    if (
        payload.type == "render_complete"
        and session.f_state == FState.AI1_PENDING.value
        and SsState(session.ss_state) is SsState.FOCAL
    ):
        # 렌더 beacon이 F0 → F1을 연다. beacon이 유실돼도 User1 제출이 같은 전이를 수행하므로
        # 시간 지표가 연구 상태의 게이트가 되지 않는다(§2.11 불변 원칙).
        session.f_state = FState.USER1.value

    await store.record_event(
        db, session.id, payload.type, payload=body or None, client_ts=payload.client_ts
    )
    await db.flush()
    return {"recorded": True}
