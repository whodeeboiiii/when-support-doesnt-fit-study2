"""FastAPI 단일 서비스 진입점 (구현명세서 §2.0 · §5.4 · §6.7).

배포 단위 1개다: React(Vite) 빌드 정적 서빙 + `/api` + (NS4) `/admin` 콘솔.

기동 시 두 가지를 한다.

1. **자산 게이트(§5.4)**: dossier 전수를 스키마 검증한다. 필수 키 누락·질문 수 계약 위반이면
   **기동을 실패시킨다** — 자산이 깨진 채 세션을 받는 것보다 안 뜨는 편이 안전하다.
   prompt_config의 `prompt_hash` 정합도 같은 자리에서 본다(§6.7 재현성).
2. **LLM 클라이언트 주입(§2.0)**: DEV_MODE면 fake LLM, 아니면 OpenRouter. 배포 구성과 동일
   코드 경로이고 분기는 이 지점과 DB URL 두 곳뿐이다.

NS2까지의 라우터: `/api/health`, 참가자 API(§8.2 — `api/participant.py`·`api/branch.py`),
연구자 세션 생성·코드 발급(`api/admin.py`). AI2 파이프라인 본체는 NS3, 콘솔 R1–R4는 NS4다.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import admin, branch, health, participant
from app.assets import dossier_loader, presurvey
from app.core.config import get_settings
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
    app.include_router(health.router)
    app.include_router(participant.router)
    app.include_router(branch.router)
    app.include_router(admin.router)

    if FRONTEND_DIST.is_dir():
        # SPA 정적 서빙 (§2.0). 빌드 산출물이 없으면(API 전용 개발) 그냥 건너뛴다.
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        logger.info("frontend/dist 없음 — API만 서빙한다 (npm run build 후 정적 서빙)")
    return app


app = create_app()
