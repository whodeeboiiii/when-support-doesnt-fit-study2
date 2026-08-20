"""연구자 API — R1 세션 관리와 개입 (구현명세서 §8.2 · §2.5 · §2.7 · §4.12 · NT-12·NT-26·NT-27).

여기는 **연구자가 세션에 손을 대는 자리**다: 생성·코드 발급·flag·abort·dropout·비용 조회.
읽기 전용 뷰(R2 모니터·R3 review·R4 dossier)는 `api/admin_views.py`에 있다.

네 불변식이 이 파일에 걸린다.

- **참가자당 완료 세션 1개**(NT-12·§2.5). 진행 중이거나 완료된 세션이 있으면 새 세션을 만들지
  않는다. 다시 시작해야 하면 기존 세션을 중단 처리(SS90·SS91)한 뒤다. P00은 QA 전용이라
  무제한이다(§2.5).
- **재발급은 같은 세션에 바인딩**(NT-27). 코드가 만료돼도 새 세션을 만들지 않는다 —
  §3.5의 "저장 지점 복원"이 세션 id에 걸려 있기 때문이다.
- **flag는 non-blocking**(D-07·NT-26). 상태를 바꾸지 않고 `events`에만 남는다. 상태를 바꾸는
  연구자 개입은 abort(SS90)·dropout(SS91) 둘뿐이다.
- **전 행위는 `audit_logs`에 남는다**(§2.7). 조회도 예외가 아니다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api import store
from app.api.deps import AdminActor, DbSession
from app.assets import dossier_loader
from app.assets.files import PARTICIPANT_NUMBERS, QA_PARTICIPANT_NO
from app.core import access_code, freeze
from app.core.state_machine import (
    IllegalTransition,
    SsState,
    assert_ss_transition,
)
from app.core.williams import sequence, sequence_index
from app.models import tables
from app.notify.discord import NotifyEvent, notify
from app.security import fernet
from app.security.audit import AuditAction, record

router = APIRouter(prefix="/admin", tags=["researcher"])

#: 새 세션을 막는 기존 세션 상태 (NT-12).
BLOCKING_STATUSES = ("active", "done")

#: §8.1 `events.payload` — flag 사유는 🔒다(§2.9). 컬럼을 늘리지 않고 payload 안에 넣는다.
FLAG_EVENT = "researcher_flag"
ABORT_EVENT = "researcher_abort"
DROPOUT_EVENT = "researcher_dropout"
REASON_FIELD = "reason_encrypted"


def _now() -> datetime:
    return datetime.now(UTC)


async def get_session_or_404(db: DbSession, session_id: uuid.UUID) -> tables.Session:
    session = await db.get(tables.Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "세션을 찾을 수 없습니다")
    return session


class CreateSessionRequest(BaseModel):
    participant_no: str


async def _ensure_participant(db: DbSession, participant_no: str) -> tables.Participant:
    """§8.1 `participants` — sequence_index는 **생성 시 결정론 산출·저장**(§3.3)."""
    participant = await db.get(tables.Participant, participant_no)
    dossier = dossier_loader.load(participant_no)
    if participant is None:
        participant = tables.Participant(
            participant_no=participant_no,
            sequence_index=sequence_index(participant_no),
            dossier_version=dossier.version,
            dossier_hash=dossier.content_hash,
            is_test=participant_no == QA_PARTICIPANT_NO,
        )
        db.add(participant)
        await db.flush()
        return participant
    # 자산이 바뀌었다면 그 사실을 남긴다 — 배정(sequence_index)은 번호에서 나오므로 불변이다.
    participant.dossier_version = dossier.version
    participant.dossier_hash = dossier.content_hash
    return participant


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """세션 생성 + 접속 코드 1개 발급. **평문 코드는 이 응답에만 존재한다**(§2.5)."""
    participant_no = payload.participant_no.strip().upper()
    if participant_no not in PARTICIPANT_NUMBERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"알 수 없는 참가자 번호: {participant_no}")

    if participant_no != QA_PARTICIPANT_NO:
        existing = await store.sessions_of_participant(db, participant_no, BLOCKING_STATUSES)
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{participant_no}에 이미 세션이 있습니다 (참가자당 완료 세션 1개 — NT-12)",
            )

    await _ensure_participant(db, participant_no)
    code = access_code.generate_code()
    session = tables.Session(
        participant_no=participant_no,
        access_code_hash=access_code.hash_code(participant_no, code),
        code_expires_at=access_code.expires_at(),
        ss_state=SsState.CREATED.value,
        status="active",
    )
    db.add(session)
    await db.flush()
    await record(db, actor=actor, action=AuditAction.CODE_ISSUE, target=f"session:{session.id}")
    return {
        "session_id": str(session.id),
        "participant_no": participant_no,
        "sequence_index": sequence_index(participant_no),
        "access_code": code,
        "code_expires_at": session.code_expires_at.isoformat() if session.code_expires_at else None,
    }


@router.post("/sessions/{session_id}/code")
async def reissue_code(session_id: uuid.UUID, actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """§9.1 접속 코드 만료 → 재발급. **동일 세션에 바인딩**한다(NT-27)."""
    session = await get_session_or_404(db, session_id)

    code = access_code.generate_code()
    session.access_code_hash = access_code.hash_code(session.participant_no, code)
    session.code_expires_at = access_code.expires_at()
    await db.flush()
    await record(db, actor=actor, action=AuditAction.CODE_ISSUE, target=f"session:{session.id}")
    return {
        "session_id": str(session.id),
        "participant_no": session.participant_no,
        "access_code": code,
        "code_expires_at": session.code_expires_at.isoformat() if session.code_expires_at else None,
    }


# --------------------------------------------------------------------------- #
# R1 세션 관리 (§4.12) — 참가자 목록·sequence·dossier lock·세션 상태 일람
# --------------------------------------------------------------------------- #


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _session_row(session: tables.Session) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "ss_state": session.ss_state,
        "branch_index": session.branch_index,
        "status": session.status,
        "created_at": _iso(session.created_at),
        "joined_at": _iso(session.joined_at),
        "code_expires_at": _iso(session.code_expires_at),
        "code_expired": access_code.is_expired(session.code_expires_at),
    }


@router.get("/participants")
async def list_participants(actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """R1 화면의 표 하나 (§4.12).

    sequence는 **저장값이 아니라 번호에서 산출**한 값을 보여 준다(§3.3) — 세션이 아직 없는
    참가자도 배정을 미리 확인할 수 있어야 세션 전 체크리스트(부록 D.2)가 성립한다.
    dossier lock 상태(`locked`·`dummy`)는 D.2의 첫 줄이 요구하는 값이다.
    """
    rows: list[dict[str, Any]] = []
    for participant_no in PARTICIPANT_NUMBERS:
        dossier = dossier_loader.load(participant_no)
        sessions = await store.sessions_of_participant(db, participant_no)
        rows.append(
            {
                "participant_no": participant_no,
                "sequence_index": sequence_index(participant_no),
                # 조건 라벨은 **연구자 화면에만** 나온다(§4.10 — 참가자에게는 비공개).
                "sequence": list(sequence(participant_no)),
                "dossier": {
                    "version": dossier.version,
                    "locked": dossier.is_locked,
                    "locked_at": dossier.locked_at,
                    "hash": dossier.content_hash,
                    "dummy": dossier.is_dummy,
                },
                "sessions": [_session_row(row) for row in sessions],
            }
        )
    await record(db, actor=actor, action=AuditAction.VIEW, target="console:R1")
    frozen = await freeze.current(db)
    return {
        "participants": rows,
        # §11.3 모집 게이트 — **표시만** 한다. 시작 여부는 연구자가 정한다(자동 차단 없음).
        "launch_gate": [
            {"tag": blocker.tag, "detail": blocker.detail} for blocker in freeze.blockers()
        ],
        # §10.5 설계 동결 — soft launch 종료 시 `scripts/freeze_study_version.py`로 1회 기입.
        "study_version_frozen_at": _iso(frozen.frozen_at) if frozen else None,
    }


@router.get("/costs")
async def costs(actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """§2.8 — `llm_calls` usage 합산. 대시보드도 상한도 두지 않는다(12세션 규모)."""
    result = await db.execute(
        select(
            tables.LlmCall.role,
            func.count(tables.LlmCall.id),
            func.sum(tables.LlmCall.prompt_tokens),
            func.sum(tables.LlmCall.completion_tokens),
            func.sum(tables.LlmCall.cost),
        ).group_by(tables.LlmCall.role)
    )
    by_role = [
        {
            "role": role,
            "calls": int(calls or 0),
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
            "cost": float(cost or 0.0),
        }
        for role, calls, prompt, completion, cost in result.all()
    ]
    await record(db, actor=actor, action=AuditAction.VIEW, target="console:costs")
    return {
        "by_role": by_role,
        "total_cost": sum(entry["cost"] for entry in by_role),
        "total_calls": sum(entry["calls"] for entry in by_role),
    }


# --------------------------------------------------------------------------- #
# R2 개입 — flag(non-blocking) · abort(SS90) · dropout(SS91)  §4.12 · §9.1 · NT-26
# --------------------------------------------------------------------------- #


class ReasonRequest(BaseModel):
    """flag·abort 공통. 사유는 **필수**다(§4.12 — 중단 버튼은 사유 필수)."""

    reason: str = Field(min_length=1)


@router.post("/sessions/{session_id}/flag")
async def flag_session(
    session_id: uuid.UUID, payload: ReasonRequest, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """§4.12 flag — **기록 전용**이다(D-07).

    상태를 바꾸지 않는다는 것이 이 엔드포인트의 전부다(NT-26). checkpoint 사실 오류 구두
    언급도 여기로 들어온다 — 자산은 고치지 않는다(D-08 · 부록 D.3).
    """
    session = await get_session_or_404(db, session_id)
    before = session.ss_state
    await store.record_event(
        db,
        session.id,
        FLAG_EVENT,
        branch_id=(
            branch.id
            if (branch := await store.branch_by_index(db, session.id, session.branch_index or 0))
            else None
        ),
        payload={
            # 🔒 사유는 암호문으로 넣는다(§2.9 · §8.1 컬럼 목록 유지).
            REASON_FIELD: fernet.encrypt(payload.reason).decode("ascii"),
            "ss_state": before,
            "branch_index": session.branch_index,
        },
    )
    await record(db, actor=actor, action=AuditAction.FLAG, target=f"session:{session.id}")
    await db.flush()
    assert session.ss_state == before, "flag가 상태를 바꿨다 — non-blocking 위반(D-07)"
    return {"flagged": True, "ss_state": session.ss_state, "status": session.status}


async def _interrupt(
    db: DbSession,
    session: tables.Session,
    *,
    target: SsState,
    event_type: str,
    reason: str | None,
) -> dict[str, Any]:
    """§3.1 중단 전이 공통 — SS90(연구자 abort)·SS91(dropout)."""
    try:
        assert_ss_transition(SsState(session.ss_state), target)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    before = session.ss_state
    session.ss_state = target.value
    session.status = "abort" if target is SsState.RESEARCHER_ABORT else "dropout"
    session.branch_index = None
    if reason is not None:
        session.abort_reason = fernet.encrypt(reason)  # 🔒 §8.1 `sessions.abort_reason`
    await store.record_event(
        db, session.id, event_type, payload={"from_ss_state": before, "at": _iso(_now())}
    )
    await db.flush()
    return {"ss_state": session.ss_state, "status": session.status}


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: uuid.UUID, payload: ReasonRequest, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """§9.1 연구자 abort — SS90 + 사유 저장 + notify. 참가자 화면은 중단 안내로 수렴한다."""
    session = await get_session_or_404(db, session_id)
    result = await _interrupt(
        db, session, target=SsState.RESEARCHER_ABORT, event_type=ABORT_EVENT, reason=payload.reason
    )
    await record(db, actor=actor, action=AuditAction.ABORT, target=f"session:{session.id}")
    # §2.8 트리거 4 — 참가자 원문은 싣지 않는다(사유는 DB에만).
    await notify(
        NotifyEvent.RESEARCHER_ABORT,
        "연구자가 세션을 중단했다",
        participant_no=session.participant_no,
        session_id=str(session.id),
    )
    return result


@router.post("/sessions/{session_id}/dropout")
async def dropout_session(
    session_id: uuid.UUID, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """§9.1 — 복구 불능(브라우저·네트워크 이탈) 시 연구자가 SS91로 처리한다.

    abort와 달리 **알림을 보내지 않는다**(§2.8 표에 없다). 연구자가 이미 아는 상황이다.
    """
    session = await get_session_or_404(db, session_id)
    result = await _interrupt(
        db, session, target=SsState.DROPOUT, event_type=DROPOUT_EVENT, reason=None
    )
    await record(db, actor=actor, action=AuditAction.ABORT, target=f"session:{session.id}")
    return result
