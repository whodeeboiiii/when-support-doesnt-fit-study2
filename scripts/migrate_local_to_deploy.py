"""로컬 SQLite → 배포 Postgres 데이터 이관 (§2.4 배포 전환 보조).

    python scripts/migrate_local_to_deploy.py --source proto_v2_local.sqlite3 \
        --target "$DATABASE_URL" --target-schema proto_v2            # 미리보기(기본)
    python scripts/migrate_local_to_deploy.py ... --apply            # 실제 이관

**왜 필요한가.** 로컬에서 돌린 세션은 로컬 파일 DB에 남는다. 배포로 옮기는 순간 그 데이터는
따라오지 않는다 — 완주한 세션은 export에서 빠지고, **진행 중인 세션은 재개할 수 없다**
(참가자가 다시 접속하면 배포 DB에는 그 세션이 없다).

**하지 않는 것.**
- schema를 바꾸지 않는다. 원본과 대상의 테이블 정의는 같은 `Base.metadata`다.
- 대상에 이미 행이 있으면 멈춘다. 두 번 돌려 데이터가 겹치는 것이 가장 나쁜 결과다.
- 🔒 컬럼은 **암호문 그대로** 옮긴다. 따라서 배포 환경의 `FERNET_KEY`가 원본과 같아야
  복호화된다(§2.9 — "수집 시작 후 변경 금지"가 이관에도 그대로 걸린다).

**시각.** SQLite는 tz 없는 값으로 저장한다(`CURRENT_TIMESTAMP` = UTC). Postgres의
`timestamptz`에 그대로 넣으면 서버 TimeZone 설정에 따라 해석이 갈리므로, 넣기 전에 UTC를
명시해 붙인다. 이 변환이 없으면 세션 시각이 조용히 몇 시간씩 밀린다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import Table, create_engine, func, inspect, select, text  # noqa: E402

from app.models import Base  # noqa: E402
from app.models import tables  # noqa: F401,E402  (모델 등록)


def sync_url(url: str) -> str:
    """async 드라이버가 붙은 URL을 동기용으로 되돌린다 — 이관은 한 번 도는 배치다."""
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def source_url(value: str) -> str:
    if "://" in value:
        return sync_url(value)
    path = Path(value).resolve()
    if not path.is_file():
        raise SystemExit(f"원본 SQLite 파일이 없다: {path}")
    return f"sqlite:///{path}"


def redact(url: str) -> str:
    parsed = urlparse(url)
    if parsed.password:
        return url.replace(parsed.password, "***")
    return url


def to_utc(value: object) -> object:
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def read_rows(connection, table: Table) -> list[dict]:
    rows = []
    for row in connection.execute(select(table)).mappings():
        rows.append({key: to_utc(val) for key, val in row.items()})
    return rows


def count(connection, table: Table) -> int:
    return connection.execute(select(func.count()).select_from(table)).scalar_one()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="로컬 SQLite → 배포 Postgres 이관")
    parser.add_argument("--source", required=True, help="SQLite 파일 경로 또는 URL")
    parser.add_argument("--target", required=True, help="대상 DATABASE_URL (Postgres)")
    parser.add_argument("--target-schema", required=True, help="대상 schema (예: proto_v2)")
    parser.add_argument("--apply", action="store_true", help="실제로 쓴다 (기본은 미리보기)")
    args = parser.parse_args(argv)

    src_engine = create_engine(source_url(args.source))
    dst_engine = create_engine(sync_url(args.target))
    schema = args.target_schema
    if not schema.replace("_", "").isalnum():
        raise SystemExit(f"허용되지 않는 schema 이름: {schema!r}")

    print(f"원본 : {redact(str(src_engine.url))}")
    print(f"대상 : {redact(str(dst_engine.url))} · schema={schema}")
    print(f"모드 : {'실제 이관(--apply)' if args.apply else '미리보기'}")
    print()

    ordered = Base.metadata.sorted_tables  # FK 의존 순서
    with src_engine.connect() as src, dst_engine.connect() as dst:
        dst.execute(text(f'SET search_path TO "{schema}", public'))

        inspector = inspect(dst)
        missing = [t.name for t in ordered if not inspector.has_table(t.name, schema=schema)]
        if missing:
            raise SystemExit(
                f"대상 schema에 테이블이 없다: {', '.join(missing)}\n"
                "  → 먼저 `python scripts/init_db.py`를 대상 구성으로 한 번 돌려라."
            )

        payload: dict[str, list[dict]] = {}
        occupied: dict[str, int] = {}
        for table in ordered:
            rows = read_rows(src, table)
            if rows:
                payload[table.name] = rows
            existing = count(dst, table)
            if existing:
                occupied[table.name] = existing

        total = sum(len(r) for r in payload.values())
        for table in ordered:
            n = len(payload.get(table.name, []))
            if n:
                print(f"  {table.name:22s} {n:5d}행")
        print(f"  {'합계':22s} {total:5d}행")
        print()

        if occupied:
            print("❌ 대상 schema가 비어 있지 않다 — 겹쳐 쓰지 않는다.")
            for name, existing in occupied.items():
                print(f"  - {name}: {existing}행")
            print("  → 빈 schema를 쓰거나(권장: 새 schema), 대상 데이터를 먼저 정리하라.")
            return 1

        if not total:
            print("옮길 행이 없다.")
            return 0

        if not args.apply:
            print("미리보기다 — 아무것도 쓰지 않았다. 실제 이관은 `--apply`.")
            return 0

        # 이 커넥션은 위의 조회로 이미 트랜잭션을 열어 뒀다(autobegin). 같은 트랜잭션에
        # 그대로 쓰고 한 번에 커밋한다 — 전부 들어가거나 하나도 안 들어가거나 둘 중 하나다.
        try:
            for table in ordered:
                rows = payload.get(table.name)
                if rows:
                    dst.execute(table.insert(), rows)
            dst.commit()
        except Exception:
            dst.rollback()
            raise
        print("✅ 이관 완료 — 대상 행수 확인:")

    with dst_engine.connect() as dst:
        dst.execute(text(f'SET search_path TO "{schema}", public'))
        for table in ordered:
            n = count(dst, table)
            if n:
                print(f"  {table.name:22s} {n:5d}행")
    print()
    print("⚠ 🔒 필드는 암호문 그대로 옮겼다 — 배포의 FERNET_KEY가 원본과 같아야 읽힌다(§2.9).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
