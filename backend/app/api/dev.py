"""DEV_MODE 전용 개발 보조 API (구현명세서 §2.0 · §0.5 — "fake LLM + 로컬 DB, 팀 시연 구성").

**이 라우터는 명세서의 연구 API가 아니다.** 시연·QA를 반복해서 돌리기 위한 개발 도구이고,
그래서 세 겹으로 가둔다.

1. **등록 자체가 조건부다**(`main.create_app`). DEV_MODE가 아니거나 DB가 로컬이 아니면
   라우터를 붙이지 않는다 — 배포 구성에서는 경로가 존재하지 않는다(404).
2. **요청 시점에 한 번 더 본다**(`_require_dev`). 설정이 런타임에 바뀌어도 열리지 않는다.
3. **연구 로직을 우회하지 않는다.** 하는 일은 "참가자 산출물 삭제 + 정상 경로로 새 세션·새
   접속 코드 발급"뿐이다. 자동 로그인·상태 점프·조건 지정은 만들지 않는다 — 그런 뒷문이
   생기면 시연이 검증하는 것이 실제 파이프라인이 아니게 되고(§3.5 복원·NT-07 immutability),
   P0부터 다시 밟는다는 보장이 사라진다.

지우는 것은 **참가자 산출물뿐**이다. `audit_logs`는 지우지 않는다 — §2.7의 접근 이력은
초기화의 대상이 아니고, 개발용 초기화가 이력을 지울 수 있으면 그 이력은 증거가 아니다.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api import admin
from app.api.deps import SESSION_COOKIE, DbSession
from app.assets.files import QA_PARTICIPANT_NO, is_participant_no
from app.core import access_code
from app.core.config import get_settings, is_local_db
from app.core.state_machine import SsState
from app.models import tables
from app.security.audit import AuditAction, record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dev", tags=["dev"])

#: 개발용 초기화가 남기는 `audit_logs.actor`. 연구자 계정과 구분되어야 사후에 걸러낼 수 있다.
DEV_ACTOR = "dev_mode"


def _require_dev() -> None:
    """DEV_MODE + 로컬 DB가 아니면 **경로가 없는 것처럼** 굴린다(403이 아니라 404)."""
    settings = get_settings()
    if not settings.dev_mode or not is_local_db(settings.resolved_database_url):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


async def purge_participant(db: DbSession, participant_no: str) -> dict[str, int]:
    """해당 참가자의 세션 산출물을 전부 지운다. `audit_logs`·`participants`는 남긴다."""
    session_ids = select(tables.Session.id).where(
        tables.Session.participant_no == participant_no
    )
    run_ids = select(tables.FocalRun.id).where(tables.FocalRun.session_id.in_(session_ids))
    view_ids = select(tables.PairwiseView.id).where(
        tables.PairwiseView.session_id.in_(session_ids)
    )
    generation_ids = select(tables.Generation.id).where(
        tables.Generation.focal_run_id.in_(run_ids)
    )

    deleted: dict[str, int] = {}

    async def _wipe(model, condition) -> None:  # noqa: ANN001
        result = await db.execute(delete(model).where(condition))
        deleted[model.__tablename__] = int(result.rowcount or 0)

    # generations를 참조하는 것부터 → focal_runs를 참조하는 것 → sessions를 참조하는 것 순.
    await _wipe(tables.LlmCall, tables.LlmCall.generation_id.in_(generation_ids))
    await _wipe(tables.Turn, tables.Turn.focal_run_id.in_(run_ids))
    await _wipe(tables.DownstreamAction, tables.DownstreamAction.focal_run_id.in_(run_ids))
    await _wipe(tables.SidecarEntry, tables.SidecarEntry.focal_run_id.in_(run_ids))
    await _wipe(tables.Generation, tables.Generation.focal_run_id.in_(run_ids))
    await _wipe(tables.PairwiseResponse, tables.PairwiseResponse.pairwise_view_id.in_(view_ids))
    await _wipe(tables.PairwiseView, tables.PairwiseView.session_id.in_(session_ids))
    await _wipe(tables.AltExposure, tables.AltExposure.session_id.in_(session_ids))
    await _wipe(tables.Rating, tables.Rating.session_id.in_(session_ids))
    await _wipe(tables.CheckpointEdit, tables.CheckpointEdit.session_id.in_(session_ids))
    # D-44 — 사전설문 행도 `sessions`를 참조한다. 여기서 빠지면 세션을 지우는 순간
    # 고아 행이 남고 Postgres에서는 FK 위반으로 초기화 자체가 실패한다.
    await _wipe(tables.PresurveyResponse, tables.PresurveyResponse.session_id.in_(session_ids))
    await _wipe(tables.Event, tables.Event.session_id.in_(session_ids))
    await _wipe(tables.FocalRun, tables.FocalRun.session_id.in_(session_ids))
    await _wipe(tables.Session, tables.Session.participant_no == participant_no)
    await db.flush()
    return deleted


@router.get("/status")
async def dev_status(db: DbSession) -> dict[str, Any]:
    """개발 바가 자기 존재 여부를 묻는 자리. 배포에서는 404라서 바가 아예 그려지지 않는다."""
    _require_dev()
    result = await db.execute(select(tables.Session).order_by(tables.Session.created_at))
    sessions = [
        {
            "participant_no": row.participant_no,
            "ss_state": row.ss_state,
            "f_state": row.f_state,
            "status": row.status,
        }
        for row in result.scalars().all()
    ]
    # §5.1 — 세션을 열 수 있는 번호는 배정표의 행 + P00이다.
    from app.core import assignment

    numbers = [QA_PARTICIPANT_NO, *assignment.load().participant_numbers]
    return {
        "dev_mode": True,
        "participants": numbers,
        "default_participant": QA_PARTICIPANT_NO,
        "sessions": sessions,
    }


class ResetRequest(BaseModel):
    participant_no: str = QA_PARTICIPANT_NO


@router.post("/reset")
async def reset_participant(
    payload: ResetRequest, response: Response, db: DbSession
) -> dict[str, Any]:
    """진행 상태를 지우고 **새 접속 코드**를 발급한다 — 그 다음은 P0부터 정상 경로다.

    자동 접속시키지 않는 이유가 이 도구의 핵심 제약이다: P0(§4.0)도 파이프라인의 일부라
    건너뛰면 시연이 그 화면을 검증하지 못한다. 그래서 여기서 하는 일은 "초기화 + 코드 발급"
    까지이고, 접속은 참가자 화면에서 사람이 한다.
    """
    _require_dev()
    participant_no = payload.participant_no.strip().upper()
    if not is_participant_no(participant_no):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"알 수 없는 참가자 번호: {participant_no}")

    deleted = await purge_participant(db, participant_no)

    # 참가자 행은 남기고 자산 버전만 갱신한다 — 세션 생성 경로(§8.2 `POST /admin/sessions`)와
    # 같은 함수를 쓴다. 초기화 전용 생성 경로를 따로 만들면 둘이 언젠가 갈라진다.
    await admin._ensure_participant(db, participant_no)
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
    # 발급은 발급이다 — 개발용이라도 §8.1의 `code_issue`로 남긴다(행위 목록은 늘리지 않는다).
    await record(db, actor=DEV_ACTOR, action=AuditAction.CODE_ISSUE, target=f"session:{session.id}")
    # 실패 지연 카운터(§4.0)도 프로세스 메모리다 — 초기화했는데 429가 남아 있으면 안 된다.
    access_code.record_success(participant_no)
    # 지워진 세션을 가리키는 쿠키를 브라우저에 남기지 않는다(§9.1 — 401 dead-end 방지).
    response.delete_cookie(SESSION_COOKIE, path="/")
    logger.warning("DEV_MODE 초기화: %s — 삭제 %s", participant_no, deleted)
    return {
        "participant_no": participant_no,
        "session_id": str(session.id),
        "access_code": code,
        "code_expires_at": session.code_expires_at.isoformat() if session.code_expires_at else None,
        "deleted": deleted,
    }
