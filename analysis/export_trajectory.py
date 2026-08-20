"""분석 export — participant × condition trajectory (구현명세서 §7.6 · 부록 B · §2.9 · NT-30).

    DEV_MODE=true python analysis/export_trajectory.py --actor <이름> --out exports/
    python analysis/export_trajectory.py --actor <이름> --out exports/ --include-text --coding coding.csv

분석 단위는 조건별 요약이 아니라 **participant × condition trajectory**다(§7.6 · 초안 §7.1).
그래서 기본 파일 `trajectory.csv`의 한 행 = 한 참가자의 한 branch이고, AI1→User1→sidecar→
AI2→downstream→평정이 그 행에 함께 실린다.

세 가지 통제가 §2.9·NT-30에서 온다.

1. **자유 텍스트는 열이 아니라 파일로 분리**한다. 기본 출력에는 참가자·연구자가 쓴 문장이
   한 글자도 없고, `--include-text`를 준 실행만 `free_text.csv`를 따로 만든다. 텍스트 없이
   돌리는 것이 기본값이어야 공유·재실행이 안전하다.
2. **복호화는 §2.9의 "② 분석 export" 지점**이다. 기본 실행도 텍스트 **길이**(§7.4 행동 측정)를
   위해 복호화하므로, 실행 1회당 `audit_logs`에 `export`와 `decrypt` 각 1행을 남긴다.
   플래그와 무관하게 남긴다 — 열지 않은 척할 수 있으면 audit이 아니다.
3. **비식별**: 저장된 것 자체가 가명(P01–P12)이고, 접속 코드·user_agent·IP는 어떤 파일에도
   나가지 않는다. 세션 id는 파일 간 조인 키로만 쓰고 참가자 번호와 1:1이다.

`first_opportunity`·`carryover_sensitive` 플래그는 `analysis/tagging_flags.py`가 붙인다.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from analysis.tagging_flags import annotate, load_coding  # noqa: E402
from app.assets import dossier_loader, rating_items  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import tables  # noqa: E402
from app.models.session import create_engine  # noqa: E402
from app.security import fernet  # noqa: E402
from app.security.audit import AuditAction, record  # noqa: E402

#: 자유 텍스트가 들어가는 유일한 파일 (`--include-text`).
FREE_TEXT_FILE = "free_text.csv"

#: 기본 출력 파일들 — 자유 텍스트 0열.
TRAJECTORY_FILE = "trajectory.csv"
RATINGS_FILE = "ratings.csv"
PRESURVEY_FILE = "presurvey.csv"
INTEGRITY_FILE = "generation_integrity.csv"
EVENTS_FILE = "events.csv"

#: §8.1 `events.payload`의 flag 사유(암호문) — 이벤트 파일에서는 통째로 제거한다.
REASON_FIELD = "reason_encrypted"

#: 이벤트 payload에서 지우는 키. `user_agent`는 §4.0의 운영 기록이지 분석 변수가 아니고,
#: 브라우저 지문이라 비식별 export에 실을 이유가 없다(§2.9 · NT-30).
EVENT_PAYLOAD_DROP: frozenset[str] = frozenset({REASON_FIELD, "user_agent"})

#: §7.3 12문항. 열 이름은 변수명 그대로다(합산 열은 만들지 않는다 — §0.4).
RATING_COLUMNS: tuple[str, ...] = tuple(
    f"rating_{item.item_id}" for item in rating_items.RATING_ITEMS
)


@dataclass(frozen=True, slots=True)
class ExportTables:
    """파일로 쓰기 전의 export 전체. 테스트는 파일 없이 이 구조만 본다."""

    trajectory: list[dict[str, Any]]
    ratings: list[dict[str, Any]]
    presurvey: list[dict[str, Any]]
    integrity: list[dict[str, Any]]
    events: list[dict[str, Any]]
    free_text: list[dict[str, Any]]

    def as_files(self) -> dict[str, list[dict[str, Any]]]:
        files = {
            TRAJECTORY_FILE: self.trajectory,
            RATINGS_FILE: self.ratings,
            PRESURVEY_FILE: self.presurvey,
            INTEGRITY_FILE: self.integrity,
            EVENTS_FILE: self.events,
        }
        if self.free_text:
            files[FREE_TEXT_FILE] = self.free_text
        return files


def _decrypt(value: bytes | None) -> str | None:
    return fernet.decrypt(value) if value else None


def _length(text: str | None) -> int | None:
    return len(text) if text is not None else None


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def collect(
    db: AsyncSession, *, actor: str, include_text: bool = False, coding_path: Path | None = None
) -> ExportTables:
    """DB → export 표. 파일 쓰기는 하지 않는다(호출부가 결정한다)."""
    coding = load_coding(coding_path) if coding_path else None

    sessions = list((await db.execute(select(tables.Session))).scalars().all())
    participants = {
        row.participant_no: row
        for row in (await db.execute(select(tables.Participant))).scalars().all()
    }

    trajectory: list[dict[str, Any]] = []
    ratings_rows: list[dict[str, Any]] = []
    presurvey_rows: list[dict[str, Any]] = []
    integrity_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    free_text: list[dict[str, Any]] = []

    for session in sessions:
        participant = participants.get(session.participant_no)
        dossier = dossier_loader.load(session.participant_no)
        session_key = str(session.id)

        if include_text and session.abort_reason:
            free_text.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "branch_index": "",
                    "field": "abort_reason",
                    "text": _decrypt(session.abort_reason),
                }
            )

        flag_events = (
            await db.execute(
                select(tables.Event).where(
                    tables.Event.session_id == session.id,
                    tables.Event.type.like("researcher_%"),
                )
            )
        ).scalars().all()
        flag_count = sum(1 for event in flag_events if event.type == "researcher_flag")

        for event in (
            await db.execute(
                select(tables.Event)
                .where(tables.Event.session_id == session.id)
                .order_by(tables.Event.server_ts)
            )
        ).scalars().all():
            payload = {
                key: value
                for key, value in (event.payload or {}).items()
                if key not in EVENT_PAYLOAD_DROP
            }
            event_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "type": event.type,
                    # §2.11 — 파생 지표(latency·체류)는 계산하지 않는다. 쌍만 남긴다(NT-29).
                    "client_ts": _iso(event.client_ts),
                    "server_ts": _iso(event.server_ts),
                    "payload": json.dumps(payload, ensure_ascii=False) if payload else "",
                }
            )
            if include_text and (event.payload or {}).get(REASON_FIELD):
                free_text.append(
                    {
                        "participant_no": session.participant_no,
                        "session_id": session_key,
                        "branch_index": "",
                        "field": f"{event.type}.reason",
                        "text": fernet.decrypt(event.payload[REASON_FIELD].encode("ascii")),
                    }
                )

        for row in (
            await db.execute(
                select(tables.PresurveyResponse)
                .where(tables.PresurveyResponse.session_id == session.id)
                .order_by(tables.PresurveyResponse.display_order)
            )
        ).scalars().all():
            presurvey_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "item_id": row.item_id,
                    "value": json.dumps(row.value, ensure_ascii=False),
                    "display_order": row.display_order,
                }
            )

        branches = list(
            (
                await db.execute(
                    select(tables.Branch)
                    .where(tables.Branch.session_id == session.id)
                    .order_by(tables.Branch.branch_index)
                )
            )
            .scalars()
            .all()
        )
        for branch in branches:
            turns = {
                turn.role: turn
                for turn in (
                    await db.execute(
                        select(tables.Turn).where(tables.Turn.branch_id == branch.id)
                    )
                )
                .scalars()
                .all()
            }
            user1 = turns.get("user1")
            ai2 = turns.get("ai2")
            sidecar = (
                await db.execute(
                    select(tables.SidecarEntry).where(tables.SidecarEntry.branch_id == branch.id)
                )
            ).scalars().one_or_none()
            action = (
                await db.execute(
                    select(tables.DownstreamAction).where(
                        tables.DownstreamAction.branch_id == branch.id
                    )
                )
            ).scalars().one_or_none()
            normalization = (
                await db.execute(
                    select(tables.Normalization).where(
                        tables.Normalization.branch_id == branch.id
                    )
                )
            ).scalars().first()
            generations = list(
                (
                    await db.execute(
                        select(tables.Generation)
                        .where(tables.Generation.branch_id == branch.id)
                        .order_by(tables.Generation.attempt)
                    )
                )
                .scalars()
                .all()
            )
            final = next((row for row in generations if row.final), None)
            branch_ratings = list(
                (
                    await db.execute(
                        select(tables.Rating)
                        .where(tables.Rating.branch_id == branch.id)
                        .order_by(tables.Rating.display_order)
                    )
                )
                .scalars()
                .all()
            )
            values = {row.item_id: row.value for row in branch_ratings}

            user1_text = _decrypt(user1.text) if user1 else None
            row: dict[str, Any] = {
                "participant_no": session.participant_no,
                "session_id": session_key,
                "is_test": bool(participant.is_test) if participant else "",
                "sequence_index": participant.sequence_index if participant else "",
                "branch_index": branch.branch_index,
                "condition": branch.condition or "",
                "actionability": dossier.sampling.actionability,
                "mismatch_locus": dossier.sampling.mismatch_locus,
                "dossier_version": dossier.version,
                "dossier_locked": dossier.is_locked,
                "stimulus_hash": branch.stimulus_hash or "",
                "user1_disposition": branch.user1_disposition or "",
                "user1_chars": _length(user1_text),
                "normalization_applied": bool(normalization.applied) if normalization else "",
                "matched_pattern_id": (normalization.matched_pattern_id or "") if normalization else "",
                "referent_id": (normalization.referent_id or "") if normalization else "",
                "sidecar_choice": sidecar.choice if sidecar else "",
                "sidecar_relevance": sidecar.relevance_1_7 if sidecar else "",
                "sidecar_text_chars": _length(_decrypt(sidecar.free_text)) if sidecar else "",
                "sidecar_reason_chars": _length(_decrypt(sidecar.reason_text)) if sidecar else "",
                "ai2_present": ai2 is not None,
                "ai2_chars": _length(_decrypt(ai2.text)) if ai2 else "",
                "fallback_used": bool(final.fallback_used) if final else "",
                "regenerated": (final.attempt > 1) if final else "",
                "checker_skipped": any(row.checker_skipped for row in generations) if generations else "",
                "violations": json.dumps(
                    [v for row in generations for v in (row.rule_violations or [])],
                    ensure_ascii=False,
                ),
                "downstream_action": action.code if action else "",
                "branch_started_at": _iso(branch.started_at),
                "branch_completed_at": _iso(branch.completed_at),
                "session_status": session.status,
                "session_ss_state": session.ss_state,
                "flag_count": flag_count,
                **{
                    f"rating_{item.item_id}": values.get(item.item_id, "")
                    for item in rating_items.RATING_ITEMS
                },
            }
            trajectory.append(row)

            for rating in branch_ratings:
                ratings_rows.append(
                    {
                        "participant_no": session.participant_no,
                        "branch_index": branch.branch_index,
                        "condition": branch.condition or "",
                        "item_id": rating.item_id,
                        "value": rating.value,
                        "block": rating.block,
                        "display_order": rating.display_order,
                    }
                )

            for generation in generations:
                integrity_rows.append(
                    {
                        "participant_no": session.participant_no,
                        "branch_index": branch.branch_index,
                        "condition": branch.condition or "",
                        "attempt": generation.attempt,
                        "final": generation.final,
                        "fallback_used": generation.fallback_used,
                        "checker_skipped": generation.checker_skipped,
                        "rule_violations": json.dumps(
                            generation.rule_violations or [], ensure_ascii=False
                        ),
                        "checker_result": json.dumps(
                            generation.checker_result or {}, ensure_ascii=False
                        ),
                        "created_at": _iso(generation.created_at),
                    }
                )

            if include_text:
                for field, text in (
                    ("user1_raw", user1_text),
                    ("user1_normalized", _decrypt(user1.text_normalized) if user1 else None),
                    ("ai2_final_text", _decrypt(ai2.text) if ai2 else None),
                    ("sidecar_text", _decrypt(sidecar.free_text) if sidecar else None),
                    ("sidecar_reason", _decrypt(sidecar.reason_text) if sidecar else None),
                ):
                    if text:
                        free_text.append(
                            {
                                "participant_no": session.participant_no,
                                "session_id": session_key,
                                "branch_index": branch.branch_index,
                                "field": field,
                                "text": text,
                            }
                        )

    trajectory = annotate(trajectory, coding)

    # §2.9 — export·복호화 각 1행. 실행 단위로 남긴다(행 단위로 남기면 이력이 잡음이 된다).
    await record(db, actor=actor, action=AuditAction.EXPORT, target=f"trajectory:{len(trajectory)}행")
    await record(
        db,
        actor=actor,
        action=AuditAction.DECRYPT,
        target=f"export:{'text' if include_text else 'lengths'}",
    )
    return ExportTables(
        trajectory=trajectory,
        ratings=ratings_rows,
        presurvey=presurvey_rows,
        integrity=integrity_rows,
        events=event_rows,
        free_text=free_text,
    )


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """빈 표도 파일로 남긴다 — 파일이 없는 것과 데이터가 없는 것은 다르다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="trajectory export (§7.6 · NT-30)")
    parser.add_argument("--actor", required=True, help="실행자 — audit_logs에 남는다 (§2.9)")
    parser.add_argument("--out", type=Path, default=Path("exports"), help="출력 디렉터리")
    parser.add_argument(
        "--include-text",
        action="store_true",
        help=f"자유 텍스트를 {FREE_TEXT_FILE}로 함께 내보낸다 (기본: 내보내지 않음)",
    )
    parser.add_argument("--coding", type=Path, help="§7.6 표현 코딩 CSV (carryover 플래그)")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_engine(settings.resolved_database_url, settings.db_schema)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        exported = await collect(
            db, actor=args.actor, include_text=args.include_text, coding_path=args.coding
        )
        await db.commit()
    await engine.dispose()

    for name, rows in exported.as_files().items():
        write_csv(args.out / name, rows)
        print(f"{args.out / name}: {len(rows)}행")
    if not args.include_text:
        print(f"자유 텍스트는 내보내지 않았다 — 필요하면 --include-text ({FREE_TEXT_FILE} 분리 생성)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
