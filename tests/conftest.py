"""테스트 공통 픽스처 (v5.0 `tests/conftest.py` 이식·개정).

- **LLM 실호출 0건**: 전 테스트에 `FakeLLM`을 주입한다. 주입이 없으면 게이트웨이가
  `NoClientConfigured`를 raise하므로 실호출로 새는 경로가 없다(§6.7).
- **DB는 DEV_MODE의 SQLite**(§2.0). 구 리포는 로컬 Postgres를 요구했지만, 신 명세는 DEV_MODE를
  정식 구성으로 두므로 CI가 외부 DB 없이 돈다. Postgres 전용 경로(search_path)는
  `models/session.py`가 URL로 분기한다.
- 도메인 로직은 HTTP를 거치지 않고 직접 import한다 — 화면·API가 붙기 전(NS1)에도 계약을 건다.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

#: §2.7 Basic auth — 테스트 전용 자격증명(실값은 환경변수에만 존재한다).
ADMIN_USER = "test-admin"
ADMIN_PASS = "test-admin-password"

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="study2_enactment_test_"))
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{_TEST_DB_DIR / f'{uuid.uuid4().hex}.sqlite3'}"


@pytest.fixture(scope="session", autouse=True)
def _test_env() -> None:
    """설정을 테스트 값으로 고정한다. 비밀정보는 테스트 전용 임시값."""
    os.environ["DEV_MODE"] = "true"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["DB_SCHEMA"] = "proto_v2"
    os.environ["STUDY_VERSION"] = "proto_v2_test"
    os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
    os.environ["ADMIN_USER"] = ADMIN_USER
    os.environ["ADMIN_PASS"] = ADMIN_PASS
    os.environ.pop("DISCORD_WEBHOOK_URL", None)
    os.environ.pop("OPENROUTER_API_KEY", None)

    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _committed_assets_only(_test_env: None) -> AsyncIterator[None]:
    """실값 배정표가 로컬에 착지해도 테스트는 **커밋된 자산**으로 돈다 (§2.9 · PH-08).

    `assignments/assignment_v1.json`은 gitignore 대상이라 CI에는 없다. 그 파일이 있고
    없고에 따라 판정이 갈리면 "연구팀 컴퓨터에서만 빨간" 테스트가 되고, 그건 자산을
    만드는 사람이 가장 CI를 믿어야 하는 시점에 CI를 못 믿게 만든다.

    실값 자산 자체의 검증은 여기가 아니라 기동 게이트(§5.4)와
    `scripts/freeze_study_version.py --check`가 한다.
    """
    from app.core import assignment

    original = assignment.DEFAULT_ASSIGNMENT_PATH
    assignment.DEFAULT_ASSIGNMENT_PATH = original.with_name("__테스트에서는_보지_않는다__.json")
    assignment.reset_cache()
    yield
    assignment.DEFAULT_ASSIGNMENT_PATH = original
    assignment.reset_cache()


@pytest.fixture(scope="session")
async def engine(_test_env: None) -> AsyncIterator:
    from app.models import Base
    from app.models import tables  # noqa: F401  (모델 등록)
    from app.models.session import create_engine

    eng = create_engine(TEST_DATABASE_URL, "proto_v2")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """테스트마다 트랜잭션을 롤백해 서로 오염되지 않게 한다."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        maker = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with maker() as sess:
            yield sess
        await trans.rollback()


@pytest.fixture(autouse=True)
def llm(_test_env: None) -> AsyncIterator:
    """전 테스트에 fake 게이트웨이를 주입한다 (LLM 실호출 0건)."""
    from app.llm.fake_llm import FakeLLM
    from app.llm.gateway import calls
    from app.llm.gateway.client import set_client

    fake = FakeLLM()
    set_client(fake)
    calls.reset_concurrency_guard()
    yield fake
    set_client(None)


@pytest.fixture(autouse=True)
def _reset_access_code_throttle() -> None:
    """§4.0 실패 지연 카운터도 프로세스 메모리다 — 테스트 간 누수를 막는다."""
    from app.core import access_code

    access_code.reset_throttle()


@pytest.fixture(autouse=True)
def _reset_notify_state() -> None:
    """§2.8 watch는 프로세스 메모리 상태를 쓴다 — 테스트 간 누수를 막는다."""
    from app.notify import watch

    watch.reset()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.main import create_app
    from app.models.session import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
