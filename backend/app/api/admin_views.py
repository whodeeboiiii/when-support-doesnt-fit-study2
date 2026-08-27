"""연구자 콘솔 읽기 뷰 — R2 모니터 · R3 contrastive · R4 dossier (§4.13 · §8.2 · §2.9).

세 뷰가 공유하는 규율이 이 파일의 전부다.

1. **복호화는 여기가 §2.9의 "콘솔" 지점**이다. 복호화한 요청은 예외 없이 `audit_logs`에
   `decrypt` 1행을 남긴다(NT-28). 값 단위가 아니라 **요청 단위**로 남긴다 — 한 화면이 40개
   필드를 복호화한다고 audit을 40행 늘리면 접근 이력이 잡음이 된다.
2. **조회도 audit 대상**이다(§2.7 "모든 콘솔 조회"). R4는 dossier 열람이라 `view` 1행이
   반드시 남는다.
3. **researcher_only·조건 라벨·sidecar는 R2–R4에서만** 나온다(NT-39). researcher_only는
   `assets.dossier_private`로만 읽고, 이 모듈은 `llm/` 어디에서도 import되지 않는다(NT-04).

**v2의 새 항목 둘**(§2.7·§4.13):
- R2에 **checkpoint 수정 diff + 경보**. `trouble_cue`·`problematic_ai_response`가 수정되면
  붉은 경보를 띄운다 — 자극의 전제가 흔들렸을 수 있고, 연구자가 Zoom에서 구두 확인해야
  한다(§3.4 · 부록 D.3). 시스템은 막지 않는다.
- R3가 **contrastive interview 뷰**로 개편됐다: focal trajectory + 평정 + 대안 노출 순서 +
  세 pair(좌우·조건 라벨·focal 포함 여부·응답값) + researcher_only + flag.

R3가 P11과 비슷해 보여도 `state_payload`를 재사용하지 않는다: 참가자 화면은 sidecar·조건
라벨을 **빼야** 하고 연구자 화면은 **넣어야** 한다(NT-39). 같은 함수에 플래그를 달면 언젠가
참가자 쪽에서 True로 불린다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api import store
from app.api.admin import get_session_or_404
from app.api.deps import AdminActor, DbSession
from app.assets import dossier_loader, pairwise_items, rating_items
from app.assets.dossier_private import load_researcher_only
from app.assets.files import is_participant_no
from app.assets.screen_copy import END_TYPE_OPTIONS
from app.core import assignment
from app.core.state_machine import FState, SsState, screen_for
from app.models import tables
from app.security import fernet
from app.security.audit import AuditAction, record

router = APIRouter(prefix="/admin", tags=["researcher"])

#: R2 이벤트 스트림에 싣는 최근 이벤트 수. 라이브 모니터는 3s 폴링이라 창을 짧게 잡는다(§2.7).
EVENT_WINDOW = 60

#: §8.1 `events.payload`의 flag 사유 필드 (암호문).
REASON_FIELD = "reason_encrypted"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _decrypt(value: bytes | None) -> str | None:
    return fernet.decrypt(value) if value else None


async def _audit_decrypt(db: DbSession, actor: str, target: str) -> None:
    """§2.9 — 복호화 조회 1건. 값은 남기지 않는다(누가 무엇을 열었는가만)."""
    await record(db, actor=actor, action=AuditAction.DECRYPT, target=target)


def ai2_state(
    session: tables.Session, generations: list[tables.Generation]
) -> str | None:
    """§4.13 "AI2 파이프라인 상태(생성 중/재생성/fallback)".

    상태를 따로 저장하지 않고 `generations`에서 읽는다 — 표시용 상태 컬럼을 만들면 그 값이
    audit(§8.4)과 어긋날 수 있고, 재구성의 정본은 언제나 generations다(NT-15).
    """
    final = next((row for row in generations if row.final), None)
    if final is None:
        return "generating" if session.f_state == FState.AI2.value else "pending"
    if final.fallback_used:
        return "fallback"
    return "regenerated" if final.attempt > 1 else "clean"


async def _events(db: DbSession, session_id: uuid.UUID) -> list[tables.Event]:
    result = await db.execute(
        select(tables.Event)
        .where(tables.Event.session_id == session_id)
        .order_by(tables.Event.server_ts.desc())
        .limit(EVENT_WINDOW)
    )
    return list(reversed(result.scalars().all()))


def _event_row(event: tables.Event) -> dict[str, Any]:
    """flag 사유는 여기서 평문이 된다(§2.9 콘솔 표시 지점)."""
    payload = dict(event.payload or {})
    encrypted = payload.pop(REASON_FIELD, None)
    if encrypted:
        payload["reason"] = fernet.decrypt(encrypted.encode("ascii"))
    return {
        "type": event.type,
        "payload": payload or None,
        "client_ts": _iso(event.client_ts),
        "server_ts": _iso(event.server_ts),
    }


async def _checkpoint_diff(db: DbSession, session_id: uuid.UUID) -> dict[str, Any]:
    """§2.7·§4.2 — segment별 원문/수정본 diff + 경보 (v2 신설).

    경보는 `trouble_cue`·`problematic_ai_response` 수정에 붙는다(§3.4). 그 둘이 AI1의
    전제이기 때문이다 — 다른 segment 수정은 사실 정정으로 흡수된다.
    """
    rows = await store.checkpoint_edits(db, session_id)
    edits = [
        {
            "segment": row.segment,
            "original": _decrypt(row.original),
            "edited": _decrypt(row.edited),
            "edited_at": _iso(row.edited_at),
            # 붉은 경보 — 연구자가 Zoom에서 구두 확인해야 하는 행(부록 D.3).
            "alert": row.segment in dossier_loader.ALERT_SEGMENTS,
        }
        for row in rows
    ]
    return {
        "edits": edits,
        "edited_segments": sorted({row.segment for row in rows}),
        "alert": any(entry["alert"] for entry in edits),
    }


# --------------------------------------------------------------------------- #
# R2 라이브 모니터 (§4.13 · §8.2 `GET /monitor/{id}`)
# --------------------------------------------------------------------------- #


@router.get("/monitor/{session_id}")
async def monitor(session_id: uuid.UUID, actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """SS·F·alt_index·pair_index·화면 + transcript + **수정 diff·경보** + AI2 상태 + 이벤트.

    3s 폴링으로 호출되므로(§2.7) 매 호출이 audit 2행(view·decrypt)을 남긴다. 감사 기록이
    빠르게 늘지만, "언제부터 언제까지 이 세션을 보고 있었는가"가 그대로 남는 편이 낫다.
    """
    session = await get_session_or_404(db, session_id)
    participant = await db.get(tables.Participant, session.participant_no)
    run = await store.focal_run(db, session.id)

    transcript: list[dict[str, Any]] = []
    focal: dict[str, Any] | None = None
    if run is not None:
        generations = await store.generations(db, run.id)
        focal = {
            # 조건 라벨은 연구자 화면 전용이다(§1.2).
            "condition": run.condition,
            "stimulus_hash": run.stimulus_hash,
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
            "checkpoint_edited": run.checkpoint_edited,
            "edited_segments": run.edited_segments,
            "ai2_state": ai2_state(session, generations),
            "attempts": len(generations),
            "checker_skipped": any(row.checker_skipped for row in generations),
            "rule_violations": [
                violation for row in generations for violation in (row.rule_violations or [])
            ],
            # §6.4 R-2 — **위반이 아니라 기록**이다. 화면에서도 그렇게 보여야 한다.
            "alt_overlap": [
                overlap for row in generations for overlap in (row.alt_overlap or [])
            ],
        }
        for turn in await store.turns(db, run.id):
            transcript.append(
                {
                    "role": turn.role,
                    "text": _decrypt(turn.text),
                    "at": _iso(turn.submitted_at or turn.rendered_at),
                }
            )

    f_state = FState(session.f_state) if session.f_state else None
    ss_state = SsState(session.ss_state)

    await record(db, actor=actor, action=AuditAction.VIEW, target=f"session:{session.id}")
    await _audit_decrypt(db, actor, f"session:{session.id}:transcript")
    return {
        "session": {
            "session_id": str(session.id),
            "participant_no": session.participant_no,
            "ss_state": session.ss_state,
            "f_state": session.f_state,
            "alt_index": session.alt_index,
            "pair_index": session.pair_index,
            "screen": screen_for(ss_state, f_state if ss_state is SsState.FOCAL else None),
            "status": session.status,
            "joined_at": _iso(session.joined_at),
            "focal_condition": participant.focal_condition if participant else None,
        },
        "focal": focal,
        "transcript": transcript,
        "checkpoint": await _checkpoint_diff(db, session.id),
        "alt_exposures": [
            {
                "position": row.position,
                "condition": row.condition,
                "rendered_at": _iso(row.rendered_at),
                "advanced_at": _iso(row.advanced_at),
            }
            for row in await store.alt_exposures(db, session.id)
        ],
        "pairwise": [
            {
                "position": row.position,
                "contrast": row.contrast,
                "left": row.left_condition,
                "right": row.right_condition,
                "focal_included": row.focal_included,
                "focal_side": row.focal_side,
                "submitted_at": _iso(row.submitted_at),
            }
            for row in await store.pairwise_views(db, session.id)
        ],
        "events": [_event_row(event) for event in await _events(db, session.id)],
    }


# --------------------------------------------------------------------------- #
# R3 contrastive interview 뷰 (§4.13 · §8.2 `GET /review/{id}`)
# --------------------------------------------------------------------------- #


@router.get("/review/{session_id}")
async def review(session_id: uuid.UUID, actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """§4.13 R3 — 인터뷰 중 연구자가 보는 화면 (부록 D.3 가이드와 짝).

    ① focal trajectory(조건 라벨 포함) ② focal 평정·MC ③ 대안 노출 순서 ④ 세 pair
    ⑤ researcher_only ⑥ flag. 참가자 P11에는 이 중 **아무것도** 없다(NT-39).
    """
    session = await get_session_or_404(db, session_id)
    dossier = dossier_loader.load(session.participant_no)
    participant = await db.get(tables.Participant, session.participant_no)
    end_labels = {option.code: option.label for option in END_TYPE_OPTIONS}
    focal_items = {item.item_id: item for item in rating_items.load().items}

    # ① focal trajectory
    run = await store.focal_run(db, session.id)
    trajectory: dict[str, Any] | None = None
    if run is not None:
        entry = await store.sidecar(db, run.id)
        action = await store.downstream(db, run.id)
        generations = await store.generations(db, run.id)
        turns = {turn.role: turn for turn in await store.turns(db, run.id)}
        trajectory = {
            "condition": run.condition,
            "ai1": dossier.presented(run.condition) if run.condition else None,
            "user1": _decrypt(turns["user1"].text) if "user1" in turns else None,
            "sidecar": (
                {
                    "has_more": entry.has_more,
                    "free_text": _decrypt(entry.free_text),
                    "provenance": entry.provenance,
                    "reason_text": _decrypt(entry.reason_text),
                }
                if entry
                else None
            ),
            "ai2": _decrypt(turns["ai2"].text) if "ai2" in turns else None,
            "ai2_state": ai2_state(session, generations),
            "generation_path": [
                {
                    "attempt": row.attempt,
                    "rule_violations": row.rule_violations,
                    "checker_result": row.checker_result,
                    "checker_skipped": row.checker_skipped,
                    "alt_overlap": row.alt_overlap,
                    "fallback_used": row.fallback_used,
                    "final": row.final,
                }
                for row in generations
            ],
            "user2": _decrypt(turns["user2"].text) if "user2" in turns else None,
            "downstream": (
                {
                    "disposition": action.disposition,
                    "end_type": action.end_type,
                    "end_label": end_labels.get(action.end_type or ""),
                    "reason_text": _decrypt(action.reason_text),
                }
                if action
                else None
            ),
            "checkpoint_edited": run.checkpoint_edited,
        }

    # ④ 세 pair — 좌우·조건 라벨·focal 포함 여부·응답값
    pairs: list[dict[str, Any]] = []
    for view in await store.pairwise_views(db, session.id):
        presented = {
            entry.item.item_id: entry
            for entry in pairwise_items.presentation_order(
                view.contrast, view.left_condition, view.right_condition
            )
        }
        pairs.append(
            {
                "position": view.position,
                "contrast": view.contrast,
                "left": {
                    "condition": view.left_condition,
                    "ai1": dossier.presented(view.left_condition),
                },
                "right": {
                    "condition": view.right_condition,
                    "ai1": dossier.presented(view.right_condition),
                },
                "focal_included": view.focal_included,
                "focal_side": view.focal_side,
                "responses": [
                    {
                        "item_id": row.item_id,
                        "text": presented[row.item_id].text if row.item_id in presented else "",
                        "value": row.value,
                        "display_order": row.display_order,
                    }
                    for row in await store.pairwise_responses(db, view.id)
                ],
            }
        )

    await record(db, actor=actor, action=AuditAction.VIEW, target=f"session:{session.id}:review")
    await _audit_decrypt(db, actor, f"session:{session.id}:review")
    return {
        "session": {
            "session_id": str(session.id),
            "participant_no": session.participant_no,
            "ss_state": session.ss_state,
            "status": session.status,
            "focal_condition": participant.focal_condition if participant else None,
        },
        "trajectory": trajectory,
        "checkpoint": await _checkpoint_diff(db, session.id),
        # ② focal 평정·MC — construct 라벨을 붙여 보여 준다(합산은 하지 않는다 — §7.1).
        "ratings": [
            {
                "scope": row.scope,
                "construct": row.construct,
                "item_id": row.item_id,
                "text": focal_items[row.item_id].text if row.item_id in focal_items else "",
                "value": row.value,
                "display_order": row.display_order,
            }
            for row in await store.ratings(db, session.id)
        ],
        # ③ 대안 노출 순서
        "alt_exposures": [
            {
                "position": row.position,
                "condition": row.condition,
                "ai1": dossier.presented(row.condition),
                "rendered_at": _iso(row.rendered_at),
                "advanced_at": _iso(row.advanced_at),
            }
            for row in await store.alt_exposures(db, session.id)
        ],
        "pairs": pairs,
        # ⑤ 인터뷰 참조용 요약. 이 값이 LLM 경로에 닿는 코드 경로는 없다(§1.2 · NT-04).
        "researcher_only": load_researcher_only(session.participant_no),
        "evidence_code": dossier.evidence_code.as_dict(),
        # ⑥ flag 목록
        "flags": [
            _event_row(event)
            for event in await _events(db, session.id)
            if event.type.startswith("researcher_")
        ],
    }


# --------------------------------------------------------------------------- #
# R4 dossier·자극·배정 뷰어 (§4.13 · §8.2 `GET /dossier/{pno}`) — 읽기 전용
# --------------------------------------------------------------------------- #


@router.get("/dossier/{participant_no}")
async def dossier_view(participant_no: str, actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """3층 + evidence code + R/U/Q segment + **조립된 4자극** + stimuli_meta + fallback +
    provenance·QC + 배정표 행 (§4.13 · §5.3).

    **읽기 전용**이다. 콘솔에서 dossier를 고치는 경로는 만들지 않는다 — 자산 수정은 파일과
    2인 판정·lock 절차(§5.3 · 부록 D.2)를 지나야 한다.
    """
    participant_no = participant_no.strip().upper()
    if not is_participant_no(participant_no):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"알 수 없는 참가자 번호: {participant_no}")

    dossier = dossier_loader.load(participant_no)
    stimulus = dossier.stimulus
    table = assignment.load()

    await record(db, actor=actor, action=AuditAction.VIEW, target=f"dossier:{participant_no}")
    return {
        "participant_no": participant_no,
        "version": dossier.version,
        "locked": dossier.is_locked,
        "locked_at": dossier.locked_at,
        "locked_hash": dossier.locked_hash,
        "content_hash": dossier.content_hash,
        "dummy": dossier.is_dummy,
        "assignment": table.row(participant_no).as_dict() if table.has(participant_no) else None,
        "evidence_code": dossier.evidence_code.as_dict(),
        "ai_visible": dossier.ai_visible.as_dict(),
        # R/U/Q segment — 조립의 원재료(§5.4 D-35). 네 전문은 저장하지 않는다.
        "segments": {key: stimulus.segment(key) for key in dossier_loader.SEGMENT_KEYS},
        "stimuli": [
            {
                "condition": condition,
                "recipe": list(dossier_loader.STIMULUS_RECIPE[condition]),
                "text": dossier.assemble(condition),
                "presented": dossier.presented(condition),
                "meta": stimulus.stimuli_meta[condition].as_dict(),
                "hash": dossier.stimulus_hash(condition),
            }
            for condition in dossier_loader.CONDITIONS
        ],
        "neutral_fallback": stimulus.neutral_fallback,
        "qc": dict(stimulus.qc),
        "researcher_only": load_researcher_only(participant_no),
    }
