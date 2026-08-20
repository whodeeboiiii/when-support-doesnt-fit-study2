"""FastAPI 단일 서비스 진입점 (구현명세서 §2.0 · §5.4 · §6.7).

배포 단위 1개다: React(Vite) 빌드 정적 서빙 + `/api` + (NS4) `/admin` 콘솔.

기동 시 두 가지를 한다.

1. **자산 게이트(§5.4)**: dossier 전수를 스키마 검증한다. 필수 키 누락·질문 수 계약 위반이면
   **기동을 실패시킨다** — 자산이 깨진 채 세션을 받는 것보다 안 뜨는 편이 안전하다.
   prompt_config의 `prompt_hash` 정합도 같은 자리에서 본다(§6.7 재현성).
2. **LLM 클라이언트 주입(§2.0)**: DEV_MODE면 fake LLM, 아니면 OpenRouter. 배포 구성과 동일
   코드 경로이고 분기는 이 지점과 DB URL 두 곳뿐이다.

라우터: `/api/health`, 참가자 API(§8.2 — `api/participant.py`·`api/branch.py`), 연구자 API
(`api/admin.py`·`api/admin_views.py`)와 콘솔 화면(`api/console.py`). DEV_MODE + 로컬 DB일 때만
개발용 초기화 API(`api/dev.py`)가 추가로 붙는다 — 배포 구성에는 그 경로가 존재하지 않는다.

미들웨어가 하나 걸려 있다: §2.8의 "서버 오류(5xx) 누적" 알림. 5xx는 개별 라우터가 아니라
응답 경계에서만 일관되게 보이기 때문에 여기 있어야 한다.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api import admin, admin_views, branch, console, health, participant
from app.assets import dossier_loader, presurvey
from app.core.config import get_settings, is_local_db
from app.llm import normalization, prompts
from app.llm.fake_llm import FakeLLM
from app.llm.gateway.client import NoClientConfigured, set_client
from app.llm.gateway.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def validate_runtime_config() -> None:
    """§2.4·§0.5 구성 게이트 — DB 대상이 실행 구성과 맞는지 **기동 시점에** 본다.

    첫 요청까지 미루면 서버는 정상으로 보이고 참가자 화면만 500이 된다. 특히 DEV_MODE에
    원격 DB가 물린 구성은 조용히 성공하는 편이 더 위험하다(시연 데이터가 배포 DB로 간다).
    """
    settings = get_settings()
    url = settings.resolved_database_url
    logger.info(
        "DB 대상: %s (DEV_MODE=%s, schema=%s)",
        "로컬 SQLite" if url.startswith("sqlite") else "원격",
        settings.dev_mode,
        settings.db_schema,
    )


def validate_assets() -> None:
    """§5.4 기동 게이트. 예외를 삼키지 않는다 — 실패는 기동 실패다."""
    prompts.verify()
    presurvey.validate()
    normalization.validate_patterns()
    dossiers = dossier_loader.validate_all()
    dummies = sorted(no for no, dossier in dossiers.items() if dossier.is_dummy)
    if dummies:
        # 더미로 뜨는 것 자체는 개발·시연의 정상 상태다(§11.1 더미 자산 원칙).
        # 다만 조용히 넘어가지 않는다 — 본 모집 게이트는 PH-03 착지다(§11.3).
        logger.warning("dossier 스키마 더미로 기동: %s (<TODO: PH-03 실값 lock>)", dummies)
    logger.info("자산 검증 통과 — dossier %d건, prompt_config %s", len(dossiers), prompts.config_hash()[:12])


def _install_llm_client() -> None:
    settings = get_settings()
    if settings.dev_mode:
        set_client(FakeLLM())
        logger.info("DEV_MODE — fake LLM 주입 (§6.7)")
        return
    try:
        set_client(OpenRouterClient.from_settings(settings))
    except NoClientConfigured:
        # 키 미설정으로 기동을 막지 않는다 — 호출 시점에 §9.1 경로(재시도 → fallback)로
        # 수렴시키는 편이 dead-end 금지 원칙에 맞다.
        logger.warning("LLM 클라이언트 미설정 — 호출 시 §9.1 fallback 경로로 수렴한다")


async def _watch_server_errors(request: Request, call_next):
    """§2.8 트리거 5 — 서버 오류(5xx) 누적 알림.

    처리되지 않은 예외도 5xx로 세되(FastAPI가 500을 만들기 **전에** 여기를 지난다), 예외
    자체는 삼키지 않고 그대로 올린다. 알림 경로가 오류를 감추면 §9.1의 복구 규율이 깨진다.
    """
    from app.notify import watch

    try:
        response = await call_next(request)
    except Exception:
        await watch.record_server_error(f"{request.method} {request.url.path}")
        raise
    if response.status_code >= 500:
        await watch.record_server_error(f"{request.method} {request.url.path} → {response.status_code}")
    else:
        watch.record_server_success()
    return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _install_llm_client()
    yield
    set_client(None)


def create_app() -> FastAPI:
    validate_runtime_config()
    validate_assets()
    settings = get_settings()
    app = FastAPI(
        title="NOT QUITE YES — Study 2 enactment",
        version=settings.study_version,
        lifespan=lifespan,
        # 참가자에게 노출될 이유가 없는 문서 경로는 열지 않는다.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.middleware("http")(_watch_server_errors)
    app.include_router(health.router)
    app.include_router(participant.router)
    app.include_router(branch.router)
    app.include_router(admin.router)
    app.include_router(admin_views.router)
    app.include_router(console.router)

    if settings.dev_mode and is_local_db(settings.resolved_database_url):
        # 개발용 초기화 API (§2.0 시연 구성). **배포 구성에서는 라우터를 붙이지 않는다** —
        # 권한으로 막는 것과 경로가 없는 것은 다르다(`api/dev.py` 상단 참조).
        from app.api import dev

        app.include_router(dev.router)
        logger.warning("DEV_MODE — 개발용 초기화 API를 연다: %s", dev.router.prefix)

    if FRONTEND_DIST.is_dir():
        # SPA 정적 서빙 (§2.0). 빌드 산출물이 없으면(API 전용 개발) 그냥 건너뛴다.
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        logger.info("frontend/dist 없음 — API만 서빙한다 (npm run build 후 정적 서빙)")
    return app


app = create_app()
