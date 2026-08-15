"""테이블 정의 (구현명세서 §8.1 표 그대로).

NS1 범위는 **저장 자리**까지다 — 상태 전이·idempotency·복구 규칙은 NS2(§3·§8.2),
AI2 파이프라인 산출물의 기록 규칙은 NS3(§6)에서 이 테이블 위에 얹는다.

두 가지 규율이 컬럼 모양을 결정한다.

1. 🔒 = §2.9 Fernet 암호화 필드다. 애플리케이션이 암호문(bytes)을 넣으므로 컬럼 타입은
   `LargeBinary`다. 평문 컬럼을 따로 두지 않는다 — 두면 언젠가 그쪽에 쓴다(NT-28).
2. **researcher_only layer는 이 파일에 존재하지 않는다**(§5.2·§8.1). dossier 자산 파일에만
   있고 DB로 내려오지 않는다. 컬럼을 추가하고 싶어지면 그건 §1.2 위반 신호다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonB, created_at_column, uuid_pk


class Participant(Base):
    """§8.1 `participants`. P00은 QA 전용 합성 참가자다(§5.1 — `is_test=true`)."""

    __tablename__ = "participants"

    participant_no: Mapped[str] = mapped_column(String(3), primary_key=True)
    #: §3.3 `(participant_no − 1) mod 4 + 1`의 **저장값**. 산출은 NS2 `core/williams.py`.
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    dossier_version: Mapped[str | None] = mapped_column(String(64))
    dossier_hash: Mapped[str | None] = mapped_column(String(64))
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Session(Base):
    """§8.1 `sessions`. 참가자당 완료 세션 1개 불변식은 NS2에서 강제한다(NT-12)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    participant_no: Mapped[str] = mapped_column(
        ForeignKey("participants.participant_no"), nullable=False, index=True
    )
    #: §2.5 6자리 일회용 접속 코드는 **해시로만** 저장한다. 재발급은 동일 세션에 바인딩(NT-27).
    access_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: §3.1 SS00–SS07·SS90·SS91
    ss_state: Mapped[str] = mapped_column(String(8), nullable=False)
    #: SS04 진행 중인 branch (1–4). 그 밖의 상태에서는 None.
    branch_index: Mapped[int | None] = mapped_column(Integer)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: §4.1 항목별 bool + 시각
    consent_items: Mapped[dict | None] = mapped_column(JsonB)
    consent_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # active/done/abort/dropout
    abort_reason: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    created_at: Mapped[datetime] = created_at_column()


class Branch(Base):
    """§8.1 `branches`. condition·stimulus_hash는 최초 진입 시 저장 후 불변(NT-07)."""

    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("session_id", "branch_index"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    branch_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–4
    condition: Mapped[str | None] = mapped_column(String(2))  # C1–C4
    stimulus_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: §3.2 B0–B7
    b_state: Mapped[str] = mapped_column(String(4), nullable=False)
    #: §3.2 B2 3분기 — reply / no_reply / end
    user1_disposition: Mapped[str | None] = mapped_column(String(16))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Turn(Base):
    """§8.1 `turns`. role=ai1(자극 표시)·user1(참가자 발화)·ai2(실시간 생성 1턴)."""

    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = uuid_pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(8), nullable=False)  # ai1/user1/ai2
    text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    #: 🔒 user1만 — §6.4 referential normalization 결과. AI1·AI2에는 없다.
    text_normalized: Mapped[bytes | None] = mapped_column(LargeBinary)
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generations.id"))


class Normalization(Base):
    """§8.1 `normalizations`. 원문·정규화본은 `turns`에 있고 여기에는 판정 메타만 둔다."""

    __tablename__ = "normalizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matched_pattern_id: Mapped[str | None] = mapped_column(String(16))
    referent_id: Mapped[str | None] = mapped_column(String(32))


class SidecarEntry(Base):
    """§8.1 `sidecar_entries`. **LLM 경로에서 접근 불가**(§1.2 — 어떤 payload에도 넣지 않는다)."""

    __tablename__ = "sidecar_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    choice: Mapped[str] = mapped_column(String(8), nullable=False)  # none/has/skip
    free_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    relevance_1_7: Mapped[int | None] = mapped_column(Integer)
    reason_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒


