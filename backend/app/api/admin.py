"""연구자 API — 세션 생성·코드 발급 (구현명세서 §8.2 · §2.5 · §2.7 · NT-12 · NT-27).

**NS2 범위는 세션을 시작시키는 데 필요한 최소한**이다. 콘솔 화면 R1–R4와 모니터·flag·abort·
review·export는 NS4다(§11.1). 여기 있는 두 엔드포인트가 없으면 참가자가 접속할 수 없다.

두 불변식이 이 파일에 걸린다.

- **참가자당 완료 세션 1개**(NT-12·§2.5). 진행 중이거나 완료된 세션이 있으면 새 세션을 만들지
  않는다. 다시 시작해야 하면 기존 세션을 중단 처리(SS90·SS91)한 뒤다 — 그 판단은 연구자가
  콘솔에서 한다(NS4). P00은 QA 전용이라 무제한이다(§2.5).
- **재발급은 같은 세션에 바인딩**(NT-27). 코드가 만료돼도 새 세션을 만들지 않는다 —
  §3.5의 "저장 지점 복원"이 세션 id에 걸려 있기 때문이다.

전 행위는 `audit_logs`에 남는다(§2.7).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api import store
from app.api.deps import AdminActor, DbSession
from app.assets import dossier_loader
from app.assets.files import PARTICIPANT_NUMBERS, QA_PARTICIPANT_NO
from app.core import access_code
from app.core.state_machine import SsState
from app.core.williams import sequence_index
from app.models import tables
from app.security.audit import AuditAction, record

router = APIRouter(prefix="/admin", tags=["researcher"])

#: 새 세션을 막는 기존 세션 상태 (NT-12).
BLOCKING_STATUSES = ("active", "done")


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
    session = await db.get(tables.Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "세션을 찾을 수 없습니다")

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
