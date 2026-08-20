"""테이블 정의 (구현명세서 §8.1 표 그대로).

두 가지 규율이 컬럼 모양을 결정한다.

1. 🔒 = §2.9 Fernet 암호화 필드다. 애플리케이션이 암호문(bytes)을 넣으므로 컬럼 타입은
   `LargeBinary`다. 평문 컬럼을 따로 두지 않는다 — 두면 언젠가 그쪽에 쓴다(NT-28).
2. **researcher_only layer는 이 파일에 존재하지 않는다**(§5.3·§8.1). dossier 자산 파일에만
   있고 DB로 내려오지 않는다. 컬럼을 추가하고 싶어지면 그건 §1.2 위반 신호다.

**v2.0에서 삭제된 테이블**: `branches`(→ `focal_runs`) · `normalizations`(D-34) ·
`presurvey_responses`(D-31). **신설**: `checkpoint_edits`(D-25) · `focal_runs` ·
`alt_exposures`(D-29) · `pairwise_views` · `pairwise_responses`.

합산 열은 어디에도 없다(§0.4 · §7.1 · §7.5 — overall preference index 산출 금지).
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
    """§8.1 `participants`. **배정표 행을 세션 생성 시 복사·고정한다**(NT-07).

    복사하는 이유는 §1.4다: 배정표 파일은 생성 후 금지지만, 파일이 바뀌어도 진행 중 세션의
    배정이 따라 바뀌면 안 된다. `assignment_version`이 어느 표에서 온 값인지를 남긴다.
    """

    __tablename__ = "participants"

    participant_no: Mapped[str] = mapped_column(String(3), primary_key=True)
    #: §5.2 배정표에서 복사 — C1–C4. 세션 중 불변(NT-07).
    focal_condition: Mapped[str | None] = mapped_column(String(2))
    #: focal을 제외한 세 조건의 순열 (§3.3).
    alt_order: Mapped[list | None] = mapped_column(JsonB)
    pair_order: Mapped[list | None] = mapped_column(JsonB)
    #: contrast → [left, right]
    pair_sides: Mapped[dict | None] = mapped_column(JsonB)
    assignment_version: Mapped[str | None] = mapped_column(String(32))
    #: §5.3 evidence_code에서 복사 — **descriptor 전용**이다(§1.5-4). 분기 입력 금지.
    a_level: Mapped[str | None] = mapped_column(String(2))
    mismatch_locus: Mapped[str | None] = mapped_column(String(32))
    dossier_version: Mapped[str | None] = mapped_column(String(64))
    dossier_hash: Mapped[str | None] = mapped_column(String(64))
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Session(Base):
    """§8.1 `sessions`. 참가자당 완료 세션 1개 불변식은 `api/admin.py`가 강제한다(NT-12)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    participant_no: Mapped[str] = mapped_column(
        ForeignKey("participants.participant_no"), nullable=False, index=True
    )
    #: §2.5 6자리 일회용 접속 코드는 **해시로만** 저장한다. 재발급은 동일 세션에 바인딩(NT-27).
    access_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: §3.1 SS00–SS10·SS90·SS91
    ss_state: Mapped[str] = mapped_column(String(8), nullable=False)
    #: §3.2 F0–F5. SS04 밖에서는 None이 아니라 **마지막 값이 남는다**(복원·콘솔 표시용).
    f_state: Mapped[str | None] = mapped_column(String(4))
    #: §3.3 진행 위치 1–3. 해당 단계 밖에서는 None.
    alt_index: Mapped[int | None] = mapped_column(Integer)
    pair_index: Mapped[int | None] = mapped_column(Integer)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: §4.1 항목별 bool + 시각 (6종 — `alternative_exposure` 신설)
    consent_items: Mapped[dict | None] = mapped_column(JsonB)
    consent_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # active/done/abort/dropout
    abort_reason: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    created_at: Mapped[datetime] = created_at_column()


