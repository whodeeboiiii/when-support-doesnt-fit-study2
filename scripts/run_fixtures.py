"""fixture 러너 CLI (구현명세서 §10.1).

    DEV_MODE=true python scripts/run_fixtures.py                 # fake LLM (CI와 동일 판정)
    python scripts/run_fixtures.py --real --out reports/fixtures.md   # 실모델 1회 (QA 직전)

CI 상주분은 `tests/integration/test_fixture_runner.py`다. 이 스크립트는 **보고서**가 필요할 때
쓴다 — 블록별 통과율과 불일치 목록을 마크다운으로 남겨 QA 기록(부록 D)에 붙인다.

`--real`은 §10.1의 "실모델 실행은 QA 직전 1회"다. 실키·슬러그가 있어야 하고 비용이 든다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.llm.fake_llm import FakeLLM  # noqa: E402
from app.llm.gateway.client import set_client  # noqa: E402
from app.llm.gateway.openrouter_client import OpenRouterClient  # noqa: E402
from app.models import Base, tables  # noqa: E402,F401
from app.models.session import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402
from tests import fixture_runner  # noqa: E402


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="normalization·integrity fixture 실행 (§10.1)")
    parser.add_argument("--out", type=Path, help="마크다운 보고서 경로")
    parser.add_argument(
        "--real",
        action="store_true",
        help="실모델로 checker를 돌린다 (QA 직전 1회 — 비용 발생)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.real:
        set_client(OpenRouterClient.from_settings(settings))
    else:
        set_client(FakeLLM())

    # llm_calls 기록에도 실제 경로를 쓴다(§8.4). 실행 흔적은 fixture 전용 DB에 남는다.
    engine = create_engine(settings.resolved_database_url, settings.db_schema)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    normalization_report = fixture_runner.run_normalization_fixture()
    async with maker() as session:
        integrity_report = await fixture_runner.run_integrity_fixture(session)
        await session.commit()
    await engine.dispose()

    reports = [
        (normalization_report, fixture_runner.NORMALIZATION_THRESHOLDS),
        (
            integrity_report,
            # 실모델에서는 checker 블록에 게이트를 걸지 않는다 [파일럿 확정 — §10.1].
            {**fixture_runner.INTEGRITY_THRESHOLDS, "C": None}
            if args.real
            else fixture_runner.INTEGRITY_THRESHOLDS,
        ),
    ]
    document = fixture_runner.render_markdown(reports)
    print(document)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(document, encoding="utf-8")

    breaches = [
        breach for report, thresholds in reports for breach in report.gate_failures(thresholds)
    ]
    return 1 if breaches else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
