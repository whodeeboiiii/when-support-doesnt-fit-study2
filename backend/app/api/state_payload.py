"""`GET /state` 화면 payload 조립 (구현명세서 §8.2 · §3.5 · §4).

    GET /state → SS·B 상태 + 현재 화면에 필요한 데이터(자극·문항 순서 포함 — 서버 산출값 재사용)

규율 세 가지.

1. **현재 화면 것만 내려간다.** 네 branch의 자극을 미리 실어 보내지 않는다(NT-13 "자극 사전
   로드 0건"). P10(cross-branch review)만 예외이고, 그때는 이미 네 branch가 끝난 뒤다.
2. **조건 라벨은 내려가지 않는다.** payload 어디에도 C1–C4·uptake·elicitation이 없다
   (§4.10 construct label 비공개). branch 라벨은 번호뿐이고, 그 번호도 화면에 숫자로 쓰지
   않는다(§4.4) — 클라이언트가 어느 branch에 제출할지 알아야 해서 실려 있을 뿐이다.
3. **문항 ID는 내려가지 않는다.** 사전설문(§4.2 NT-05)도 평정(§7.3 변수명)도 위치로만 오간다.

P10에서 참가자 자신의 User1·AI2 텍스트를 복호화한다. §2.9의 "복호화 지점 2곳(콘솔·export)"은
**연구자 접근**의 통제 규칙이고, 여기서는 참가자가 자기 세션의 자기 발화를 다시 보는 것이라
audit 대상 접근이 아니다. §4.10이 네 trajectory 재표시를 요구하므로 이 경로는 필수다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api import store
from app.assets import dossier_loader, presurvey, rating_items, screen_copy
from app.core.state_machine import BState, Disposition, SsState, has_ai2, screen_for
from app.models import tables
from app.security import fernet


def _decrypt(value: bytes | None) -> str | None:
    return fernet.decrypt(value) if value else None


def checkpoint_view(dossier: dossier_loader.Dossier) -> dict[str, Any]:
    """§4.3 — 상황 요약 카드 + [원 요청] → [문제된 AI 응답] → [trouble cue].

    `ai_visible` 층만 나간다. `derivation`(자극·fallback·prohibited inference)과
    `researcher_only`는 참가자 화면에 존재하지 않는다(§1.2).
    """
    visible = dossier.ai_visible
    return {
        "situation_summary": visible.situation_summary,
        "turns": [
            {"role": "user", "text": visible.original_request},
            {"role": "ai", "text": visible.problematic_ai_response},
            {"role": "user", "text": visible.trouble_cue.text},
        ],
    }


def sidecar_question(disposition: Disposition | str | None) -> str:
    """§4.6 [정본] 2변형 — 서버가 고른다(분기 규칙을 클라이언트에 복제하지 않는다)."""
    if disposition == Disposition.REPLY:
        return screen_copy.SIDECAR_QUESTION_REPLY
    return screen_copy.SIDECAR_QUESTION_NO_REPLY


def ratings_view(session_id: object, branch_index: int, ai1_text: str) -> dict[str, Any]:
    """§4.9 — 블록 1(AI1 카드 앵커) → 블록 2. 블록 내 순서는 시드 고정(NT-08)."""
    presented = rating_items.presentation_order(session_id, branch_index)
    blocks = []
    for block, instruction, card in (
        (rating_items.BLOCK_ANCHOR, screen_copy.RATINGS_BLOCK1_INSTRUCTION, ai1_text),
        (rating_items.BLOCK_INTERACTION, screen_copy.RATINGS_BLOCK2_INSTRUCTION, None),
    ):
        blocks.append(
            {
                "block": block,
                "instruction": instruction,
                # 블록 1에만 해당 branch의 AI1 원문을 회색 카드로 재표시한다(§4.9).
                "ai1_card": card,
                "items": [
                    {"position": entry.position, "text": entry.item.text}
                    for entry in presented
                    if entry.block == block
                ],
            }
        )
    return {
        "blocks": blocks,
        "scale": {
            "min": rating_items.SCALE_MIN,
            "max": rating_items.SCALE_MAX,
            "min_label": screen_copy.RATINGS_SCALE_MIN_LABEL,
            "max_label": screen_copy.RATINGS_SCALE_MAX_LABEL,
        },
    }


async def _cross_review(
    db: AsyncSession, session: tables.Session, dossier: dossier_loader.Dossier
) -> list[dict[str, Any]]:
    """§4.10 — 네 trajectory(AI1 → User1 → [AI2] → downstream). sidecar는 제외(PH-02)."""
    labels = {option.code: option.label for option in screen_copy.DOWNSTREAM_OPTIONS}
    trajectories: list[dict[str, Any]] = []
    for branch in await store.branches_of(db, session.id):
        user1 = await store.turn(db, branch.id, "user1")
        ai2 = await store.turn(db, branch.id, "ai2")
        action = await store.downstream(db, branch.id)
        trajectories.append(
            {
                "index": branch.branch_index,
                "label": screen_copy.CROSS_REVIEW_BRANCH_LABEL.format(index=branch.branch_index),
                "ai1": dossier.stimulus(branch.condition) if branch.condition else None,
                "user1": _decrypt(user1.text) if user1 else None,
                "disposition": branch.user1_disposition,
                "ai2": _decrypt(ai2.text) if ai2 else None,
                "downstream": labels.get(action.code) if action else None,
            }
        )
    return trajectories


async def _screen_data(
    db: AsyncSession,
    session: tables.Session,
    screen: str,
    branch: tables.Branch | None,
) -> dict[str, Any]:
    dossier = dossier_loader.load(session.participant_no)

    if screen == "P1":
        return {
            "notice": screen_copy.CONSENT_TODO,
            "items": [
                {"field": item.field, "label": item.label} for item in screen_copy.CONSENT_ITEMS
            ],
        }
    if screen == "P2":
        return {"items": presurvey.load().participant_payload()}
    if screen == "P3":
        return {"intro": screen_copy.CHECKPOINT_INTRO, "checkpoint": checkpoint_view(dossier)}
    if screen == "P4":
        return {"notice": screen_copy.BRANCH_REENTRY}

    if branch is None:
        # SS04 밖의 화면들 — branch가 필요 없다.
        if screen == "P10":
            return {
                "branches": await _cross_review(db, session, dossier),
                "end_button": screen_copy.CROSS_REVIEW_END_BUTTON,
            }
        if screen == "P11":
            return {
                "notice": screen_copy.DEBRIEF_TODO,
                "button": screen_copy.DEBRIEF_CONFIRM_BUTTON,
            }
        if screen == "ABORTED":
            return {"message": screen_copy.SESSION_ABORTED}
        return {}

    ai1_text = dossier.stimulus(branch.condition) if branch.condition else None

    if screen == "P5":
        return {
            "checkpoint": checkpoint_view(dossier),
            "ai1": ai1_text,
            "buttons": {
                "send": screen_copy.SEND_BUTTON,
                "no_reply": screen_copy.NO_REPLY_BUTTON,
                "end": screen_copy.END_BUTTON,
            },
        }
    if screen == "P6":
        return {
            "transition": screen_copy.SIDECAR_TRANSITION,
            "question": sidecar_question(branch.user1_disposition),
            "choices": [
                {"value": value, "label": label} for value, label in screen_copy.SIDECAR_CHOICES
            ],
            "has_notice": screen_copy.SIDECAR_HAS_NOTICE,
            "relevance_question": screen_copy.SIDECAR_RELEVANCE_QUESTION,
            "relevance_min": screen_copy.SIDECAR_RELEVANCE_MIN,
            "relevance_max": screen_copy.SIDECAR_RELEVANCE_MAX,
            "reason_prompt": screen_copy.SIDECAR_REASON_PROMPT,
        }
    if screen == "P7":
        generation = await store.final_generation(db, branch.id)
        return {
            "loading": screen_copy.AI2_LOADING,
            "delayed": screen_copy.AI2_DELAYED,
            # 이미 확정된 산출물이 있으면 그대로 재서빙한다 — 재생성 0건(§8.3-4·NT-08).
            "ai2": _decrypt(generation.output_text) if generation else None,
        }
    if screen == "P8":
        return {
            "instruction": screen_copy.DOWNSTREAM_INSTRUCTION,
            "options": [
                {"code": option.code, "label": option.label}
                for option in screen_copy.DOWNSTREAM_OPTIONS
            ],
        }
    if screen == "P9":
        return ratings_view(session.id, branch.branch_index, ai1_text or "")
    return {}


async def build_state(db: AsyncSession, session: tables.Session) -> dict[str, Any]:
    """§8.2 `GET /state` 응답. 화면 선택도 데이터도 서버 상태에서 나온다(§1.3·§3.5)."""
    ss_state = SsState(session.ss_state)
    branch: tables.Branch | None = None
    if ss_state is SsState.BRANCH_BLOCK and session.branch_index is not None:
        branch = await store.branch_by_index(db, session.id, session.branch_index)
    b_state = BState(branch.b_state) if branch is not None else None
    screen = screen_for(ss_state, b_state)
    return {
        "screen": screen,
        "ss_state": ss_state.value,
        "b_state": b_state.value if b_state is not None else None,
        # 제출 경로(`/branch/{b}/…`)를 위한 값이다. **화면에 표시하지 않는다**(§4.4).
        "branch_index": session.branch_index,
        "participant_no": session.participant_no,
        "status": session.status,
        "has_ai2": has_ai2(branch.user1_disposition) if branch is not None else None,
        "data": await _screen_data(db, session, screen, branch),
    }
