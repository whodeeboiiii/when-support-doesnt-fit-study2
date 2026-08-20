"""연구자 콘솔 읽기 뷰 — R2 모니터 · R3 review · R4 dossier (구현명세서 §4.12 · §8.2 · §2.9).

세 뷰가 공유하는 규율이 이 파일의 전부다.

1. **복호화는 여기가 §2.9의 "① 콘솔 표시" 지점**이다. 복호화한 요청은 예외 없이
   `audit_logs`에 `decrypt` 1행을 남긴다(NT-28). 값 단위가 아니라 **요청 단위**로 남긴다 —
   한 화면이 40개 필드를 복호화한다고 audit을 40행 늘리면 접근 이력이 잡음이 된다.
2. **조회도 audit 대상**이다(§2.7 "모든 콘솔 조회"). R4는 dossier 열람이라 `view` 1행이
   반드시 남는다.
3. **researcher_only는 R3·R4에서만** 나온다. 그 층은 `assets.dossier_private`로만 읽고,
   이 모듈은 `llm/` 어디에서도 import되지 않는다(§1.2 · NT-04).

R3가 P10과 "같은 4열"인데도 `state_payload._cross_review`를 재사용하지 않는 이유: 참가자
화면은 sidecar를 **빼야** 하고(PH-02) 연구자 화면은 **넣어야** 한다(§4.12). 같은 함수에
플래그를 달면 언젠가 참가자 쪽에서 True로 불린다.
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
from app.assets import dossier_loader, rating_items, screen_copy
from app.assets.dossier_private import load_researcher_only
from app.assets.files import PARTICIPANT_NUMBERS
from app.core.state_machine import BState, SsState, has_ai2, screen_for
from app.core.williams import sequence
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


def ai2_state(branch: tables.Branch, generations: list[tables.Generation]) -> str | None:
    """§4.12 "AI2 파이프라인 상태(생성 중/재생성/fallback)".

    상태를 따로 저장하지 않고 `generations`에서 읽는다 — 표시용 상태 컬럼을 만들면 그 값이
    audit(§8.4)과 어긋날 수 있고, 재구성의 정본은 언제나 generations다(NT-15).
    """
    if not has_ai2(branch.user1_disposition):
        return None
    final = next((row for row in generations if row.final), None)
    if final is None:
        return "generating" if BState(branch.b_state) is BState.AI2 else "pending"
    if final.fallback_used:
        return "fallback"
    return "regenerated" if final.attempt > 1 else "clean"


async def _generations(db: DbSession, branch_id: uuid.UUID) -> list[tables.Generation]:
    result = await db.execute(
        select(tables.Generation)
        .where(tables.Generation.branch_id == branch_id)
        .order_by(tables.Generation.attempt, tables.Generation.created_at)
    )
    return list(result.scalars().all())


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
        "branch_id": str(event.branch_id) if event.branch_id else None,
        "payload": payload or None,
        "client_ts": _iso(event.client_ts),
        "server_ts": _iso(event.server_ts),
    }


# --------------------------------------------------------------------------- #
# R2 라이브 모니터 (§4.12 · §8.2 `GET /monitor/{id}`)
# --------------------------------------------------------------------------- #


@router.get("/monitor/{session_id}")
async def monitor(session_id: uuid.UUID, actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """현재 SS·B 상태 + transcript + 이벤트 스트림 + AI2 파이프라인 상태.

    3s 폴링으로 호출되므로(§2.7) 매 호출이 audit 2행(view·decrypt)을 남긴다. 감사 기록이
    빠르게 늘지만, "언제부터 언제까지 이 세션을 보고 있었는가"가 그대로 남는 편이 낫다.
    """
    session = await get_session_or_404(db, session_id)
    branches = await store.branches_of(db, session.id)

    branch_rows: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    for branch in branches:
        generations = await _generations(db, branch.id)
        branch_rows.append(
            {
                "index": branch.branch_index,
                # 조건 라벨은 연구자 화면 전용이다(§4.10).
                "condition": branch.condition,
                "b_state": branch.b_state,
                "disposition": branch.user1_disposition,
                "started_at": _iso(branch.started_at),
                "completed_at": _iso(branch.completed_at),
                "ai2_state": ai2_state(branch, generations),
                "attempts": len(generations),
                "checker_skipped": any(row.checker_skipped for row in generations),
                "rule_violations": [
                    violation for row in generations for violation in (row.rule_violations or [])
                ],
            }
        )
        for role in ("ai1", "user1", "ai2"):
            turn = await store.turn(db, branch.id, role)
            if turn is None:
                continue
            transcript.append(
                {
                    "branch_index": branch.branch_index,
                    "role": role,
                    "text": _decrypt(turn.text),
                    "at": _iso(turn.submitted_at or turn.rendered_at),
                }
            )

    b_state = None
    if SsState(session.ss_state) is SsState.BRANCH_BLOCK and session.branch_index is not None:
        current = await store.branch_by_index(db, session.id, session.branch_index)
        b_state = BState(current.b_state) if current is not None else None

    await record(db, actor=actor, action=AuditAction.VIEW, target=f"session:{session.id}")
    await _audit_decrypt(db, actor, f"session:{session.id}:transcript")
    return {
        "session": {
            "session_id": str(session.id),
            "participant_no": session.participant_no,
            "ss_state": session.ss_state,
            "b_state": b_state.value if b_state is not None else None,
            "screen": screen_for(SsState(session.ss_state), b_state),
            "branch_index": session.branch_index,
            "status": session.status,
            "joined_at": _iso(session.joined_at),
        },
        "branches": branch_rows,
        "transcript": transcript,
        "events": [_event_row(event) for event in await _events(db, session.id)],
    }


# --------------------------------------------------------------------------- #
# R3 review 뷰 (§4.12 · §8.2 `GET /review/{id}`) — 인터뷰 참조용
# --------------------------------------------------------------------------- #


@router.get("/review/{session_id}")
async def review(session_id: uuid.UUID, actor: AdminActor, db: DbSession) -> dict[str, Any]:
    """P10과 같은 4열 + sidecar · 평정 · flag · researcher_only 요약.

    참가자 화면(P10)과 다른 점 둘: sidecar가 **보이고**(§4.12 — 연구자는 R3에서 열람),
    조건 라벨이 붙는다. 이 뷰는 cross-branch interview(부록 D.3) 중 연구자만 본다.
    """
    session = await get_session_or_404(db, session_id)
    dossier = dossier_loader.load(session.participant_no)
    labels = {option.code: option.label for option in screen_copy.DOWNSTREAM_OPTIONS}
    item_text = {item.item_id: item.text for item in rating_items.RATING_ITEMS}

    trajectories: list[dict[str, Any]] = []
    for branch in await store.branches_of(db, session.id):
        user1 = await store.turn(db, branch.id, "user1")
        ai2 = await store.turn(db, branch.id, "ai2")
        action = await store.downstream(db, branch.id)
        entry = await store.sidecar(db, branch.id)
        generations = await _generations(db, branch.id)
        trajectories.append(
            {
                "index": branch.branch_index,
                "condition": branch.condition,
                "ai1": dossier.stimulus(branch.condition) if branch.condition else None,
                "user1": _decrypt(user1.text) if user1 else None,
                "user1_normalized": _decrypt(user1.text_normalized) if user1 else None,
                "disposition": branch.user1_disposition,
                "ai2": _decrypt(ai2.text) if ai2 else None,
                "ai2_state": ai2_state(branch, generations),
                "downstream": labels.get(action.code) if action else None,
                "downstream_code": action.code if action else None,
                "sidecar": (
                    {
                        "choice": entry.choice,
                        "free_text": _decrypt(entry.free_text),
                        "relevance_1_7": entry.relevance_1_7,
                        "reason_text": _decrypt(entry.reason_text),
                    }
                    if entry
                    else None
                ),
                "ratings": [
                    {
                        "item_id": row.item_id,
                        "text": item_text.get(row.item_id, ""),
                        "value": row.value,
                        "block": row.block,
                        "display_order": row.display_order,
                    }
                    for row in await store.ratings(db, branch.id)
                ],
            }
        )

    flags = [
        _event_row(event)
        for event in await _events(db, session.id)
        if event.type.startswith("researcher_")
    ]

    await record(db, actor=actor, action=AuditAction.VIEW, target=f"session:{session.id}:review")
    await _audit_decrypt(db, actor, f"session:{session.id}:review")
    return {
        "session": {
            "session_id": str(session.id),
            "participant_no": session.participant_no,
            "ss_state": session.ss_state,
            "status": session.status,
        },
        "branches": trajectories,
        "flags": flags,
        # §4.12 — 인터뷰 참조용 요약. 이 값이 LLM 경로에 닿는 코드 경로는 없다(§1.2 · NT-04).
        "researcher_only": load_researcher_only(session.participant_no),
        "interview_note": screen_copy.CROSS_REVIEW_END_BUTTON,
    }


# --------------------------------------------------------------------------- #
# R4 dossier·자극 뷰어 (§4.12 · §8.2 `GET /dossier/{pno}`) — 읽기 전용
# --------------------------------------------------------------------------- #


@router.get("/dossier/{participant_no}")
async def dossier_view(
    participant_no: str, actor: AdminActor, db: DbSession
) -> dict[str, Any]:
    """3층 · AI1 4종 · fallback · referent_map + hash·lock 시각 (§4.12 · §5.2).

    **읽기 전용**이다. 콘솔에서 dossier를 고치는 경로는 만들지 않는다 — 자산 수정은 파일과
    2인 판정·lock 절차(§5.2 · 부록 D.2)를 지나야 한다.
    """
    participant_no = participant_no.strip().upper()
    if participant_no not in PARTICIPANT_NUMBERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"알 수 없는 참가자 번호: {participant_no}")

    dossier = dossier_loader.load(participant_no)
    derivation = dossier.derivation
    await record(db, actor=actor, action=AuditAction.VIEW, target=f"dossier:{participant_no}")
    return {
        "participant_no": participant_no,
        "version": dossier.version,
        "locked": dossier.is_locked,
        "locked_at": dossier.locked_at,
        "locked_hash": dossier.locked_hash,
        "content_hash": dossier.content_hash,
        "dummy": dossier.is_dummy,
        "sequence": list(sequence(participant_no)),
        "sampling": {
            "actionability": dossier.sampling.actionability,
            "mismatch_locus": dossier.sampling.mismatch_locus,
            "notes_ref": dossier.sampling.notes_ref,
        },
        "ai_visible": dossier.ai_visible.as_dict(),
        "derivation": {
            "warranted_uptake": derivation.warranted_uptake,
            "prohibited_inference": list(derivation.prohibited_inference),
            "residual_uncertainty": {
                "text": derivation.residual_uncertainty.text,
                "question_stem": derivation.residual_uncertainty.question_stem,
            },
            "focal_repair_relevant_content": derivation.focal_repair_relevant_content,
            "neutral_fallback": derivation.neutral_fallback,
            "referent_map": [
                {"patterns": list(entry.patterns), "proposition": entry.proposition}
                for entry in derivation.referent_map
            ],
        },
        "stimuli": [
            {
                "condition": condition,
                "text": derivation.stimuli[condition],
                "meta": derivation.stimuli_meta[condition].as_dict(),
                "hash": dossier.stimulus_hash(condition),
            }
            for condition in dossier_loader.CONDITIONS
        ],
        "researcher_only": load_researcher_only(participant_no),
    }
