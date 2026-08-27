"""참가자 API — focal 수준 (구현명세서 §8.2 · §3.2 · §4.4–§4.7).

인과 창은 **checkpoint → AI1 → User1 → sidecar → AI2 → User2/종료**이고 **AI3는 없다**
(§0.4 · D-33). 이 파일의 엔드포인트 순서가 그 창 자체다.

v1.0.1 `api/branch.py`에서 개편됐다(부록 H.2). 사라진 것들이 그대로 v2.0의 결정이다.

- `BRANCH_COUNT`·`_close_branch`·branch 루프 → focal 1회(D-23)
- `no_reply/end` 3분기 → **User1 필수**(D-32). 이 파일에 disposition 인자가 없다.
- normalization 호출 → 폐기(D-34). User1 원문이 그대로 payload에 간다.
- downstream 7코드 → reply/end + 이탈 유형 6코드(D-26)
- ratings → **세션 수준**으로 이동(`api/participant.py`)

⚠ 이 라우터는 대안 AI1을 한 번도 읽지 않는다(NT-31·NT-10'). focal 구간에서 대안이 존재하지
않는다는 것은 화면·저장·payload 전체의 불변식이다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import leakage_sources, store
from app.api.deps import CurrentSession, DbSession, require_active
from app.api.state_payload import build_state, effective_checkpoint
from app.assets import dossier_loader, screen_copy
from app.core.idempotency import is_replay_f
from app.core.state_machine import (
    Disposition,
    FState,
    IllegalTransition,
    SsState,
    assert_f_transition,
    assert_ss_transition,
)
from app.llm import ai2_pipeline
from app.models import tables
from app.security import fernet

router = APIRouter(prefix="/api/focal", tags=["participant"])


def _now() -> datetime:
    return datetime.now(UTC)


async def _resolve(db: DbSession, session: tables.Session) -> tables.FocalRun:
    require_active(session)
    if SsState(session.ss_state) is not SsState.FOCAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "focal 단계가 아닙니다")
    run = await store.focal_run(db, session.id)
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "focal run이 없습니다")
    return run


def _f_state(session: tables.Session) -> FState:
    if not session.f_state:
        raise HTTPException(status.HTTP_409_CONFLICT, "focal 상태가 없습니다")
    return FState(session.f_state)


def _require_f(session: tables.Session, target: FState) -> None:
    try:
        assert_f_transition(_f_state(session), target)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


async def _reply(db: DbSession, session: tables.Session, replayed: bool) -> dict[str, Any]:
    await db.flush()
    return {"replayed": replayed, **await build_state(db, session)}


# --------------------------------------------------------------------------- #
# P4 User1 (§4.4 · F1) — **필수 작성**(D-32)
# --------------------------------------------------------------------------- #


class User1Request(BaseModel):
    text: str


@router.post("/user1")
async def submit_user1(
    payload: User1Request, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — F1→F2. 텍스트 필수 (NT-40).

    **"답장 보내지 않기"·"대화 종료" 경로가 없다**(D-32). 그런 요청을 받을 자리 자체를 두지
    않는 것이 그 결정의 구현이다 — disposition 인자도, 빈 텍스트 허용도 없다.
    """
    run = await _resolve(db, session)
    if is_replay_f(_f_state(session), FState.SIDECAR):
        return await _reply(db, session, replayed=True)

    if _f_state(session) is FState.AI1_PENDING:
        # 렌더 beacon이 유실된 경우 — 시간 beacon이 연구 상태를 막지 않는다(§2.11).
        session.f_state = FState.USER1.value
    _require_f(session, FState.SIDECAR)

    text = payload.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, screen_copy.USER1_EMPTY)

    # §8.3 — 저장은 제출 시점에 끝난다. AI2 호출은 sidecar 제출 뒤에만 일어나므로
    # (§0.4 · NT-16) 여기서 미리 생성하지 않는다.
    db.add(
        tables.Turn(
            focal_run_id=run.id,
            role="user1",
            text=fernet.encrypt(text),  # 🔒
            submitted_at=_now(),
        )
    )
    session.f_state = FState.SIDECAR.value
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P5 private sidecar 3단 (§4.5 · F2 · D-28)
# --------------------------------------------------------------------------- #


class SidecarRequest(BaseModel):
    has_more: bool
    free_text: str | None = None
    provenance: Literal["preexisting", "prompt_evoked", "uncertain"] | None = None
    reason: str | None = None


