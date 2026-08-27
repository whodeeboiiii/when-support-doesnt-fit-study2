"""DB 대상 해석 규칙 (구현명세서 §2.0 · §2.4 · §0.5).

§2.0은 배포와 시연이 **동일 코드 경로**를 돌되 갈리는 지점이 두 곳뿐이라고 못박는다:
LLM 클라이언트와 DB URL. 그 두 번째 지점이 여기다.

양방향으로 조용한 흘러내림을 막는다.

- 운영 구성에서 `DATABASE_URL` 미설정 → 로컬 파일 DB로 흘러내리면 수집 데이터가 배포 DB
  밖에 쌓인다. 기동 실패가 맞다.
- 시연 구성(DEV_MODE=true)에 원격 DB → **시연·QA 데이터가 배포 DB로 들어간다.** fake AI2
  산출물이 실참가자 데이터와 같은 테이블에 남고, §2.4의 schema 전환 규율이 무의미해진다.
  §0.5가 DEV_MODE를 "fake LLM + 로컬 DB"로 정의하므로 이것도 기동 실패가 맞다.
"""

from __future__ import annotations

import pytest

from app.core.config import DEV_DATABASE_URL, Settings, is_local_db

REMOTE_URL = "postgresql+psycopg://user:secret@db.example.supabase.co:5432/postgres"


def test_dev_mode_without_url_falls_back_to_local_sqlite() -> None:
    settings = Settings(dev_mode=True, database_url="")
    assert settings.resolved_database_url == DEV_DATABASE_URL
    assert is_local_db(settings.resolved_database_url)


def test_dev_mode_accepts_an_explicit_sqlite_url() -> None:
    """CI·테스트는 임시 파일 SQLite를 명시한다 — 그건 여전히 로컬 DB다."""
    settings = Settings(dev_mode=True, database_url="sqlite+aiosqlite:///./tmp.sqlite3")
    assert settings.resolved_database_url == "sqlite+aiosqlite:///./tmp.sqlite3"


def test_dev_mode_refuses_a_remote_database() -> None:
    """§0.5 — DEV_MODE는 로컬 DB 구성이다. 시연 데이터를 배포 DB에 넣지 않는다."""
    settings = Settings(dev_mode=True, database_url=REMOTE_URL)
    with pytest.raises(RuntimeError) as caught:
        _ = settings.resolved_database_url
    message = str(caught.value)
    assert "DEV_MODE" in message
    assert "secret" not in message, "오류 문안에 자격증명을 싣지 않는다"


def test_production_requires_an_explicit_url() -> None:
    settings = Settings(dev_mode=False, database_url="")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _ = settings.resolved_database_url


def test_production_uses_the_given_url_as_is() -> None:
    settings = Settings(dev_mode=False, database_url=REMOTE_URL)
    assert settings.resolved_database_url == REMOTE_URL


def test_boot_gate_calls_the_same_rule() -> None:
    """기동 시점에 본다 — 첫 요청까지 미루면 서버는 정상으로 보이고 화면만 500이 된다."""
    import inspect

    from app import main

    assert "validate_runtime_config()" in inspect.getsource(main.create_app)
    assert "resolved_database_url" in inspect.getsource(main.validate_runtime_config)


def test_schema_defaults_are_the_new_lineage() -> None:
    """§2.4 — v2 계보는 `proto_v2`(시연·QA) → `main_v2`(본실험). **v1 schema는 읽기 전용 동결**이다."""
    settings = Settings()
    assert settings.db_schema in {"proto_v2", "main_v2", "proto_v2_test"}
    # v1 schema에 쓰기가 열리면 수집 데이터가 구 설계의 테이블로 들어간다.
    assert not settings.db_schema.endswith("_v1")
    assert not settings.db_schema.startswith("pilot")


# --------------------------------------------------------------------------- #
# 드라이버 정규화 — 배포 콘솔이 주는 URL 그대로 붙였을 때 기동이 죽지 않게 한다.
#
# Supabase·Railway는 `postgresql://…` 형태를 복사해 준다. SQLAlchemy는 드라이버가 빠진
# 그 형태를 psycopg2(동기·미설치)로 해석하므로 배포 도중 `ModuleNotFoundError`로 끊긴다.
# 여기서 바꾸는 것은 **드라이버뿐**이고 연결 대상은 그대로다 — 위 파일 상단이 막는
# "다른 DB에 조용히 붙는" 문제와는 층위가 다르다.
# --------------------------------------------------------------------------- #

BARE_URL = "postgresql://user:secret@db.example.supabase.co:5432/postgres"


def test_bare_postgres_url_gets_the_installed_driver() -> None:
    settings = Settings(dev_mode=False, database_url=BARE_URL)
    resolved = settings.resolved_database_url
    assert resolved.startswith("postgresql+psycopg://")
    # 연결 대상은 한 글자도 바뀌지 않는다.
    assert resolved.endswith("user:secret@db.example.supabase.co:5432/postgres")


def test_postgres_legacy_scheme_is_normalized_too() -> None:
    """일부 호스트는 아직 `postgres://`를 준다."""
    settings = Settings(dev_mode=False, database_url="postgres://u:p@h:5432/db")
    assert settings.resolved_database_url == "postgresql+psycopg://u:p@h:5432/db"


def test_normalization_never_touches_sqlite() -> None:
    settings = Settings(dev_mode=True, database_url="sqlite+aiosqlite:///./tmp.sqlite3")
    assert settings.resolved_database_url == "sqlite+aiosqlite:///./tmp.sqlite3"


def test_normalization_does_not_reopen_the_dev_mode_hole() -> None:
    """드라이버가 빠진 원격 URL도 DEV_MODE에서는 여전히 기동 실패여야 한다."""
    settings = Settings(dev_mode=True, database_url=BARE_URL)
    with pytest.raises(RuntimeError, match="DEV_MODE"):
        _ = settings.resolved_database_url


def test_only_the_installed_async_driver_is_used() -> None:
    """psycopg3 외의 async 드라이버는 설치돼 있지 않다 — 정규화 대상을 하나로 묶어둔다."""
    from app.core.config import PG_ASYNC_URL_PREFIX

    assert PG_ASYNC_URL_PREFIX == "postgresql+psycopg://"
    with pytest.raises(ModuleNotFoundError):
        __import__("psycopg2")
