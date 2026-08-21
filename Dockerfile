# syntax=docker/dockerfile:1
#
# 배포 이미지 (구현명세서 §2.0 — "단일 상시 구동 FastAPI 서비스 + React/Vite 정적 서빙").
#
# §2.0의 "배포 단위 1개"를 이미지 수준에서 그대로 지킨다: 프런트를 빌드해 `dist`를 만들고,
# **같은 이미지 안의** FastAPI가 그 dist와 `/api`·`/admin`을 함께 서빙한다. 프런트를 별도
# 호스트에 올리면 `credentials: 'same-origin'`(api.ts)이 깨지고 CORS·SameSite 설정이
# 새로 필요해진다 — 배포 단위를 쪼개지 않는 이유다.
#
# 플랫폼 중립이다. Railway가 이 파일을 그대로 빌드하고, 무료 정책이 바뀌면 Render·Fly·
# Cloud Run이 같은 이미지를 받는다. 호스트 고유 설정(볼륨·헬스체크·도메인)은 이미지가
# 아니라 플랫폼 콘솔에 둔다.
#
# ⚠ **소스 트리 배치를 그대로 유지해야 한다.** 앱이 자산·정적 파일을 `__file__` 기준 상대
#    경로로 찾기 때문이다:
#      assets/files.py    REPO_ROOT     = parents[3]                        → /app
#      api/console.py     CONSOLE_HTML  = parents[3]/frontend/console/…     → /app/frontend/console/
#      main.py            FRONTEND_DIST = parents[2]/frontend/dist          → /app/frontend/dist
#    그래서 `pip install .`(site-packages로 복사)이 아니라 **`pip install -e .`**를 쓴다.
#    복사본으로 설치되면 위 셋이 전부 엉뚱한 경로를 가리켜 기동 게이트(§5.4)가 그 자리에서
#    죽는다. 이 줄을 바꾸려면 세 경로 계산을 먼저 바꿔라.

# --------------------------------------------------------------------------- #
# 1단계 — 프런트 빌드 (§2.0 React 18 + Vite + TS + Tailwind)
# --------------------------------------------------------------------------- #
FROM node:22-slim AS frontend

WORKDIR /build

# 의존성 레이어를 소스와 분리한다 — src/ 수정만으로 npm ci를 다시 돌리지 않는다.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# `tsc -b && vite build` — 타입 오류는 빌드 실패다(이미지에 깨진 dist를 넣지 않는다).
RUN npm run build

# --------------------------------------------------------------------------- #
# 2단계 — 런타임 (FastAPI, Python 3.12+)
# --------------------------------------------------------------------------- #
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 의존성은 pyproject 단일 정본에서 온다 — requirements.txt를 따로 두지 않는다(목록이 갈라진다).
COPY pyproject.toml ./
COPY backend/ ./backend/
RUN pip install -e .

# 런타임에 읽는 자산. 전부 `REPO_ROOT` 기준이므로 배치가 리포와 같아야 한다.
#   prompts/     llm/prompts.py — prompt_config 정본·prompt_hash 대조(§6.6)
#   fixtures/    assets/rating_items.py · pairwise_items.py
#   dossiers/    P00 실값 + schema_dummy (실값 P01–P30은 커밋 대상이 아니다 — §2.9)
#   assignments/ assignment_dummy.json (실값은 미커밋 — DOSSIER_DIR·ASSIGNMENT_PATH로 주입)
COPY prompts/ ./prompts/
COPY fixtures/ ./fixtures/
COPY dossiers/ ./dossiers/
COPY assignments/ ./assignments/
COPY scripts/ ./scripts/
COPY analysis/ ./analysis/

# 연구자 콘솔은 빌드 없는 정적 HTML 1장이다(§2.1) — Vite 산출물이 아니라 원본을 그대로 싣는다.
COPY frontend/console/ ./frontend/console/
COPY --from=frontend /build/dist ./frontend/dist

# 기동 전에 스키마를 만든다. `create_all`은 멱등이라 매 부팅 안전하고(scripts/init_db.py),
# 볼륨이 비어 있거나 컨테이너가 갈린 뒤에도 테이블이 있는 상태로 수렴한다 — 이게 없으면
# 첫 요청이 `no such table: sessions`로 죽는다(앱은 테이블을 만들지 않는다).
#
# `exec`로 uvicorn을 PID 1에 올려 플랫폼의 SIGTERM이 그대로 전달되게 한다.
# `$PORT`는 플랫폼이 주입한다(Railway·Render·Cloud Run 공통). 로컬 확인용 기본값 8000.
CMD ["sh", "-c", "python scripts/init_db.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