class Rating(Base):
    """§8.1 `ratings` — branch당 12행, 전 종결 유형 동일(D-22).

    **합산 컬럼을 두지 않는다**(§0.4·§7.3 동결). 단일 re-grounding score는 존재하지 않는다.
    """

    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("branch_id", "item_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    #: §7.3 표의 변수명 (recognition·substantive_uptake·…)
    item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–7
    #: §4.9 2블록 — 1 = 문항 1·2(AI1 카드 앵커), 2 = 문항 3–12
    block: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 블록 내 무작위 제시 순서 (D-13·D-22)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class DownstreamAction(Base):
    """§8.1 `downstream_actions` — AI2가 표시된 branch만 1행 (§4.8 7선택 1회)."""

    __tablename__ = "downstream_actions"

    id: Mapped[uuid.UUID] = uuid_pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    #: §4.8 영문 코드 고정 — continue_reply·correct_reformulate·pause·end·new_chat·switch_ai·seek_human
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    #: §4.8 "표시 순서" — 화면에 제시된 7코드의 순서를 그대로 남긴다(선택지의 위치는 여기서 파생).
    display_order: Mapped[list | None] = mapped_column(JsonB)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PresurveyResponse(Base):
    """§8.1 `presurvey_responses` (§4.2).

    `value`가 JSON인 이유: 사전설문 자산이 아직 placeholder라 응답 형식(정수 척도·범주 코드)이
    문항마다 다를 수 있다 `<TODO: PH-01 — 문항 원문 확정 시 형식 고정>`.
    """

    __tablename__ = "presurvey_responses"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[object | None] = mapped_column(JsonB)
    display_order: Mapped[int | None] = mapped_column(Integer)


class Generation(Base):
    """§8.1 `generations` — AI2 integrity 감사 (§6.5·§6.6, NT-15).

    attempt 1/2와 `final`로 {정상 통과 | 재생성 1회 통과 | neutral_fallback} 경로가 복원된다.
    """

    __tablename__ = "generations"

    id: Mapped[uuid.UUID] = uuid_pk()
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 또는 2 (재생성 최대 1회)
    output_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    rule_violations: Mapped[list | None] = mapped_column(JsonB)  # §6.5 R-1–R-4
    checker_result: Mapped[dict | None] = mapped_column(JsonB)  # 부록 A.2 판정 전문
    checker_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class LlmCall(Base):
    """§8.1 `llm_calls` — 전 호출 1건 = 1행 (§8.4 audit 재구성의 원천)."""

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = uuid_pk()
    generation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generations.id"))
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # main/validator
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_requested: Mapped[str | None] = mapped_column(String(128))
    #: §2.2.2-② silent update 감지 — 문자열 변경 최초 감지 시 notify
    provider_reported_model: Mapped[str | None] = mapped_column(String(128))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict | None] = mapped_column(JsonB)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Event(Base):
    """§8.1 `events` — beacon·flag·abort (§2.11·§7.5).

    flag 사유는 🔒 대상이다(§2.9). 컬럼을 늘리지 않고 `payload`의 암호문 필드로 넣는다 —
    §8.1의 컬럼 목록이 정본이므로 여기에 열을 추가하지 않는다.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JsonB)
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    server_ts: Mapped[datetime] = created_at_column()


class AuditLog(Base):
    """§8.1 `audit_logs` — 콘솔 조회·복호화·export 전수 (§2.7·§2.9)."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    #: view/decrypt/export/flag/abort/code_issue (§8.1)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    target: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = created_at_column()


class StudyVersion(Base):
    """§8.1 `study_version` — soft launch 종료 시 1회 동결 (§10.5)."""

    __tablename__ = "study_version"

    id: Mapped[uuid.UUID] = uuid_pk()
    spec_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    model_strings: Mapped[dict | None] = mapped_column(JsonB)
    assets_hash: Mapped[dict | None] = mapped_column(JsonB)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