@router.post("/sidecar")
async def submit_sidecar(
    payload: SidecarRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — F2→F3. **이 내용은 어떤 LLM payload에도 들어가지 않는다**(§1.2 · NT-01).

    §8.2의 분기 규칙을 서버가 강제한다(NT-36):
    - `has_more=false` → 나머지 전부 null
    - `has_more=true` → `free_text`·`provenance` 필수
    - `reason`은 `provenance=preexisting`일 때만 허용 (3단은 그 경우에만 뜬다 — §4.5)
    """
    run = await _resolve(db, session)
    if is_replay_f(_f_state(session), FState.AI2):
        return await _reply(db, session, replayed=True)
    if _f_state(session) is not FState.SIDECAR:
        raise HTTPException(status.HTTP_409_CONFLICT, "sidecar 단계가 아닙니다")

    free_text = (payload.free_text or "").strip()
    reason = (payload.reason or "").strip()

    if payload.has_more:
        if not free_text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "내용을 적어주세요")
        if payload.provenance is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "언제 떠올랐는지 선택해주세요")
    elif free_text or reason or payload.provenance is not None:
        # "없어요"에 본문이 딸려 오면 화면과 저장이 어긋난 것이다 — 저장하지 않는다.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택과 입력이 맞지 않습니다")

    if reason and payload.provenance != screen_copy.SIDECAR_REASON_PROVENANCE:
        # 3단은 `preexisting`에서만 존재한다(§4.5). 다른 경로로 들어온 값은 받지 않는다.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "이유는 '답장을 쓸 때 이미 떠올라 있었어요'를 선택한 경우에만 받습니다 (§4.5)",
        )

    db.add(
        tables.SidecarEntry(
            focal_run_id=run.id,
            has_more=payload.has_more,
            provenance=payload.provenance,
            free_text=fernet.encrypt(free_text) if free_text else None,  # 🔒
            reason_text=fernet.encrypt(reason) if reason else None,  # 🔒
        )
    )
    _require_f(session, FState.AI2)
    session.f_state = FState.AI2.value
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P6 AI2 (§4.6 · §6 · F3)
# --------------------------------------------------------------------------- #


@router.post("/ai2")
async def run_ai2(session: CurrentSession, db: DbSession) -> dict[str, Any]:
    """§8.2 — F3 트리거. 재호출은 저장된 산출물을 그대로 돌려준다.

    §8.3이 요구하는 시간 순서(sidecar 제출 후에만 AI2 호출)는 상태로 강제된다: F3은 sidecar
    제출로만 도달하고, 그 전에는 이 엔드포인트가 409다(NT-16의 구조적 근거).
    """
    run = await _resolve(db, session)
    if _f_state(session) is not FState.AI2:
        raise HTTPException(status.HTTP_409_CONFLICT, "AI2 단계가 아닙니다")

    if await store.final_generation(db, run.id) is not None:
        # 새로고침·중복 요청 — **재생성 0건**(§8.3 · NT-08).
        return await _reply(db, session, replayed=True)

    dossier = dossier_loader.load(session.participant_no)
    user1_turn = await store.turn(db, run.id, "user1")
    user1 = fernet.decrypt(user1_turn.text) if user1_turn and user1_turn.text else ""

    # §6.2 allowlist ② — **effective checkpoint**(참가자 수정 반영). 원문이 아니다(D-25).
    effective = await effective_checkpoint(db, session)
    # §6.2 ③ — focal AI1 **참가자가 본 그대로**. v1.0.1과 정반대의 정책이다(D-34).
    # C3·C4에는 무대지시 한 줄이 붙어 있고 그것까지 함께 간다(D-40): 참가자는 "추천을 이미
    # 받은 대화"를 이어가는데 AI2만 그 사실을 모르면, AI2가 그 추천을 처음부터 다시 한다.
    focal_ai1 = dossier.presented(run.condition) if run.condition else ""

    # R-1 대조 문자열 — **판정에만** 쓰이고 어떤 프롬프트에도 실리지 않는다(§6.4).
    forbidden = await leakage_sources.collect(
        db, session_id=session.id, participant_no=session.participant_no, focal_run_id=run.id
    )
    # §6.4 R-2 — 대안 AI1의 u·q segment. **위반이 아니라 플래그**다(alt_overlap).
    alt_segments = leakage_sources.alt_segments(dossier, run.condition or "")

    outcome = await ai2_pipeline.run(
        db,
        focal_run_id=run.id,
        effective=effective,
        focal_ai1=focal_ai1,
        user1=user1,
        neutral_fallback=dossier.stimulus.neutral_fallback,
        prohibited_inference=dossier.evidence_code.prohibited_inference,
        forbidden=forbidden,
        alt_segments=alt_segments,
    )
    db.add(
        tables.Turn(
            focal_run_id=run.id,
            role="ai2",
            text=fernet.encrypt(outcome.text),  # 🔒
            rendered_at=_now(),
            generation_id=outcome.generation_id,
        )
    )
    # f_state는 F3에 머문다 — 표시가 끝나고 참가자가 진행할 때 `POST /advance`가 F4로 옮긴다.
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# P7 User2 / 종료 (§4.7 · F4 · D-26)
# --------------------------------------------------------------------------- #


class DownstreamRequest(BaseModel):
    disposition: Literal["reply", "end"]
    text: str | None = None
    end_type: str | None = None
    reason: str | None = None


@router.post("/downstream")
async def submit_downstream(
    payload: DownstreamRequest, session: CurrentSession, db: DbSession
) -> dict[str, Any]:
    """§8.2 — F4→F5. enacted behavioral choice이고 실제 실행은 요구하지 않는다(§7.4).

    검증(NT-41): reply → text 필수 / end → end_type 필수 / other → 이유 텍스트 필수.

    **`reply`여도 AI 응답을 만들지 않는다**(§3.2 · D-33). User2를 저장하고 안내만 표시한다.
    """
    run = await _resolve(db, session)
    if is_replay_f(_f_state(session), FState.CLOSED):
        return await _reply(db, session, replayed=True)
    if _f_state(session) is not FState.DOWNSTREAM:
        raise HTTPException(status.HTTP_409_CONFLICT, "downstream 단계가 아닙니다")

    disposition = Disposition(payload.disposition)
    text = (payload.text or "").strip()
    reason = (payload.reason or "").strip()

    if disposition is Disposition.REPLY:
        if not text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, screen_copy.USER1_EMPTY)
        if payload.end_type or reason:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택과 입력이 맞지 않습니다")
        end_type = None
    else:
        if payload.end_type not in screen_copy.END_TYPE_CODES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택지에 없는 이탈 유형입니다")
        if text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택과 입력이 맞지 않습니다")
        end_type = payload.end_type
        # `other`는 "기타 (직접 입력)"이라 텍스트가 없으면 값이 비어 있는 것과 같다(NT-41).
        if end_type == screen_copy.END_TYPE_REQUIRES_TEXT and not reason:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "어떤 선택인지 적어주세요")
        if screen_copy.END_REASON_REQUIRED and not reason:
            # [파일럿 확정: 필수 여부] — 상수 하나로 끌 수 있게 둔다(§4.7).
            raise HTTPException(status.HTTP_400_BAD_REQUEST, screen_copy.END_REASON_PROMPT)

    if disposition is Disposition.REPLY:
        db.add(
            tables.Turn(
                focal_run_id=run.id,
                role="user2",
                text=fernet.encrypt(text),  # 🔒
                submitted_at=_now(),
            )
        )
    db.add(
        tables.DownstreamAction(
            focal_run_id=run.id,
            disposition=disposition.value,
            end_type=end_type,
            reason_text=fernet.encrypt(reason) if reason else None,  # 🔒
            # §4.7 "표시 순서" — 제시된 6코드의 순서 그대로(무작위 아님).
            display_order=list(screen_copy.END_TYPE_CODES),
            selected_at=_now(),
        )
    )
    _require_f(session, FState.CLOSED)
    session.f_state = FState.CLOSED.value
    run.completed_at = _now()
    return await _reply(db, session, replayed=False)


# --------------------------------------------------------------------------- #
# `POST /advance` 위임 (§8.2 — P6: F3→F4 · P7: F5→SS05)
# --------------------------------------------------------------------------- #


async def advance_focal(
    db: AsyncSession, session: tables.Session, screen: str
) -> dict[str, Any]:
    """`api/participant.advance`가 위임하는 focal 구간 전이."""
    run = await store.focal_run(db, session.id)
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "focal run이 없습니다")

    if screen == "P6":
        # F3 → F4. AI2(또는 fallback)가 **표시된 뒤**에만 넘어간다(§3.2).
        if await store.final_generation(db, run.id) is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "표시할 AI2 산출물이 아직 없습니다")
        _require_f(session, FState.DOWNSTREAM)
        session.f_state = FState.DOWNSTREAM.value
        await db.flush()
        return await build_state(db, session)

    # P7 — F5(CLOSED)에서 종료 안내를 읽은 뒤 SS05로. downstream 제출이 선행돼야 한다.
    if _f_state(session) is not FState.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "아직 선택이 저장되지 않았습니다")
    try:
        assert_ss_transition(SsState(session.ss_state), SsState.FOCAL_MEASURES)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.ss_state = SsState.FOCAL_MEASURES.value
    await db.flush()
    return await build_state(db, session)