class CheckpointEdit(Base):
    """§8.1 `checkpoint_edits` (§3.4 · §4.2 · D-25) — **누적**한다.

    한 segment를 여러 번 고칠 수 있고 최종본은 segment별 **마지막 행**이다. 덮어쓰지 않는
    이유는 §7.7이다: "checkpoint 수정의 성격(사실 정정 vs 선호 유입)"이 사후 코딩 대상이고,
    수정 과정 자체가 그 코딩의 자료다.

    `original`은 **그 수정 시점의 직전 값**이다(최초 수정이면 dossier 원문). 수정 전 원문은
    R-1의 금지 문자열이므로(§6.4) 여기서 나간 값이 AI2 payload에 닿는 경로는 없다.
    """

    __tablename__ = "checkpoint_edits"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    #: §4.2 편집 가능 segment 5종
    segment: Mapped[str] = mapped_column(String(32), nullable=False)
    original: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    edited: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FocalRun(Base):
    """§8.1 `focal_runs` — **참가자당 1행**(D-23). v1.0.1 `branches`의 후신.

    condition·stimulus_hash는 F0 진입 시 저장 후 불변이다(§3.2 — "조건 확정 유일 지점", NT-07).
    """

    __tablename__ = "focal_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, unique=True, index=True
    )
    condition: Mapped[str | None] = mapped_column(String(2))  # C1–C4
    stimulus_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: §3.4 — export에 노출된다. AI1·stimulus_hash는 수정과 무관하게 불변이다(NT-34).
    checkpoint_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_segments: Mapped[list | None] = mapped_column(JsonB)


class Turn(Base):
    """§8.1 `turns`. role = ai1(자극 표시) · user1 · ai2(실시간 생성 1턴) · user2.

    `text_normalized`는 삭제됐다(D-34 — normalization 폐기). **AI3는 없다**(D-33): role에
    `ai3`가 없다는 것이 그 불변식의 저장 층 표현이다.
    """

    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = uuid_pk()
    focal_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("focal_runs.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(8), nullable=False)  # ai1/user1/ai2/user2
    text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generations.id"))


class SidecarEntry(Base):
    """§8.1 `sidecar_entries` (§4.5 3단 — D-28).

    **LLM 경로에서 접근 불가**(§1.2 — 어떤 payload에도 넣지 않는다). v1의 `choice`·
    `relevance_1_7`이 삭제되고 `has_more`·`provenance`가 들어왔다.

    4범주(pre-existing unexpressed / deliberate withholding / prompt-evoked / uncertain)는
    **사후 코딩**이며 시스템 값이 아니다(§4.5·§7.3). 그래서 그 열이 여기 없다.
    """

    __tablename__ = "sidecar_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    focal_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("focal_runs.id"), nullable=False, index=True
    )
    has_more: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: §7.3 — preexisting / prompt_evoked / uncertain. 참가자 자기보고다.
    provenance: Mapped[str | None] = mapped_column(String(16))
    free_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    reason_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒


class DownstreamAction(Base):
    """§8.1 `downstream_actions` (§4.7 · D-26) — AI2 이후 enacted choice 1회."""

    __tablename__ = "downstream_actions"

    id: Mapped[uuid.UUID] = uuid_pk()
    focal_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("focal_runs.id"), nullable=False, index=True
    )
    #: §3.2 F4 — reply / end. 둘 다 유효한 종결이고 다음 상태가 같다(§0.3 판정 금지).
    disposition: Mapped[str] = mapped_column(String(8), nullable=False)
    #: §4.7 이탈 유형 6코드. `disposition=reply`면 None.
    end_type: Mapped[str | None] = mapped_column(String(24))
    reason_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    #: §4.7 "표시 순서" — 제시된 6코드의 순서 그대로(무작위 아님). 선택 위치는 여기서 파생.
    display_order: Mapped[list | None] = mapped_column(JsonB)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Rating(Base):
    """§8.1 `ratings` — focal 7 + MC 2 (§4.8). 세션 수준이다(branch당이 아니라).

    **합산 컬럼을 두지 않는다**(§0.4·§7.1). 5 construct는 라벨이지 점수가 아니다.
    """

    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("session_id", "item_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    #: §8.1 — focal(블록 1) / mc(블록 2). v1의 `block` 정수를 대체한다.
    scope: Mapped[str] = mapped_column(String(8), nullable=False)
    #: §7.1 construct 라벨 (grounding_sufficiency · … · manipulation_check)
    construct: Mapped[str] = mapped_column(String(48), nullable=False)
    item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–7
    #: 블록 내 무작위 제시 순서 (§4.8)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class AltExposure(Base):
    """§8.1 `alt_exposures` (§3.3 · §4.9 · D-29) — 대안 노출 1건.

    **focal 측정 완료 후에만 행이 생긴다**(NT-31). 최초 진입 시 저장 후 불변이고,
    `advanced_at`만 나중에 채워진다.
    """

    __tablename__ = "alt_exposures"
    __table_args__ = (UniqueConstraint("session_id", "position"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–3
    condition: Mapped[str] = mapped_column(String(2), nullable=False)  # C1–C4 (focal 제외)
    stimulus_hash: Mapped[str | None] = mapped_column(String(64))
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    advanced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PairwiseView(Base):
    """§8.1 `pairwise_views` (§3.3 · §4.10 · §7.5) — pair 제시 1건.

    `focal_included`·`focal_side`는 초안 §7.12의 sensitivity 분석 입력이다. 참가자에게는
    어느 쪽이 focal이었는지 라벨링하지 않지만(§4.10) 서버는 기록한다.
    """

    __tablename__ = "pairwise_views"
    __table_args__ = (UniqueConstraint("session_id", "position"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–3
    #: §1.5-6 — sequence / scope / stopping. 이 셋만 존재한다.
    contrast: Mapped[str] = mapped_column(String(16), nullable=False)
    left_condition: Mapped[str] = mapped_column(String(2), nullable=False)
    right_condition: Mapped[str] = mapped_column(String(2), nullable=False)
    focal_included: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: 'left' | 'right' | None (focal이 이 pair에 없을 때)
    focal_side: Mapped[str | None] = mapped_column(String(8))
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PairwiseResponse(Base):
    """§8.1 `pairwise_responses` — pair 1건의 문항 응답. **합산 없음**(§7.5)."""

    __tablename__ = "pairwise_responses"
    __table_args__ = (UniqueConstraint("pairwise_view_id", "item_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    pairwise_view_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pairwise_views.id"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–7
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Generation(Base):
    """§8.1 `generations` — AI2 integrity 감사 (§6.4·§6.6, NT-15).

    attempt 1/2와 `final`로 {정상 통과 | 재생성 1회 통과 | neutral_fallback} 경로가 복원된다.
    `alt_overlap`은 v2 신설이다: 구 R-2(타 branch 문자열)가 폐기되고, 대안 AI1의 u·q segment가
    AI2 출력에 verbatim 등장하는 경우를 **위반이 아니라 플래그로만** 기록한다(§6.4 R-2 행).
    """

    __tablename__ = "generations"

    id: Mapped[uuid.UUID] = uuid_pk()
    focal_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("focal_runs.id"), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 또는 2 (재생성 최대 1회)
    output_text: Mapped[bytes | None] = mapped_column(LargeBinary)  # 🔒
    rule_violations: Mapped[list | None] = mapped_column(JsonB)  # §6.4 R-1·R-3·R-4
    checker_result: Mapped[dict | None] = mapped_column(JsonB)  # 부록 A.2 판정 전문
    checker_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: §6.4 R-2 — **위반이 아니다**. 기록만 하고 재생성을 부르지 않는다.
    alt_overlap: Mapped[list | None] = mapped_column(JsonB)
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
    #: §2.2 silent update 감지 — 문자열 변경 최초 감지 시 notify
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
    """§8.1 `events` — beacon·flag·abort (§2.11).

    `branch_id`가 삭제됐다(§8.1) — 세션에 focal run이 하나뿐이라 참조가 필요 없다. 위치
    정보(alt_index·pair_index)가 필요하면 `payload`에 넣는다.

    flag 사유는 🔒 대상이다(§2.9). 컬럼을 늘리지 않고 `payload`의 암호문 필드로 넣는다.

    §2.11 — `response_latency` 파생 변수를 **산출하지 않는다**. beacon 쌍만 남긴다.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), nullable=False, index=True
    )
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
