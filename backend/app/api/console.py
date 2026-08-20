"""연구자 콘솔 화면 서빙 (구현명세서 §2.7 · §4.12).

콘솔은 **빌드 없는 정적 HTML 1장**(`frontend/console/index.html`)이고 여기서 Basic auth 뒤에
서빙한다. 참가자 SPA와 분리한 이유는 두 가지다.

1. **NT-13**: 조건 라벨·researcher_only·sidecar를 다루는 화면 코드가 참가자 번들에 들어갈 수
   있는 경로를 만들지 않는다. 두 화면이 한 번들이면 "안 들어가게 조심"이 유일한 방어가 된다.
2. 세션 진행 중 콘솔을 고쳐야 할 때 참가자 번들을 재빌드하지 않는다.

데이터는 전부 `/admin/*` JSON(§8.2)에서 온다 — 이 라우터는 파일 하나를 돌려줄 뿐이다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import AdminActor, DbSession
from app.security.audit import AuditAction, record

router = APIRouter(prefix="/admin", tags=["researcher"])

CONSOLE_HTML = Path(__file__).resolve().parents[3] / "frontend" / "console" / "index.html"


@router.get("/console", include_in_schema=False)
async def console(actor: AdminActor, db: DbSession) -> FileResponse:
    """R1–R4 콘솔 페이지. 인증은 `AdminActor`(§2.7 Basic auth)가 건다.

    페이지 자체에는 데이터가 없지만 **연 사실은 남긴다** — §2.7의 "모든 콘솔 조회"에는
    콘솔을 연 것도 포함된다고 읽는 편이 접근 이력으로 쓸모 있다.
    """
    if not CONSOLE_HTML.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "콘솔 파일이 없습니다")
    await record(db, actor=actor, action=AuditAction.VIEW, target="console:page")
    # 콘솔 화면을 캐시에 남기지 않는다 — 세션 중 화면공유 환경이다(부록 D.3).
    return FileResponse(CONSOLE_HTML, media_type="text/html", headers={"Cache-Control": "no-store"})
