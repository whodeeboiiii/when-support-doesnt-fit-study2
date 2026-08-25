"""설계 동결 · 모집 게이트 점검 (구현명세서 §10.5 · §11.2).

    python scripts/freeze_study_version.py --check              # 모집 게이트 + 자산 출처
    python scripts/freeze_study_version.py --actor <이름>        # soft launch 종료 시 1회 동결

`--check`는 **어디서 읽었는가**(§2.4 `DOSSIER_DIR`·`ASSIGNMENT_PATH`)를 함께 찍는다 — PH-04
반입 직후의 첫 확인이 그것이다. 게이트가 PH-03을 보고할 때 "볼륨이 안 붙었다"와 "파일은
있는데 아직 lock 전이다"가 구분되지 않으면 손을 댈 수 없다.

§10.5: "soft launch 종료 시 `study_version`에 spec_version·prompt_hash·model_strings·
assets_hash 동결 기입. 이후 변경은 §1.4 본실험 열만 적용."

동결은 **한 번**이다. 이미 기록이 있으면 그대로 두고 알려만 준다 — 덮어쓰기는 동결이 아니다.
미착지 항목(PH-03·PH-IRB 등)이 있으면 동결을 거절한다: 무엇을 고정했는지 말할 수 없는
상태에서 고정 기록을 남기면 그 기록이 거짓이 된다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core import freeze  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import tables  # noqa: E402,F401  (모델 등록)
from app.models.session import create_engine  # noqa: E402
from app.security.audit import AuditAction, record  # noqa: E402


def _print_sources() -> None:
    """§2.4 · PH-04 — 지금 읽고 있는 파일이 무엇인가."""
    sources = freeze.asset_sources()
    dossiers = sources["dossiers"]
    mark = " (DOSSIER_DIR 오버라이드)" if sources["dossier_dir_overridden"] else ""

    print("자산 출처 (§2.4 · PH-04)")
    print(f"  dossier 디렉터리 : {sources['dossier_dir']}{mark}")
    if sources["schema_dummy_dir"] != f"{sources['dossier_dir']}/schema_dummy":
        print(f"  스키마 더미      : {sources['schema_dummy_dir']} (리포 바닥으로 내려감)")
    print(
        f"  dossier          : 실값 {len(dossiers['real'])}건 "
        f"(lock {len(dossiers['locked'])}건) · 더미 {len(dossiers['dummy'])}건"
    )
    if dossiers["dummy"]:
        print(f"    더미로 뜬 번호 : {', '.join(dossiers['dummy'])}")

    entry = sources["assignment"]
    if entry.get("error"):
        print(f"  배정표           : 읽을 수 없다 — {entry['error']}")
    else:
        state = "dummy" if entry["is_dummy"] else "실값"
        print(f"  배정표           : {entry['path']} [{state} · {entry['version']} · {entry['rows']}행]")

    for label, key in (("focal 문항", "focal_items"), ("pairwise 문항", "pairwise_items")):
        item = sources[key]
        state = "placeholder" if item["is_placeholder"] else "실값"
        print(f"  {label:<15}: {item['version']} [{state}]")
    print(f"  동의서 버전      : {sources['consent_version']}")
    print()


def _print_gate(blockers: list[freeze.Blocker]) -> None:
    if not blockers:
        print("모집 게이트: 통과 — PH-03·PH-IRB 계열 착지 (§11.2)")
        return
    print(f"모집 게이트: 미착지 {len(blockers)}건 — 본 모집을 시작하지 않는다 (§11.2)")
    for blocker in blockers:
        print(f"  - {blocker.tag}: {blocker.detail}")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="study_version 동결 (§10.5)")
    parser.add_argument("--actor", help="실행자 — audit_logs에 남는다 (§2.7)")
    parser.add_argument("--check", action="store_true", help="게이트만 점검하고 쓰지 않는다")
    args = parser.parse_args(argv)

    if args.check:
        _print_sources()
    blockers = freeze.blockers()
    _print_gate(blockers)

    if args.check:
        return 0 if not blockers else 1
    if not args.actor:
        parser.error("--actor가 필요하다 (동결은 감사 대상 행위다)")
    if blockers:
        print("\n동결하지 않았다 — 위 항목 착지 후 다시 실행하라.")
        return 1

    settings = get_settings()
    engine = create_engine(settings.resolved_database_url, settings.db_schema)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        row, created = await freeze.freeze(db, frozen_at=datetime.now(UTC))
        if created:
            await record(db, actor=args.actor, action=AuditAction.EXPORT, target="study_version")
        await db.commit()
    await engine.dispose()

    if created:
        print(f"\n동결 기입: spec {row.spec_version} · prompt {row.prompt_hash[:12]} · {row.frozen_at}")
    else:
        print(f"\n이미 동결돼 있다 ({row.frozen_at}) — 덮어쓰지 않았다 (§1.4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
