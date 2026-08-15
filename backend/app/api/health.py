"""헬스체크 (§2.0 상시 구동 서비스의 기동 확인용).

참가자·연구자 어느 화면도 아니다. 자산 **내용**은 절대 싣지 않는다 — 참가자 브라우저에서
열리는 경로이므로 dossier·자극 원문이 여기로 새면 §2.9(클라이언트에 자극 사전 로드 금지,
NT-13) 위반이다. 실린 것은 개수·버전 문자열뿐이다.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.assets import dossier_loader
from app.core.config import get_settings
from app.llm import prompts

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    dossiers = dossier_loader.load_all()
    return {
        "status": "ok",
        "study_version": settings.study_version,
        "db_schema": settings.db_schema,
        "dev_mode": settings.dev_mode,
        "prompt_config_version": prompts.version_lock()["prompt_config_version"],
        "dossiers": {
            "loaded": len(dossiers),
            # 실값이 아직 안 들어온 참가자 — 콘솔 R4·부록 D.2의 lock 확인 항목과 같은 정보다.
            "schema_dummy": sorted(no for no, d in dossiers.items() if d.is_dummy),
            "locked": sorted(no for no, d in dossiers.items() if d.is_locked),
        },
    }
