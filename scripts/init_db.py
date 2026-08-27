"""스키마 생성 (구현명세서 §2.4 — v5.0 `scripts/init_db.py` 이식·개정).

Alembic은 도입하지 않는다(v5.0 §11.1 결정 승계) — 수집 기간이 짧고 스키마 변경은 §1.4에
따라 본실험 시작 후 금지이며, 환경 분리는 schema 단위다. 스키마를 바꿀 때는 **새 schema로
갈아탄다**(구 schema는 읽기 전용 동결): `proto_v1`(시연·QA) → `main_v1`(본실험).
`create_all`은 기존 테이블을 변경하지 않으므로 in-place 반영이 아니다.

    DEV_MODE=true python scripts/init_db.py     # 로컬 SQLite
    python scripts/init_db.py                   # DATABASE_URL·DB_SCHEMA 필요
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402
from app.models import tables  # noqa: E402,F401  (모델 등록)
from app.models.session import create_engine, ensure_schema  # noqa: E402


def _safe(url: str) -> str:
    """로그에 실릴 URL에서 **비밀번호를 가린다**(§2.9 — 비밀정보는 환경변수 전용).

    이 한 줄은 배포 기동 로그로 나가고 Railway 로그에 그대로 남는다. 원문을 찍으면
    프로젝트 접근 권한이 있는 사람 전원에게 DB 비밀번호가 평문으로 보인다.
    """
    from sqlalchemy.engine import make_url

    return make_url(url).render_as_string(hide_password=True)


async def main() -> None:
    settings = get_settings()
    url = settings.resolved_database_url
    engine = create_engine(url, settings.db_schema)
    await ensure_schema(engine, settings.db_schema)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print(f"created {len(Base.metadata.tables)} tables — url={_safe(url)} schema={settings.db_schema}")


if __name__ == "__main__":
    asyncio.run(main())
