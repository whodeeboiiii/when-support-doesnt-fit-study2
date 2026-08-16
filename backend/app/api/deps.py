"""라우터 공통 의존성 (구현명세서 §2.5 · §2.7 · §3.1).

- **참가자**: httpOnly 쿠키의 세션 토큰 → `sessions` 행. 토큰이 없거나 서명이 틀리면 401이고,
  참가자 화면은 P0(접속)로 돌아간다(§9.1 — dead-end 금지).
- **연구자**: HTTP Basic (§2.7). 자격은 환경변수 전용이고 코드 기본값이 없다.

세션 상태 검증도 여기서 한 겹 건다: 종결·중단 상태(SS07·SS90·SS91)에서는 어떤 제출도 받지
않는다. 개별 라우터가 각자 기억하게 두면 언젠가 한 곳이 빠진다.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.state_machine import TERMINAL_SS, SsState
from app.models import tables
from app.models.session import get_session as get_db_session
from app.security import tokens

#: 세션 토큰 쿠키 (§2.5 httpOnly). 이름은 짧게 — Zoom 화면공유 중 devtools가 열릴 수도 있다.
SESSION_COOKIE = "s2_session"

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def set_session_cookie(response, session_id: uuid.UUID) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        tokens.issue(session_id),
        httponly=True,
        samesite="lax",
        # 로컬 개발(http)에서 secure 쿠키는 저장되지 않는다. 배포는 항상 https(Railway).
        secure=not settings.dev_mode,
        max_age=60 * 60 * 24,
        path="/",
    )


async def current_session(request: Request, db: DbSession) -> tables.Session:
    """쿠키 → 세션 행. 없으면 401(참가자는 P0로 돌아간다)."""
    try:
        session_id = tokens.read(request.cookies.get(SESSION_COOKIE))
    except tokens.InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "세션이 없습니다") from exc
    row = await db.get(tables.Session, session_id)
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "세션이 없습니다")
    return row


CurrentSession = Annotated[tables.Session, Depends(current_session)]


def require_active(session: tables.Session) -> SsState:
    """진행 중 세션만 제출을 받는다 (§3.1 — SS07·SS90·SS91은 종결)."""
    state = SsState(session.ss_state)
    if state in TERMINAL_SS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"종결된 세션입니다 ({state})")
    return state


_basic = HTTPBasic(auto_error=True)


def require_admin(credentials: Annotated[HTTPBasicCredentials, Depends(_basic)]) -> str:
    """§2.7 HTTP Basic. 자격 미설정이면 **열지 않는다** — 빈 값 통과는 인증이 아니다."""
    settings = get_settings()
    if not settings.admin_user or not settings.admin_pass:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "연구자 콘솔 자격이 설정되지 않았습니다 (§2.4)"
        )
    user_ok = secrets.compare_digest(credentials.username, settings.admin_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "인증 실패",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


AdminActor = Annotated[str, Depends(require_admin)]
