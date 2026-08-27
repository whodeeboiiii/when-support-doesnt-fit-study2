"""`GET /state` 화면 payload 조립 (구현명세서 §8.2 · §3.5 · §4 · NT-31).

    GET /state → SS·F 상태 + 현재 화면에 필요한 데이터(자극·문항 순서 포함 — 서버 산출값 재사용)

규율 넷.

1. **현재 화면 것만 내려간다.** 특히 **focal 측정(SS05) 완료 전에는 대안 AI1이 payload
   어디에도 없다**(§1.2 참가자 화면 규율 · NT-31). 판정은 `state_machine.alt_exposure_allowed()`
   한 곳에서 하고, 이 모듈은 그 함수 없이 대안 자극을 만들지 않는다.
2. **조건 라벨은 내려가지 않는다.** payload 어디에도 C1–C4·R/U/Q·"focal/대안"이라는 구분
   원리가 없다(§4 서두). P9의 라벨은 "다른 응답 1/2/3"이고 P10은 "응답 A/B"다.
3. **문항 ID는 내려가지 않는다.** focal 평정도 pairwise도 **위치**로만 오간다. 위치 → 문항
   ID 매핑은 서버에만 있다.
4. **effective checkpoint를 쓴다.** P4·P6·P9·P10에 표시되는 checkpoint는 참가자 수정본이고
   (D-25), AI1은 수정과 무관하게 locked 그대로다(§3.4 · NT-34).
5. **AI1은 `presented()`로 낸다.** 화면에 나가는 AI1은 조립 자극 + (C3·C4) 무대지시이고
   (D-40), 같은 문자열이 AI2 payload·`turns.ai1`에도 간다. 회색으로 그릴 자리를 클라이언트가
   찾을 수 있게 `ai1_note`를 **조건과 무관하게 항상** 같이 내린다 — 조건에 따라 있고 없으면
   그 필드 자체가 조건 단서가 된다(§1.2 · NT-31).

P6·P11에서 참가자 자신의 텍스트를 복호화한다. §2.9의 복호화 지점 열거에 "참가자 본인 화면
재표시(P6 AI2·P11 pair 참조)"가 명시돼 있다 — 연구자 접근이 아니므로 audit 대상이 아니다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api import store
from app.assets import dossier_loader, pairwise_items, presurvey, rating_items, screen_copy
from app.core import assignment
from app.core.config import get_settings
from app.core.state_machine import (
    ALT_POSITIONS,
    FState,
    SsState,
    alt_exposure_allowed,
    screen_for,
)
from app.models import tables
from app.security import fernet


def _decrypt(value: bytes | None) -> str | None:
    return fernet.decrypt(value) if value else None


async def effective_checkpoint(
    db: AsyncSession, session: tables.Session
) -> dossier_loader.EffectiveAiVisible:
    """§3.4 — dossier 원문 + 참가자 최종 수정본.

    **이 함수가 effective checkpoint의 단일 생산 지점이다.** 화면·AI2 payload·콘솔이 같은
    함수를 쓰므로 "P4에는 수정본, AI2에는 원문" 같은 어긋남이 생기지 않는다(NT-34).
    """
    dossier = dossier_loader.load(session.participant_no)
    edits = await store.effective_edits(db, session.id)
    return dossier_loader.build_effective(dossier.ai_visible, edits)


def checkpoint_chat(effective: dossier_loader.EffectiveAiVisible) -> dict[str, Any]:
    """§4.2·§4.4 — 상황 요약 카드 + [참가자] → [AI] → [참가자] 말풍선 3개.

    `stimulus`·`evidence_code`·`researcher_only`는 참가자 화면에 존재하지 않는다(§1.2).
    """
    return {
        "situation_summary": effective.situation_summary,
        "prior_evidence": list(effective.prior_evidence),
        "turns": [
            {"role": "user", "text": effective.original_request},
            {"role": "ai", "text": effective.problematic_ai_response},
            {"role": "user", "text": effective.trouble_cue},
        ],
    }


def _scale() -> dict[str, Any]:
    asset = rating_items.load()
    return {
        "min": asset.scale_min,
        "max": asset.scale_max,
        "min_label": screen_copy.RATINGS_SCALE_MIN_LABEL,
        "max_label": screen_copy.RATINGS_SCALE_MAX_LABEL,
    }


# --------------------------------------------------------------------------- #
# 화면별 데이터
# --------------------------------------------------------------------------- #


def _checkpoint_edit_view(
    effective: dossier_loader.EffectiveAiVisible, edited: dict[str, str]
) -> dict[str, Any]:
    """§4.2 — segment별 현재 문면 + 수정 UI. 원문(수정 전)은 내려보내지 않는다.

    수정 전 원문을 내리지 않는 이유: 참가자가 고친 값이 화면의 정본이어야 다음 수정이 그
    위에 얹힌다(§3.4 누적). 원문 대조는 연구자 콘솔(R2 diff)의 일이다.
    """
    return {
        "intro": screen_copy.CHECKPOINT_VERIFY_INTRO,
        "checkpoint": checkpoint_chat(effective),
        "segments": [
            {
                "segment": name,
                "label": screen_copy.SEGMENT_LABELS[name],
                "text": effective.as_dict()[name]
                if name != "prior_evidence"
                else "\n".join(effective.prior_evidence),
                "edited": name in edited,
            }
            for name in dossier_loader.EDITABLE_SEGMENTS
        ],
        "edit_button": screen_copy.CHECKPOINT_EDIT_BUTTON,
        "save_button": screen_copy.CHECKPOINT_EDIT_SAVE,
        "cancel_button": screen_copy.CHECKPOINT_EDIT_CANCEL,
        "edit_hint": screen_copy.CHECKPOINT_EDIT_HINT,
        "confirm_button": screen_copy.CHECKPOINT_CONFIRM_BUTTON,
    }


def _ratings_view(session_id: object, focal_ai1: str) -> dict[str, Any]:
    """§4.8 — 블록 1(focal 5 construct) → 블록 2(MC + AI1 카드). 블록 내 순서는 시드 고정."""
    asset = rating_items.load()
    presented = rating_items.presentation_order(session_id)
    blocks = []
    for block in asset.blocks:
        blocks.append(
            {
                "scope": block.scope,
                "instruction": block.instruction,
                # §4.8 · D-37 — MC 블록에만 focal AI1 원문을 회색 카드로 재표시한다.
                "ai1_card": focal_ai1 if block.ai1_card else None,
                "items": [
                    {"position": entry.position, "text": entry.item.text}
                    for entry in presented
                    if entry.scope == block.scope
                ],
            }
        )
    return {"blocks": blocks, "scale": _scale(), "ai1_note": dossier_loader.UPTAKE_NOTE}


async def _alt_view(
    db: AsyncSession, session: tables.Session, dossier: dossier_loader.Dossier
) -> dict[str, Any]:
    """§4.9 — **한 번에 하나만**. 세 대안을 한꺼번에 싣지 않는다(NT-31의 실질).

    focal AI1은 여기서 다시 보여주지 않는다(초안 §7.10 "나머지 세 AI1").
    """
    position = session.alt_index or 1
    row = await store.alt_exposure(db, session.id, position)
    if row is None:  # pragma: no cover — 라우터가 먼저 만든다
        return {}
    effective = await effective_checkpoint(db, session)
    last = position >= ALT_POSITIONS
    return {
        "position": position,
        "total": ALT_POSITIONS,
        # 첫 진입에만 1회 안내(§4.9).
        "intro": screen_copy.ALT_EXPOSURE_INTRO if position == 1 else None,
        "label": screen_copy.ALT_EXPOSURE_LABEL.format(position=position),
        "checkpoint": checkpoint_chat(effective),
        # 조건 라벨이 아니라 **표시본 문자열**만 나간다(D-40).
        "ai1": dossier.presented(row.condition),
        "ai1_note": dossier_loader.UPTAKE_NOTE,
        "typing_ms": screen_copy.TYPING_INDICATOR_MS,
        "button": screen_copy.ALT_LAST_BUTTON if last else screen_copy.ALT_NEXT_BUTTON,
    }


async def _pairwise_view(
    db: AsyncSession, session: tables.Session, dossier: dossier_loader.Dossier
) -> dict[str, Any]:
    """§4.10 — 두 열 + contrast별 문항. 좌우는 배정표가 정한다(NT-38)."""
    position = session.pair_index or 1
    row = await store.pairwise_view(db, session.id, position)
    if row is None:  # pragma: no cover — 라우터가 먼저 만든다
        return {}
    effective = await effective_checkpoint(db, session)
    presented = pairwise_items.presentation_order(
        row.contrast, row.left_condition, row.right_condition
    )
    return {
        "position": position,
        "total": len(assignment.CONTRASTS),
        "intro": screen_copy.PAIRWISE_INTRO,
        "checkpoint": checkpoint_chat(effective),
        "checkpoint_toggle": screen_copy.PAIRWISE_CHECKPOINT_TOGGLE,
        # 「응답 A」(좌) / 「응답 B」(우). **어느 쪽이 focal인지 라벨링하지 않는다**(§4.10).
        "sides": [
            {
                "label": screen_copy.PAIRWISE_SIDE_LABELS[0],
                "ai1": dossier.presented(row.left_condition),
            },
            {
                "label": screen_copy.PAIRWISE_SIDE_LABELS[1],
                "ai1": dossier.presented(row.right_condition),
            },
        ],
        "ai1_note": dossier_loader.UPTAKE_NOTE,
        # 문항 ID는 내려가지 않는다 — 위치와 (치환된) 문면만.
        "items": [{"position": entry.position, "text": entry.text} for entry in presented],
        "scale": _scale(),
        # §4.10 — 버튼이 인터뷰 시점을 지시한다. 문안은 서버가 준다(NT-13과 같은 규율).
        "button": screen_copy.PAIRWISE_SUBMIT_BUTTON,
    }


async def _interview_view(
    db: AsyncSession, session: tables.Session, dossier: dossier_loader.Dossier
) -> dict[str, Any]:
    """§4.11 [파일럿 확정 2026-08-26] — 시나리오 · focal 대화 · 나머지 세 응답.

    pair별 인터뷰가 P10에서 끝나므로(§4.10) 이 화면은 **전체를 한 번에 놓고 보는 자리**다.
    구판의 좌우 재배치는 폐기했다.

    여기 없는 것이 계약이다(NT-39): 조건 라벨 · 문항·평정값 · sidecar · researcher_only.
    User1·AI2는 **참가자 본인 텍스트의 재표시**이므로 복호화한다(§2.9 — 연구자 접근이
    아니라서 audit 대상이 아니다).

    대안 세 개가 실려도 NT-31 위반이 아니다: SS08은 focal 측정(SS05) 이후이고, 같은 세
    자극을 참가자가 이미 P9에서 봤다.
    """
    effective = await effective_checkpoint(db, session)
    run = await store.focal_run(db, session.id)

    focal_turns: list[dict[str, Any]] = []
    if run is not None:
        turns = {turn.role: turn for turn in await store.turns(db, run.id)}
        if run.condition:
            focal_turns.append({"role": "ai", "text": dossier.presented(run.condition)})
        if "user1" in turns:
            focal_turns.append({"role": "user", "text": _decrypt(turns["user1"].text) or ""})
        if "ai2" in turns:
            focal_turns.append({"role": "ai", "text": _decrypt(turns["ai2"].text) or ""})

    alternatives = [
        {
            "label": screen_copy.INTERVIEW_ALT_LABEL.format(position=row.position),
            "ai1": dossier.presented(row.condition),
        }
        for row in await store.alt_exposures(db, session.id)
    ]

    return {
        "scenario_title": screen_copy.INTERVIEW_SCENARIO_TITLE,
        # 시나리오 3필드 = checkpoint 말풍선 그대로(원 요청 → 문제된 응답 → 참가자가 남긴 말).
        "scenario": checkpoint_chat(effective),
        "focal_title": screen_copy.INTERVIEW_FOCAL_TITLE,
        "focal_turns": focal_turns,
        "alternatives_title": screen_copy.INTERVIEW_ALTERNATIVES_TITLE,
        "alternatives": alternatives,
        "ai1_note": dossier_loader.UPTAKE_NOTE,
        "button": screen_copy.INTERVIEW_HOLD_BUTTON,
    }


async def _screen_data(
    db: AsyncSession,
    session: tables.Session,
    screen: str,
    run: tables.FocalRun | None,
) -> dict[str, Any]:
    dossier = dossier_loader.load(session.participant_no)
    ss_state = SsState(session.ss_state)

    if screen == "P1":
        return {
            "notice": screen_copy.CONSENT_NOTICE,
            "items": [
                {"field": item.field, "label": item.label} for item in screen_copy.CONSENT_ITEMS
            ],
            # §4.1 하단 고정 — PII 입력 금지(심의용 연구계획서 19번).
            "footnote": screen_copy.CONSENT_PII_NOTICE,
        }
    if screen == "P1S":
        # v1.0.1 §4.2 · NT-05 — 위치와 보이는 것만 내려간다. 문항 ID·역채점·section은
        # 서버에만 있다(규율 3과 같은 형태 — focal 평정·pairwise도 위치로만 오간다).
        return {
            "intro": screen_copy.PRESURVEY_INTRO,
            "items": presurvey.load().participant_payload(),
            "submit_button": screen_copy.PRESURVEY_SUBMIT_BUTTON,
        }
    if screen == "P2":
        edits = await store.effective_edits(db, session.id)
        effective = dossier_loader.build_effective(dossier.ai_visible, edits)
        return _checkpoint_edit_view(effective, edits)
    if screen == "P3":
        # §4.3 [파일럿 확정] 30초 비활성 · 60초 보조문. **DEV_MODE에서만** 대기를 0으로 둔다 —
        # 시연·QA에서 화면을 넘길 때마다 30초를 기다리면 워크스루가 성립하지 않는다.
        # 임계값을 서버가 내려주는 구조라 클라이언트에는 "지금이 개발이다" 플래그가 없다
        # (DevBar·DevNote와 같은 규율). 참가자 구성(DEV_MODE=false)은 30/60 그대로다.
        waived = get_settings().dev_mode
        return {
            "notice": screen_copy.REENTRY_NOTICE,
            "ready_notice": screen_copy.REENTRY_READY_NOTICE,
            "min_seconds": 0 if waived else screen_copy.REENTRY_MIN_SECONDS,
            "hint_seconds": 0 if waived else screen_copy.REENTRY_HINT_SECONDS,
        }

    # --- SS04 focal (P4–P7) -------------------------------------------------
    if run is not None and screen in {"P4", "P5", "P6", "P7"}:
        effective = await effective_checkpoint(db, session)
        # AI1은 **locked 자극 그대로**다 — 수정본을 조립에 넣지 않는다(§3.4 · NT-34).
        # 무대지시는 조립이 아니라 표시·전달본의 일부다(D-40) — 그래서 `presented()`다.
        focal_ai1 = dossier.presented(run.condition) if run.condition else None

        if screen == "P4":
            return {
                "checkpoint": checkpoint_chat(effective),
                "ai1": focal_ai1,
                "ai1_note": dossier_loader.UPTAKE_NOTE,
                "typing_ms": screen_copy.TYPING_INDICATOR_MS,
                "instruction": screen_copy.USER1_INSTRUCTION,
                "send_button": screen_copy.SEND_BUTTON,
            }
        if screen == "P5":
            return {
                "transition": screen_copy.SIDECAR_TRANSITION,
                "q1": screen_copy.SIDECAR_Q1,
                "q1_choices": [
                    {"value": value, "label": label}
                    for value, label in screen_copy.SIDECAR_HAS_MORE_CHOICES
                ],
                "has_notice": screen_copy.SIDECAR_HAS_NOTICE,
                "q2": screen_copy.SIDECAR_Q2,
                "q2_choices": [
                    {"value": value, "label": label}
                    for value, label in screen_copy.SIDECAR_PROVENANCE_CHOICES
                ],
                "q3": screen_copy.SIDECAR_Q3,
                # 3단은 `preexisting`에서만 뜬다 — 그 규칙을 서버가 알려준다(§4.5).
                "q3_when_provenance": screen_copy.SIDECAR_REASON_PROVENANCE,
                "q3_optional_notice": screen_copy.SIDECAR_REASON_OPTIONAL_NOTICE,
            }
        if screen == "P6":
            generation = await store.final_generation(db, run.id)
            return {
                "checkpoint": checkpoint_chat(effective),
                "ai1": focal_ai1,
                "ai1_note": dossier_loader.UPTAKE_NOTE,
                "user1": _decrypt((await store.turn(db, run.id, "user1")).text)
                if await store.turn(db, run.id, "user1")
                else None,
                "loading": screen_copy.AI2_LOADING,
                "delayed": screen_copy.AI2_DELAYED,
                # 이미 확정된 산출물이 있으면 그대로 재서빙한다 — 재생성 0건(§8.3·NT-08).
                "ai2": _decrypt(generation.output_text) if generation else None,
            }
        if screen == "P7":
            ai2 = await store.turn(db, run.id, "ai2")
            user1 = await store.turn(db, run.id, "user1")
            user2 = await store.turn(db, run.id, "user2")
            action = await store.downstream(db, run.id)
            return {
                # P6와 **같은** 채팅 맥락을 그대로 내린다(effective checkpoint → AI1 → User1
                # → AI2). 참가자가 "실제 상황이라면 어떻게 하겠는가"를 답하려면 직전 화면에서
                # 보던 대화가 눈앞에 남아 있어야 한다 — AI2 한 말풍선만 두면 무엇에 대한
                # 판단인지의 근거가 화면에서 사라진다.
                "checkpoint": checkpoint_chat(effective),
                "ai1": focal_ai1,
                "ai1_note": dossier_loader.UPTAKE_NOTE,
                "user1": _decrypt(user1.text) if user1 else None,
                "instruction": screen_copy.DOWNSTREAM_INSTRUCTION,
                "ai2": _decrypt(ai2.text) if ai2 else None,
                # F5 — 답장을 보냈다면 그 답장도 기록의 일부다(AI 응답은 없다 — D-33).
                "user2": _decrypt(user2.text) if user2 else None,
                "reply_label": screen_copy.DOWNSTREAM_REPLY_LABEL,
                "end_label": screen_copy.DOWNSTREAM_END_LABEL,
                "send_button": screen_copy.SEND_BUTTON,
                "end_types": [
                    {"code": option.code, "label": option.label}
                    for option in screen_copy.END_TYPE_OPTIONS
                ],
                "reason_prompt": screen_copy.END_REASON_PROMPT,
                "reason_required": screen_copy.END_REASON_REQUIRED,
                # F5 — 제출이 끝난 뒤의 종료 안내. 이 값이 있으면 화면은 안내만 그린다.
                "closed_notice": (
                    screen_copy.USER2_SENT_NOTICE
                    if action is not None and action.disposition == "reply"
                    else None
                ),
                "submitted": action is not None,
            }

    if screen == "P8":
        focal_ai1 = dossier.presented(run.condition) if run and run.condition else ""
        return _ratings_view(session.id, focal_ai1)

    # --- 대안 노출 이후 (§1.2 · NT-31) --------------------------------------
    if screen in {"P9", "P10", "P11"}:
        if not alt_exposure_allowed(ss_state):  # pragma: no cover — 상태가 이미 막는다
            raise RuntimeError(f"{screen}: focal 측정 완료 전에는 대안 자극을 실을 수 없다 (NT-31)")
        if screen == "P9":
            return await _alt_view(db, session, dossier)
        if screen == "P10":
            return await _pairwise_view(db, session, dossier)
        return await _interview_view(db, session, dossier)

    if screen == "P12":
        return {"notice": screen_copy.DEBRIEF_BODY, "button": screen_copy.DEBRIEF_CONFIRM_BUTTON}
    if screen == "ABORTED":
        return {"message": screen_copy.SESSION_ABORTED}
    return {}


async def build_state(db: AsyncSession, session: tables.Session) -> dict[str, Any]:
    """§8.2 `GET /state` 응답. 화면 선택도 데이터도 서버 상태에서 나온다(§1.3·§3.5)."""
    ss_state = SsState(session.ss_state)
    run: tables.FocalRun | None = None
    f_state: FState | None = None
    if session.f_state:
        f_state = FState(session.f_state)
    if ss_state is SsState.FOCAL or f_state is not None:
        run = await store.focal_run(db, session.id)

    screen = screen_for(ss_state, f_state if ss_state is SsState.FOCAL else None)
    return {
        "screen": screen,
        "ss_state": ss_state.value,
        "f_state": f_state.value if f_state is not None else None,
        "alt_index": session.alt_index,
        "pair_index": session.pair_index,
        "participant_no": session.participant_no,
        "status": session.status,
        "data": await _screen_data(db, session, screen, run),
    }
