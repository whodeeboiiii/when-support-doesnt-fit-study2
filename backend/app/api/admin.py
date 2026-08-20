"""연구자 API — R1 세션 관리와 개입 (구현명세서 §8.2 · §2.5 · §2.7 · §4.13 · NT-12·26·27).

여기는 **연구자가 세션에 손을 대는 자리**다: 생성·코드 발급·flag·abort·dropout·비용·배정표
조회. 읽기 전용 뷰(R2 모니터·R3 contrastive·R4 dossier)는 `api/admin_views.py`에 있다.

다섯 불변식이 이 파일에 걸린다.

- **배정은 읽기만**(D-30). 세션 생성 시 배정표 행을 `participants`에 **복사**하고 그 뒤로는
  파일이 바뀌어도 세션의 배정이 따라 바뀌지 않는다(NT-07). 조건을 계산하는 코드는 없다.
- **배정표에 없는 참가자는 세션을 만들 수 없다**(§5.1 — 배정표의 행이 곧 참가자 목록).
  dossier가 없어도 마찬가지다(§9.1 마지막 행 — 409 + 사유 표시).
- **참가자당 완료 세션 1개**(NT-12·§2.5). P00은 QA 전용이라 무제한이다.
- **재발급은 같은 세션에 바인딩**(NT-27). 코드가 만료돼도 새 세션을 만들지 않는다 —
  §3.5의 "저장 지점 복원"이 세션 id에 걸려 있기 때문이다.
- **flag는 non-blocking**(D-07·NT-26). 상태를 바꾸지 않고 `events`에만 남는다. 상태를 바꾸는
  연구자 개입은 abort(SS90)·dropout(SS91) 둘뿐이다.

**전 행위는 `audit_logs`에 남는다**(§2.7). 조회도 예외가 아니다.
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
from app.assets.files import DossierNotFound, QA_PARTICIPANT_NO, is_participant_no
from app.core import access_code, assignment, freeze
from app.core.state_machine import IllegalTransition, SsState, assert_ss_transition
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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def get_session_or_404(db: DbSession, session_id: uuid.UUID) -> tables.Session:
    session = await db.get(tables.Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "세션을 찾을 수 없습니다")
    return session


class CreateSessionRequest(BaseModel):
    participant_no: str


async def _ensure_participant(db: DbSession, participant_no: str) -> tables.Participant:
    """§8.1 `participants` — **배정표 행을 복사**한다(D-30 · NT-07).

    P00은 배정표에 없다(QA 합성). 그때는 배정을 비워 두는 대신 **C1 focal + 결정론 순서**를
    쓴다 — 리허설이 배정표 없이도 전 경로를 돌 수 있어야 하기 때문이다(§10.2). 실참가자
    경로에는 이 분기가 닿지 않는다.
    """
    dossier = dossier_loader.load(participant_no)
    table = assignment.load()

    if table.has(participant_no):
        row = table.row(participant_no)
        focal, alt_order = row.focal_condition, list(row.alt_order)
        pair_order = list(row.pair_order)
        pair_sides = {key: list(value) for key, value in row.pair_sides.items()}
        a_level, locus = row.a_level, row.mismatch_locus
        version = table.version
    elif participant_no == QA_PARTICIPANT_NO:
        focal = "C1"
        alt_order = ["C2", "C3", "C4"]
        pair_order = list(assignment.CONTRASTS)
        pair_sides = {
            contrast: sorted(assignment.CONTRAST_PAIR[contrast])
            for contrast in assignment.CONTRASTS
        }
        a_level, locus = dossier.evidence_code.a_level, dossier.evidence_code.mismatch_locus
        version = "qa_fixed"
    else:
        # §5.1 — 배정표의 행이 곧 참가자 목록이다. 없는 번호로 세션을 열지 않는다.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{participant_no}는 배정표에 없습니다 ({table.source_path.name} — §5.1)",
        )

    participant = await db.get(tables.Participant, participant_no)
    if participant is None:
        participant = tables.Participant(
            participant_no=participant_no,
            focal_condition=focal,
            alt_order=alt_order,
            pair_order=pair_order,
            pair_sides=pair_sides,
            assignment_version=version,
            a_level=a_level,
            mismatch_locus=locus,
            dossier_version=dossier.version,
            dossier_hash=dossier.content_hash,
            is_test=participant_no == QA_PARTICIPANT_NO,
        )
        db.add(participant)
        await db.flush()
        return participant

    # 자산 버전이 바뀌었다면 그 사실을 남긴다. **배정은 덮어쓰지 않는다** — 이미 세션이
    # 돈 참가자의 조건이 파일 변경으로 바뀌면 NT-07이 깨진다(§1.4 배정표 생성 후 금지).
    participant.dossier_version = dossier.version
    participant.dossier_hash = dossier.content_hash
    if participant.focal_condition is None:
        participant.focal_condition = focal
        participant.alt_order = alt_order
        participant.pair_order = pair_order
        participant.pair_sides = pair_sides
        participant.assignment_version = version
        participant.a_level = a_level
        participant.mismatch_locus = locus
    return participant


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """세션 생성 + 접속 코드 1개 발급. **평문 코드는 이 응답에만 존재한다**(§2.5)."""
    participant_no = payload.participant_no.strip().upper()
    if not is_participant_no(participant_no):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"알 수 없는 참가자 번호: {participant_no}"
        )

    if participant_no != QA_PARTICIPANT_NO:
        # §5.1 — 배정표의 행이 곧 참가자 목록이다. dossier보다 **먼저** 본다: 배정에 없는
        # 번호는 dossier가 있어도 참가자가 아니고, 사유가 정확해야 R1이 원인을 말할 수 있다.
        if not assignment.load().has(participant_no):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{participant_no}는 배정표에 없습니다 (§5.1 — 배정표의 행이 참가자 목록이다)",
            )
        existing = await store.sessions_of_participant(db, participant_no, BLOCKING_STATUSES)
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{participant_no}에 이미 세션이 있습니다 (참가자당 완료 세션 1개 — NT-12)",
            )

    try:
        participant = await _ensure_participant(db, participant_no)
    except (DossierNotFound, dossier_loader.DossierContractError) as exc:
        # §9.1 마지막 행 — 배정표·dossier 불일치는 세션 생성 409 + 사유 표시다.
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{participant_no} dossier를 쓸 수 없습니다: {exc}"
        ) from exc

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
        # 조건 라벨은 **연구자 화면 전용**이다(§1.2 — 참가자에게는 비공개).
        "focal_condition": participant.focal_condition,
        "alt_order": participant.alt_order,
        "pair_order": participant.pair_order,
        "access_code": code,
        "code_expires_at": _iso(session.code_expires_at),
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
        "code_expires_at": _iso(session.code_expires_at),
    }


# --------------------------------------------------------------------------- #
# R1 세션 관리 (§4.13) — 참가자 목록·배정·dossier lock·세션 상태 일람
# --------------------------------------------------------------------------- #


def _session_row(session: tables.Session) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "ss_state": session.ss_state,
        "f_state": session.f_state,
        "alt_index": session.alt_index,
        "pair_index": session.pair_index,
        "status": session.status,
        "created_at": _iso(session.created_at),
        "joined_at": _iso(session.joined_at),
        "code_expires_at": _iso(session.code_expires_at),
        "code_expired": access_code.is_expired(session.code_expires_at),
    }


@router.get("/participants")
async def list_participants(actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """R1 화면의 표 하나 (§4.13).

    배정(focal·대안 순서·pair 순서·좌우·A-level)은 **배정표에서** 읽어 보여 준다 — 세션이
    아직 없는 참가자도 배정을 미리 확인할 수 있어야 세션 전 체크리스트(부록 D.2)가 성립한다.
    dossier lock 상태(`locked`·`dummy`)는 D.2의 첫 줄이 요구하는 값이다.
    """
    table = assignment.load()
    rows: list[dict[str, Any]] = []

    numbers = list(table.participant_numbers)
    if QA_PARTICIPANT_NO not in numbers:
        numbers.insert(0, QA_PARTICIPANT_NO)

    for participant_no in numbers:
        try:
            dossier = dossier_loader.load(participant_no)
            dossier_info: dict[str, Any] = {
                "version": dossier.version,
                "locked": dossier.is_locked,
                "locked_at": dossier.locked_at,
                "hash": dossier.content_hash,
                "dummy": dossier.is_dummy,
                "a_level": dossier.evidence_code.a_level,
                "mismatch_locus": dossier.evidence_code.mismatch_locus,
            }
        except (DossierNotFound, dossier_loader.DossierContractError) as exc:
            # §9.1 — 세션 생성이 막히는 상태다. 감추지 않는다.
            dossier_info = {"error": str(exc), "locked": False, "dummy": False}

        sessions = await store.sessions_of_participant(db, participant_no)
        rows.append(
            {
                "participant_no": participant_no,
                "assignment": (
                    table.row(participant_no).as_dict() if table.has(participant_no) else None
                ),
                "dossier": dossier_info,
                "sessions": [_session_row(row) for row in sessions],
            }
        )

    await record(db, actor=actor, action=AuditAction.VIEW, target="console:R1")
    frozen = await freeze.current(db)
    return {
        "participants": rows,
        "assignment": {
            "version": table.version,
            "seed": table.seed,
            "n": len(table.rows),
            # §2.4·NT-42 — dummy로 내려간 상태를 감출 수 없게 한다.
            "is_dummy": table.is_dummy,
            "source": table.source_path.name,
            "constraints_checked": dict(table.constraints_checked),
        },
        # §11.2 모집 게이트 — **표시만** 한다. 시작 여부는 연구자가 정한다(자동 차단 없음).
        "launch_gate": [
            {"tag": blocker.tag, "detail": blocker.detail} for blocker in freeze.blockers()
        ],
        # §10.5 설계 동결 — soft launch 종료 시 `scripts/freeze_study_version.py`로 1회 기입.
        "study_version_frozen_at": _iso(frozen.frozen_at) if frozen else None,
    }


@router.get("/assignment")
async def assignment_view(actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """§8.2 — 배정표 전문(읽기 전용). R1·R4가 참조한다.

    **쓰기 경로가 없다.** 배정 변경은 파일과 `scripts/make_assignment.py`를 지나야 하고,
    모집 시작 후에는 금지다(§1.4).
    """
    table = assignment.load()
    await record(db, actor=actor, action=AuditAction.VIEW, target="console:assignment")
    return {
        "version": table.version,
        "generated_at": table.generated_at,
        "seed": table.seed,
        "is_dummy": table.is_dummy,
        "source": table.source_path.name,
        "constraints_checked": dict(table.constraints_checked),
        "strata": assignment.strata_spread(list(table.rows.values())),
        "rows": [row.as_dict() for row in table.rows.values()],
    }


@router.get("/costs")
async def costs(actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """§2.8 — `llm_calls` usage 합산. 대시보드도 상한도 두지 않는다(24세션 규모)."""
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
# R2 개입 — flag(non-blocking) · abort(SS90) · dropout(SS91)  §4.13 · §9.1 · NT-26
# --------------------------------------------------------------------------- #


class ReasonRequest(BaseModel):
    """flag·abort 공통. 사유는 **필수**다(§3.1 — 중단은 사유 필수)."""

    reason: str = Field(min_length=1)


@router.post("/sessions/{session_id}/flag")
async def flag_session(
    session_id: uuid.UUID, payload: ReasonRequest, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """§4.13 flag — **기록 전용**이다(D-07).

    상태를 바꾸지 않는다는 것이 이 엔드포인트의 전부다(NT-26). §3.4의 "checkpoint 수정이
    자극 전제를 깨뜨렸는가"에 대한 연구자 판단도 여기로 들어온다 — 시스템은 판정하지 않고
    사람의 메모를 남긴다.
    """
    session = await get_session_or_404(db, session_id)
    before = session.ss_state
    await store.record_event(
        db,
        session.id,
        FLAG_EVENT,
        payload={
            # 🔒 사유는 암호문으로 넣는다(§2.9 · §8.1 컬럼 목록 유지).
            REASON_FIELD: fernet.encrypt(payload.reason).decode("ascii"),
            "ss_state": before,
            "f_state": session.f_state,
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
    session.alt_index = None
    session.pair_index = None
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
    # §2.8 — 참가자 원문은 싣지 않는다(사유는 DB에만).
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
