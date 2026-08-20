"""부록 D.1 QA 리허설 CLI (구현명세서 §10.2 · §11.1 NS4).

    DEV_MODE=true python scripts/run_qa_rehearsal.py --out reports/qa_rehearsal.md

CI 상주분은 `tests/integration/test_qa_rehearsal.py`다. 이 스크립트는 **QA 기록에 붙일
보고서**가 필요할 때 쓴다 — 부록 D.1의 다섯 줄이 각각 무엇으로 확인됐는지, 수동으로 남은
항목이 무엇인지 마크다운으로 남긴다.

리허설은 **일회용 임시 DB**에 돈다. 시연용 `dev_local.db`나 배포 DB를 리허설 데이터로
오염시키지 않기 위해서다(§2.4 schema 규율과 같은 취지).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

#: 리허설 전용 자격·키. 실행 환경의 값을 쓰지 않는다(§2.4 — 비밀은 환경변수 전용).
_TEMP_DB = Path(tempfile.mkdtemp(prefix="study2_qa_")) / f"{uuid.uuid4().hex}.sqlite3"
os.environ["DEV_MODE"] = "true"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEMP_DB}"
os.environ["DB_SCHEMA"] = "proto_v1"
os.environ.setdefault("STUDY_VERSION", "proto_v1_qa")
os.environ.pop("DISCORD_WEBHOOK_URL", None)

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.llm.fake_llm import FakeLLM  # noqa: E402
from app.llm.gateway.client import set_client  # noqa: E402
from app.models import Base, tables  # noqa: E402,F401
from app.models.session import create_engine  # noqa: E402
from tests import helpers, qa_rehearsal  # noqa: E402

#: 서버가 요구할 Basic auth 자격을 **리허설 헬퍼가 쓰는 값**으로 맞춘다.
#: 실행 환경의 실제 ADMIN_USER/PASS를 쓰지 않는다 — 리허설은 자기 자격으로 돈다(§2.4).
os.environ["ADMIN_USER"], os.environ["ADMIN_PASS"] = helpers.ADMIN_AUTH


def _install_notification_capture() -> list[tuple[str, dict]]:
    """§2.8 발화를 가로챈다 — 리허설이 Discord로 새 나가지 않게 한다."""
    import importlib

    from tests.helpers import NOTIFY_CALL_SITES

    captured: list[tuple[str, dict]] = []

    async def _record(event, summary: str, **fields: object) -> bool:
        captured.append((str(event), {"summary": summary, **fields}))
        return True

    for module_name in NOTIFY_CALL_SITES:
        setattr(importlib.import_module(module_name), "notify", _record)
    return captured


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="부록 D.1 QA 리허설 (DEV_MODE)")
    parser.add_argument("--out", type=Path, help="마크다운 보고서 경로")
    args = parser.parse_args(argv)

    get_settings.cache_clear()
    settings = get_settings()

    from app.main import create_app
    from app.models.session import get_session

    engine = create_engine(settings.resolved_database_url, settings.db_schema)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    fake = FakeLLM()
    set_client(fake)
    notifications = _install_notification_capture()

    app = create_app()
    async with maker() as db:
        app.dependency_overrides[get_session] = lambda: db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://qa") as client:
            report = await qa_rehearsal.run(client, db, llm=fake, notifications=notifications)
        await db.commit()
    await engine.dispose()
    set_client(None)

    rendered = report.render_markdown()
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"보고서: {args.out}")
    print(f"리허설 DB: {_TEMP_DB}")
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
