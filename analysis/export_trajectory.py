"""분석 export — participant × focal trajectory (구현명세서 §7.7 · 부록 B · §2.9 · NT-30).

    DEV_MODE=true python analysis/export_trajectory.py --actor <이름> --out exports/
    python analysis/export_trajectory.py --actor <이름> --out exports/ --include-text --latency

분석 단위가 v2에서 바뀌었다. v1.0.1은 "participant × condition"(한 참가자가 네 조건을 다
경험)이었지만, v2는 **focal between**이므로 한 참가자의 한 행이 곧 그 참가자의 유일한
focal trajectory다(D-23). 대신 **pairwise**가 참가자당 3행으로 within 비교를 담는다.

파일 7종(부록 H.2):

| 파일 | 단위 | 성격 |
|---|---|---|
| `trajectory.csv` | 참가자 1행 | focal 전 과정 + 평정 요약(계량만) |
| `checkpoint_edits.csv` | 수정 1행 | **길이·segment만**. 문장은 opt-in 파일에 |
| `presurvey.csv` | 문항 1행 | 사전설문 응답 (D-44 — 자유 텍스트 없음) |
| `ratings.csv` | 문항 1행 | focal 5 construct + MC 2 |
| `pairwise.csv` | pair 1행 | contrast·좌우·`focal_included` + 문항 응답 |
| `alt_exposure.csv` | 노출 1행 | 순서·조건·시각 |
| `generation_integrity.csv` | 시도 1행 | §7.7 — AI2 행동 코딩의 기계 열 |
| `events.csv` | 이벤트 1행 | beacon 쌍 |
| `dossier_provenance.csv` | 사건 1행 | §7.7 — provenance 구성비(논문 보고용) |
| `free_text.csv` | **opt-in** | 자유 텍스트 (`--include-text`) |

세 가지 통제가 §2.9·NT-30에서 온다.

1. **자유 텍스트는 열이 아니라 파일로 분리**한다. 기본 출력에는 참가자·연구자가 쓴 문장이
   한 글자도 없고, `--include-text`를 준 실행만 `free_text.csv`를 따로 만든다.
2. **복호화는 §2.9의 "export" 지점**이다. 기본 실행도 텍스트 **길이**(§7.4 행동 측정)를
   위해 복호화하므로, 실행 1회당 `audit_logs`에 `export`와 `decrypt` 각 1행을 남긴다.
   플래그와 무관하게 남긴다 — 열지 않은 척할 수 있으면 audit이 아니다.
3. **비식별**: 저장된 것 자체가 가명(P01–P30)이고, 접속 코드·user_agent·IP는 어떤 파일에도
   나가지 않는다. 세션 id는 파일 간 조인 키로만 쓴다.

**삭제된 것**(부록 B): `sequence_index`·`branch_index`·`disposition(no_reply)`·
`normalization_*`·`first_opportunity`·`carryover_sensitive`. 마지막 둘은 4-branch 설계와
함께 소멸했다(§7.7 — "first-opportunity·carryover 태깅은 폐기"). `presurvey_*`는 v2.0에서
삭제됐다가 **D-44로 복원**됐다 — 다만 trajectory의 열이 아니라 **별도 파일**이다(문항
1행). participant characterization 전용이라 focal 행에 붙일 이유가 없고, 붙이면 열 수가
문항 수를 따라 흔들린다.
`response_latency`는 **기본 미산출**이고 `--latency`를 준 실행만 계산한다(§2.11).
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

from app.assets import dossier_loader, pairwise_items, presurvey, rating_items  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models import tables  # noqa: E402
from app.models.session import create_engine  # noqa: E402
from app.security import fernet  # noqa: E402
from app.security.audit import AuditAction, record  # noqa: E402

#: 자유 텍스트가 들어가는 유일한 파일 (`--include-text`).
FREE_TEXT_FILE = "free_text.csv"

#: 기본 출력 파일들 — 자유 텍스트 0열.
TRAJECTORY_FILE = "trajectory.csv"
CHECKPOINT_EDITS_FILE = "checkpoint_edits.csv"
PRESURVEY_FILE = "presurvey.csv"
RATINGS_FILE = "ratings.csv"
PAIRWISE_FILE = "pairwise.csv"
ALT_EXPOSURE_FILE = "alt_exposure.csv"
INTEGRITY_FILE = "generation_integrity.csv"
EVENTS_FILE = "events.csv"
PROVENANCE_FILE = "dossier_provenance.csv"

#: §8.1 `events.payload`의 flag 사유(암호문) — 이벤트 파일에서는 통째로 제거한다.
REASON_FIELD = "reason_encrypted"

#: 이벤트 payload에서 지우는 키. `user_agent`는 §4.0의 운영 기록이지 분석 변수가 아니고,
#: 브라우저 지문이라 비식별 export에 실을 이유가 없다(§2.9 · NT-30).
EVENT_PAYLOAD_DROP: frozenset[str] = frozenset({REASON_FIELD, "user_agent", "viewport"})

#: §2.11 `--latency` — beacon 쌍에서 계산할 화면. 기본 실행에서는 산출하지 않는다.
LATENCY_PAIRS: tuple[tuple[str, str], ...] = (("render_complete", "submit"),)


@dataclass(frozen=True, slots=True)
class ExportTables:
    """파일로 쓰기 전의 export 전체. 테스트는 파일 없이 이 구조만 본다."""

    trajectory: list[dict[str, Any]]
    checkpoint_edits: list[dict[str, Any]]
    presurvey: list[dict[str, Any]]
    ratings: list[dict[str, Any]]
    pairwise: list[dict[str, Any]]
    alt_exposure: list[dict[str, Any]]
    integrity: list[dict[str, Any]]
    events: list[dict[str, Any]]
    provenance: list[dict[str, Any]]
    free_text: list[dict[str, Any]]

    def as_files(self) -> dict[str, list[dict[str, Any]]]:
        files = {
            TRAJECTORY_FILE: self.trajectory,
            CHECKPOINT_EDITS_FILE: self.checkpoint_edits,
            PRESURVEY_FILE: self.presurvey,
            RATINGS_FILE: self.ratings,
            PAIRWISE_FILE: self.pairwise,
            ALT_EXPOSURE_FILE: self.alt_exposure,
            INTEGRITY_FILE: self.integrity,
            EVENTS_FILE: self.events,
            PROVENANCE_FILE: self.provenance,
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


def _latency_ms(events: Sequence[tables.Event], screen: str) -> int | None:
    """§2.11 — `--latency`에서만. 파생 변수를 **런타임에** 계산하지 않는 규율의 예외 자리다."""
    for start_type, end_type in LATENCY_PAIRS:
        start = next(
            (
                event
                for event in events
                if event.type == start_type and (event.payload or {}).get("screen") == screen
            ),
            None,
        )
        end = next(
            (
                event
                for event in events
                if event.type == end_type and (event.payload or {}).get("screen") == screen
            ),
            None,
        )
        if start and end and start.server_ts and end.server_ts:
            return int((end.server_ts - start.server_ts).total_seconds() * 1000)
    return None


async def collect(
    db: AsyncSession, *, actor: str, include_text: bool = False, latency: bool = False
) -> ExportTables:
    """DB → export 표. 파일 쓰기는 하지 않는다(호출부가 결정한다)."""
    sessions = list((await db.execute(select(tables.Session))).scalars().all())
    participants = {
        row.participant_no: row
        for row in (await db.execute(select(tables.Participant))).scalars().all()
    }
    focal_item_scope = {item.item_id: item for item in rating_items.load().items}
    # 사전설문은 위치가 아니라 문항 ID로 저장된다 — section·reverse는 자산에서 붙인다.
    presurvey_by_id = {item.item_id: item for item in presurvey.load().items}

    trajectory: list[dict[str, Any]] = []
    edit_rows: list[dict[str, Any]] = []
    presurvey_rows: list[dict[str, Any]] = []
    ratings_rows: list[dict[str, Any]] = []
    pairwise_rows: list[dict[str, Any]] = []
    alt_rows: list[dict[str, Any]] = []
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
                    "field": "abort_reason",
                    "text": _decrypt(session.abort_reason),
                }
            )

        # --- events ---
        events = list(
            (
                await db.execute(
                    select(tables.Event)
                    .where(tables.Event.session_id == session.id)
                    .order_by(tables.Event.server_ts)
                )
            )
            .scalars()
            .all()
        )
        flag_count = sum(1 for event in events if event.type == "researcher_flag")
        for event in events:
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
                    # §2.11 — 파생 지표는 계산하지 않는다. 쌍만 남긴다(NT-29).
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
                        "field": f"{event.type}.reason",
                        "text": fernet.decrypt(event.payload[REASON_FIELD].encode("ascii")),
                    }
                )

        # --- checkpoint 수정 (§3.4 · §7.7 사후 코딩 입력) ---
        edits = list(
            (
                await db.execute(
                    select(tables.CheckpointEdit)
                    .where(tables.CheckpointEdit.session_id == session.id)
                    .order_by(tables.CheckpointEdit.edited_at)
                )
            )
            .scalars()
            .all()
        )
        for index, edit in enumerate(edits, start=1):
            original, edited = _decrypt(edit.original), _decrypt(edit.edited)
            edit_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "seq": index,
                    "segment": edit.segment,
                    # 자극 전제가 흔들릴 수 있는 segment인가 — R2 경보와 같은 판정(§3.4).
                    "alert_segment": edit.segment in dossier_loader.ALERT_SEGMENTS,
                    "original_chars": _length(original),
                    "edited_chars": _length(edited),
                    "edited_at": _iso(edit.edited_at),
                }
            )
            if include_text:
                for field, text in (("original", original), ("edited", edited)):
                    if text:
                        free_text.append(
                            {
                                "participant_no": session.participant_no,
                                "session_id": session_key,
                                "field": f"checkpoint_edit[{index}].{edit.segment}.{field}",
                                "text": text,
                            }
                        )

        # --- 대안 노출 (§4.9) ---
        alt_exposures = list(
            (
                await db.execute(
                    select(tables.AltExposure)
                    .where(tables.AltExposure.session_id == session.id)
                    .order_by(tables.AltExposure.position)
                )
            )
            .scalars()
            .all()
        )
        for row in alt_exposures:
            alt_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "position": row.position,
                    "condition": row.condition,
                    "stimulus_hash": row.stimulus_hash or "",
                    "rendered_at": _iso(row.rendered_at),
                    "advanced_at": _iso(row.advanced_at),
                }
            )

        # --- pairwise (§4.10 · §7.5 — focal-status sensitivity) ---
        for view in (
            (
                await db.execute(
                    select(tables.PairwiseView)
                    .where(tables.PairwiseView.session_id == session.id)
                    .order_by(tables.PairwiseView.position)
                )
            )
            .scalars()
            .all()
        ):
            responses = list(
                (
                    await db.execute(
                        select(tables.PairwiseResponse)
                        .where(tables.PairwiseResponse.pairwise_view_id == view.id)
                        .order_by(tables.PairwiseResponse.display_order)
                    )
                )
                .scalars()
                .all()
            )
            values = {row.item_id: row.value for row in responses}
            pairwise_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "position": view.position,
                    "contrast": view.contrast,
                    "left_condition": view.left_condition,
                    "right_condition": view.right_condition,
                    # 초안 §7.12 sensitivity의 입력이다.
                    "focal_included": view.focal_included,
                    "focal_side": view.focal_side or "",
                    "submitted_at": _iso(view.submitted_at),
                    **{
                        f"item_{item.item_id}": values.get(item.item_id, "")
                        for item in pairwise_items.load().items_for(view.contrast)
                    },
                }
            )

        # --- 사전설문 (v1.0.1 §4.2 · D-44) ---
        # 응답이 범주 코드·정수라 자유 텍스트가 아니다 — 기본 출력에 그대로 실린다.
        # 역채점은 **적용하지 않는다**: 자산의 `reverse`는 분석 시점의 정보이고, export가
        # 미리 뒤집으면 원자료가 사라진다(§7.1 합산 금지와 같은 태도).
        for response in (
            (
                await db.execute(
                    select(tables.PresurveyResponse)
                    .where(tables.PresurveyResponse.session_id == session.id)
                    .order_by(tables.PresurveyResponse.display_order)
                )
            )
            .scalars()
            .all()
        ):
            item = presurvey_by_id.get(response.item_id)
            presurvey_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "item_id": response.item_id,
                    "section": item.section if item else "",
                    "type": item.type if item else "",
                    "reverse": item.reverse if item else "",
                    # 복수 선택은 리스트다 — CSV 한 칸에 담기게 직렬화한다.
                    "value": (
                        json.dumps(response.value, ensure_ascii=False)
                        if isinstance(response.value, list)
                        else response.value
                    ),
                    "display_order": response.display_order,
                }
            )

        # --- focal 평정 (§4.8) ---
        session_ratings = list(
            (
                await db.execute(
                    select(tables.Rating)
                    .where(tables.Rating.session_id == session.id)
                    .order_by(tables.Rating.display_order)
                )
            )
            .scalars()
            .all()
        )
        for rating in session_ratings:
            ratings_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "scope": rating.scope,
                    "construct": rating.construct,
                    "item_id": rating.item_id,
                    "value": rating.value,
                    "display_order": rating.display_order,
                }
            )
        rating_values = {row.item_id: row.value for row in session_ratings}

        # --- focal trajectory — **참가자 1행**(D-23) ---
        run = (
            await db.execute(
                select(tables.FocalRun).where(tables.FocalRun.session_id == session.id)
            )
        ).scalars().one_or_none()

        turns: dict[str, tables.Turn] = {}
        sidecar = None
        action = None
        generations: list[tables.Generation] = []
        if run is not None:
            turns = {
                turn.role: turn
                for turn in (
                    await db.execute(
                        select(tables.Turn).where(tables.Turn.focal_run_id == run.id)
                    )
                )
                .scalars()
                .all()
            }
            sidecar = (
                await db.execute(
                    select(tables.SidecarEntry).where(
                        tables.SidecarEntry.focal_run_id == run.id
                    )
                )
            ).scalars().one_or_none()
            action = (
                await db.execute(
                    select(tables.DownstreamAction).where(
                        tables.DownstreamAction.focal_run_id == run.id
                    )
                )
            ).scalars().one_or_none()
            generations = list(
                (
                    await db.execute(
                        select(tables.Generation)
                        .where(tables.Generation.focal_run_id == run.id)
                        .order_by(tables.Generation.attempt)
                    )
                )
                .scalars()
                .all()
            )

        final = next((row for row in generations if row.final), None)
        user1_text = _decrypt(turns["user1"].text) if "user1" in turns else None
        user2_text = _decrypt(turns["user2"].text) if "user2" in turns else None
        ai2_text = _decrypt(turns["ai2"].text) if "ai2" in turns else None

        row: dict[str, Any] = {
            "participant_no": session.participant_no,
            "session_id": session_key,
            "is_test": bool(participant.is_test) if participant else "",
            # §5.2 배정 — 분석의 between 요인이다.
            "focal_condition": (run.condition if run else "") or "",
            "alt_order": json.dumps(participant.alt_order or [], ensure_ascii=False)
            if participant
            else "",
            "pair_order": json.dumps(participant.pair_order or [], ensure_ascii=False)
            if participant
            else "",
            "assignment_version": (participant.assignment_version or "") if participant else "",
            # §1.5-4 — descriptor 전용. 조건·분기의 입력이 아니다.
            "a_level": dossier.evidence_code.a_level,
            "mismatch_locus": dossier.evidence_code.mismatch_locus,
            "dossier_version": dossier.version,
            "dossier_locked": dossier.is_locked,
            "stimulus_hash": (run.stimulus_hash if run else "") or "",
            # §3.4 — checkpoint 수정 (AI1·stimulus_hash는 불변이다).
            "checkpoint_edited": bool(run.checkpoint_edited) if run else "",
            "edited_segments": json.dumps(
                (run.edited_segments or []) if run else [], ensure_ascii=False
            ),
            "edit_count": len(edits),
            "user1_chars": _length(user1_text),
            "sidecar_has_more": bool(sidecar.has_more) if sidecar else "",
            "sidecar_provenance": (sidecar.provenance or "") if sidecar else "",
            "sidecar_text_chars": _length(_decrypt(sidecar.free_text)) if sidecar else "",
            "sidecar_reason_chars": _length(_decrypt(sidecar.reason_text)) if sidecar else "",
            "ai2_chars": _length(ai2_text),
            "fallback_used": bool(final.fallback_used) if final else "",
            "regenerated": (final.attempt > 1) if final else "",
            "checker_skipped": any(row.checker_skipped for row in generations)
            if generations
            else "",
            "alt_overlap": json.dumps(
                [item for row in generations for item in (row.alt_overlap or [])],
                ensure_ascii=False,
            ),
            "violations": json.dumps(
                [item for row in generations for item in (row.rule_violations or [])],
                ensure_ascii=False,
            ),
            # §7.4 downstream
            "downstream_disposition": (action.disposition if action else "") or "",
            "downstream_end_type": (action.end_type or "") if action else "",
            "end_reason_chars": _length(_decrypt(action.reason_text)) if action else "",
            "user2_chars": _length(user2_text),
            "focal_started_at": _iso(run.started_at) if run else "",
            "focal_completed_at": _iso(run.completed_at) if run else "",
            "session_status": session.status,
            "session_ss_state": session.ss_state,
            "flag_count": flag_count,
            **{
                f"rating_{item_id}": rating_values.get(item_id, "")
                for item_id in focal_item_scope
            },
        }
        if latency:
            # §2.11 — 기본 미산출. 옵션을 준 실행에서만 열이 생긴다.
            for screen in ("P4", "P6", "P7"):
                row[f"latency_{screen}_ms"] = _latency_ms(events, screen) or ""
        trajectory.append(row)

        for generation in generations:
            integrity_rows.append(
                {
                    "participant_no": session.participant_no,
                    "session_id": session_key,
                    "condition": (run.condition if run else "") or "",
                    "attempt": generation.attempt,
                    "final": generation.final,
                    "fallback_used": generation.fallback_used,
                    "checker_skipped": generation.checker_skipped,
                    # §7.7 — AI2 행동 코딩의 **기계 열**. 내용 코딩은 사람이 한다.
                    "output_chars": _length(_decrypt(generation.output_text)),
                    "output_questions": _questions(_decrypt(generation.output_text)),
                    "rule_violations": json.dumps(
                        generation.rule_violations or [], ensure_ascii=False
                    ),
                    "alt_overlap": json.dumps(generation.alt_overlap or [], ensure_ascii=False),
                    "checker_result": json.dumps(
                        generation.checker_result or {}, ensure_ascii=False
                    ),
                    "created_at": _iso(generation.created_at),
                }
            )

        if include_text:
            for field, text in (
                ("user1", user1_text),
                ("ai2_final_text", ai2_text),
                ("user2", user2_text),
                ("sidecar_text", _decrypt(sidecar.free_text) if sidecar else None),
                ("sidecar_reason", _decrypt(sidecar.reason_text) if sidecar else None),
                ("end_reason", _decrypt(action.reason_text) if action else None),
            ):
                if text:
                    free_text.append(
                        {
                            "participant_no": session.participant_no,
                            "session_id": session_key,
                            "field": field,
                            "text": text,
                        }
                    )

    # §2.9 — export·복호화 각 1행. 실행 단위로 남긴다(행 단위로 남기면 이력이 잡음이 된다).
    await record(
        db, actor=actor, action=AuditAction.EXPORT, target=f"trajectory:{len(trajectory)}행"
    )
    await record(
        db,
        actor=actor,
        action=AuditAction.DECRYPT,
        target=f"export:{'text' if include_text else 'lengths'}",
    )
    return ExportTables(
        trajectory=trajectory,
        checkpoint_edits=edit_rows,
        presurvey=presurvey_rows,
        ratings=ratings_rows,
        pairwise=pairwise_rows,
        alt_exposure=alt_rows,
        integrity=integrity_rows,
        events=event_rows,
        provenance=provenance_table(),
        free_text=free_text,
    )


def _questions(text: str | None) -> int | None:
    if text is None:
        return None
    from app.core.text_metrics import count_questions

    return count_questions(text)


def provenance_table() -> list[dict[str, Any]]:
    """§7.7 — dossier의 provenance 구성비 (초안 §7.3 hierarchy, 논문 보고용).

    DB가 아니라 **자산**에서 산출한다. 세션이 없어도 나오는 표이고, 사건별 재구성 충실도의
    기술통계다.
    """
    rows: list[dict[str, Any]] = []
    for participant_no, dossier in sorted(dossier_loader.load_all().items()):
        counts = {value: 0 for value in sorted(dossier_loader.PROVENANCE_VALUES)}
        for value in dossier.ai_visible.provenance.values():
            if value in counts:
                counts[value] += 1
        total = sum(counts.values()) or 1
        rows.append(
            {
                "participant_no": participant_no,
                "dossier_version": dossier.version,
                "is_dummy": dossier.is_dummy,
                "locked": dossier.is_locked,
                **counts,
                **{f"{key}_ratio": round(value / total, 3) for key, value in counts.items()},
            }
        )
    return rows


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """빈 표도 파일로 남긴다 — 파일이 없는 것과 데이터가 없는 것은 다르다.

    열 목록은 **전 행의 합집합**이다(첫 행이 아니라). `pairwise.csv`가 그 이유다: 문항이
    contrast마다 다르므로(`item_seq_*` / `item_sco_*` / `item_sto_*`) 행마다 열이 다르다.
    첫 행 기준으로 잡으면 다른 contrast의 응답이 통째로 사라지거나 쓰기가 터진다.

    순서는 **최초 등장 순**이라 사람이 읽는 열 순서(참가자 → 배정 → 측정)가 유지된다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        # 빠진 열은 빈 칸이다 — 그 contrast에 없는 문항이라는 뜻이고, 0이 아니다.
        writer = csv.DictWriter(handle, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="focal trajectory export (§7.7 · NT-30)")
    parser.add_argument("--actor", required=True, help="실행자 — audit_logs에 남는다 (§2.9)")
    parser.add_argument("--out", type=Path, default=Path("exports"), help="출력 디렉터리")
    parser.add_argument(
        "--include-text",
        action="store_true",
        help=f"자유 텍스트를 {FREE_TEXT_FILE}로 함께 내보낸다 (기본: 내보내지 않음)",
    )
    parser.add_argument(
        "--latency",
        action="store_true",
        help="§2.11 — beacon 쌍에서 response latency를 계산한다 (기본: 미산출)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_engine(settings.resolved_database_url, settings.db_schema)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        exported = await collect(
            db, actor=args.actor, include_text=args.include_text, latency=args.latency
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
