"""DB 연결·세션 (구현명세서 §2.4).

불변 규칙: 코드에 schema-qualified 테이블명을 쓰지 않는다. schema(`proto_v1` → `main_v1`)는
**오직 연결 수준의 search_path**에서만 결정된다.

⚠ Postgres(Supabase)에서는 커넥션 단위 `SET`만으로 부족하다 — pooler가 `SET`을 실행한 서버
커넥션과 이후 쿼리를 실행하는 커넥션을 다르게 줄 수 있어 search_path가 role 기본값으로
돌아간다. 그래서 **트랜잭션이 열릴 때마다** 다시 건다(v5.0 §2.4.2 규율 승계).

DEV_MODE의 SQLite에는 schema 개념이 없으므로 이 훅을 걸지 않는다 — §2.0이 말한 "분기는
LLM 클라이언트·DB URL 두 지점뿐"을 지키려면 분기를 URL 해석 지점에 가둬야 한다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_engine(url: str, db_schema: str) -> AsyncEngine:
    engine = create_async_engine(url, pool_pre_ping=True, future=True)
    if is_sqlite(url):
        return engine

    # 식별자 인젝션 방지: schema명은 영숫자·밑줄만. **엔진 생성 시 1회** 검증한다 —
    # 매 커넥션마다 던지면 부팅은 성공하고 모든 요청만 500이 되어 원인을 찾기 어렵다.
    if not db_schema.replace("_", "").isalnum():
        raise ValueError(f"허용되지 않는 schema 이름: {db_schema!r}")
    statement = f'SET search_path TO "{db_schema}", public'

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(statement)
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn) -> None:  # noqa: ANN001
        """pooler가 커넥션을 갈아끼워도 이 트랜잭션에서는 반드시 우리 schema를 본다."""
        conn.exec_driver_sql(statement)

    return engine


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.resolved_database_url, settings.db_schema)
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 의존성. 요청당 1 세션·1 트랜잭션 (§9.1 DB write 실패 → rollback, 부분 상태 금지)."""
    async with sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ensure_schema(target_engine: AsyncEngine, db_schema: str) -> None:
    """Postgres에서만 의미가 있다. SQLite는 파일 하나가 곧 schema다."""
    if is_sqlite(str(target_engine.url)):
        return
    async with target_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{db_schema}"'))
