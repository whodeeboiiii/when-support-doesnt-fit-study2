"""incident dossier 로더 — **ai_visible·derivation 층 전용** (구현명세서 §5.2 · §5.4 · §1.2).

이 모듈이 돌려주는 어떤 값에도 `researcher_only` 층은 들어 있지 않다. 회고 stance·미전송
생각·ideal response는 §1.2 표에서 AI2·checker·normalization 전부 **금지**이고, 그 경계를
"조심해서 쓰기"가 아니라 **타입으로** 지킨다 — 이 로더는 researcher_only를 파싱조차 하지 않고,
필요한 콘솔(R3·R4)은 `dossier_private.py`를 따로 부른다(NT-04).

층별 지위 (§1.2)
- `ai_visible`  : AI2·checker·normalization·콘솔·export 전부 허용. checkpoint 정보 그 자체.
- `derivation`  : **시스템 운영 자산**이다. AI1 표시·normalization·fallback에 쓰지만
                  derivation 값이 AI2 프롬프트에 직접 삽입되는 경로는 없다
                  (예외: normalized referent 치환문·fallback 문안 그 자체).
- `researcher_only` : 이 모듈의 관할이 아니다.

기동 게이트 (§5.4): `validate_all()`이 dossier 전수를 검증하고, 필수 키 누락·질문 수 계약
위반이면 **기동을 실패시킨다**. 자산이 깨진 채 세션을 받는 것보다 안 뜨는 편이 안전하다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from app.assets.files import PARTICIPANT_NUMBERS, read_raw
from app.core.text_metrics import TextMetrics, measure

#: §0.4 실험 조건. ID 예약 규칙(§1.5-8) — C1–C4는 실험 조건 전용이다.
CONDITIONS: tuple[str, ...] = ("C1", "C2", "C3", "C4")

#: §5.3 — 질문을 담는 조건은 elicitation 조건(C2·C4)뿐이고 정확히 1개다.
QUESTION_COUNT_BY_CONDITION: Mapping[str, int] = MappingProxyType(
    {"C1": 0, "C2": 1, "C3": 0, "C4": 1}
)

#: §1.5-2 AI-visible trouble cue의 cue form.
CUE_FORMS: frozenset[str] = frozenset(
    {"explicit", "mitigated", "ambiguous", "affiliative_plus_trouble"}
)

#: §5.1 목적표집 variation 축 ② primary mismatch locus.
MISMATCH_LOCI: frozenset[str] = frozenset(
    {
        "content_depth",
        "affective_tone_intensity",
        "context_memory_use",
        "interpretation",
        "trajectory_timing",
    }
)

_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"participant_no", "version", "locked_at", "hash", "sampling", "ai_visible",
     "researcher_only", "derivation"}
)
_SAMPLING_KEYS: frozenset[str] = frozenset({"actionability", "mismatch_locus", "notes_ref"})
_AI_VISIBLE_KEYS: frozenset[str] = frozenset(
    {"situation_summary", "original_request", "problematic_ai_response", "trouble_cue",
     "prior_evidence"}
)
_DERIVATION_KEYS: frozenset[str] = frozenset(
    {"warranted_uptake", "prohibited_inference", "residual_uncertainty",
     "focal_repair_relevant_content", "stimuli", "stimuli_meta", "neutral_fallback",
     "referent_map"}
)
#: §5.2 researcher_only 필수 필드. 이 모듈은 **존재만** 확인하고 값은 읽지 않는다.
_RESEARCHER_ONLY_KEYS: frozenset[str] = frozenset(
    {"retrospective_stance", "unsent_at_the_time", "mismatch_interpretation",
     "original_trajectory", "ideal_response_reported", "correction_labor_notes"}
)


class DossierContractError(ValueError):
    """자산 계약 위반 (NT-20·NT-22·NT-23). 기동 게이트가 이 예외로 기동을 끊는다."""


# --------------------------------------------------------------------------- #
# 값 객체 — 전부 frozen. 로드된 자산은 런타임에서 변형되지 않는다(§1.4 자극 immutability).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TroubleCue:
    text: str
    form: str


@dataclass(frozen=True, slots=True)
class AiVisible:
    """§1.2 표의 'dossier ai_visible layer' — AI2·checker가 볼 수 있는 유일한 사건 정보."""

    situation_summary: str
    original_request: str
    problematic_ai_response: str
    trouble_cue: TroubleCue
    prior_evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """payload 조립·콘솔 표시용 평면 사본 (§6.2 ②)."""
        return {
            "situation_summary": self.situation_summary,
            "original_request": self.original_request,
            "problematic_ai_response": self.problematic_ai_response,
            "trouble_cue": {"text": self.trouble_cue.text, "form": self.trouble_cue.form},
            "prior_evidence": list(self.prior_evidence),
        }


@dataclass(frozen=True, slots=True)
class ResidualUncertainty:
    """§5.3 — C2·C4가 공유하는 consequential residual uncertainty 1개와 그 질문문."""

    text: str
    question_stem: str


@dataclass(frozen=True, slots=True)
class ReferentEntry:
    """§6.4 referent_map 1건 — 지시표현이 가리킬 수 있는 AI1 제안의 명시 명제문."""

    patterns: tuple[str, ...]
    proposition: str


@dataclass(frozen=True, slots=True)
class Derivation:
    warranted_uptake: str
    prohibited_inference: tuple[str, ...]
    residual_uncertainty: ResidualUncertainty
    focal_repair_relevant_content: str
    stimuli: Mapping[str, str]
    stimuli_meta: Mapping[str, TextMetrics]
    neutral_fallback: str
    referent_map: tuple[ReferentEntry, ...]


@dataclass(frozen=True, slots=True)
class Sampling:
    actionability: int
    mismatch_locus: str
    notes_ref: str


@dataclass(frozen=True, slots=True)
class Dossier:
    participant_no: str
    version: str
    locked_at: str | None
    #: §5.2 lock 시점에 기입되는 전체 JSON sha256. lock 전에는 None이다.
    locked_hash: str | None
    #: 지금 파일 내용으로 계산한 hash — §8.4 audit의 '자산 버전·hash' 자리.
    content_hash: str
    #: 스키마 더미로 내려왔는가 (§2.9 — 실값 미반입 상태). 콘솔 R4·기동 로그가 이걸 표시한다.
    is_dummy: bool
    source_path: Path
    sampling: Sampling
    ai_visible: AiVisible
    derivation: Derivation

    @property
    def is_locked(self) -> bool:
        """§5.2 lock 절차 완료 여부. locked_at·hash가 있고 현재 내용과 일치해야 한다."""
        return bool(self.locked_at) and self.locked_hash == self.content_hash

    def stimulus(self, condition: str) -> str:
        """§3.2 — branch 최초 표시 시 쓰는 AI1 원문."""
        if condition not in CONDITIONS:
            raise KeyError(f"알 수 없는 조건: {condition!r}")
        return self.derivation.stimuli[condition]

    def stimulus_hash(self, condition: str) -> str:
        """§3.2 `branches.stimulus_hash` — 표시된 자극의 동일성 증거."""
        return hashlib.sha256(self.stimulus(condition).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 해시
# --------------------------------------------------------------------------- #


def compute_document_hash(document: Mapping[str, Any]) -> str:
    """§5.2 "전체 JSON sha256".

    `hash` 필드 자신은 제외하고 계산한다 — 포함하면 값을 적는 순간 hash가 달라져 자기
    참조가 된다. 그 밖의 전 필드(researcher_only 포함)가 대상이므로 어느 층이 바뀌어도
    lock 검증이 깨진다.
    """
    payload = {key: value for key, value in document.items() if key != "hash"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 검증 — 실패 사유를 모아서 한 번에 보고한다(자산 수정 왕복을 줄인다)
# --------------------------------------------------------------------------- #


def _require_keys(
    section: str, value: Any, required: frozenset[str], problems: list[str], *, exact: bool = True
) -> dict[str, Any]:
    if not isinstance(value, dict):
        problems.append(f"{section}: 객체여야 한다 (실제 {type(value).__name__})")
        return {}
    missing = sorted(required - set(value))
    if missing:
        problems.append(f"{section}: 필수 키 누락 — {missing}")
    if exact:
        unknown = sorted(set(value) - required)
        if unknown:
            problems.append(f"{section}: 스키마에 없는 키 — {unknown}")
    return value


def _require_text(section: str, value: Any, problems: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{section}: 비어 있지 않은 문자열이어야 한다")
        return ""
    return value


def _require_text_list(section: str, value: Any, problems: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        problems.append(f"{section}: 리스트여야 한다")
        return ()
    items: list[str] = []
    for index, entry in enumerate(value):
        items.append(_require_text(f"{section}[{index}]", entry, problems))
    return tuple(items)


def _validate_sampling(raw: Any, problems: list[str]) -> Sampling:
    section = _require_keys("sampling", raw, _SAMPLING_KEYS, problems)
    actionability = section.get("actionability")
    if actionability not in (0, 1, 2):
        problems.append("sampling.actionability: 0·1·2 중 하나여야 한다 (§1.5-2)")
        actionability = 0
    locus = section.get("mismatch_locus")
    if locus not in MISMATCH_LOCI:
        problems.append(f"sampling.mismatch_locus: {sorted(MISMATCH_LOCI)} 중 하나여야 한다")
        locus = ""
    return Sampling(
        actionability=int(actionability),
        mismatch_locus=str(locus),
        notes_ref=str(section.get("notes_ref", "")),
    )


def _validate_ai_visible(raw: Any, problems: list[str]) -> AiVisible:
    section = _require_keys("ai_visible", raw, _AI_VISIBLE_KEYS, problems)
    cue_raw = section.get("trouble_cue")
    if not isinstance(cue_raw, dict) or set(cue_raw) != {"text", "form"}:
        problems.append("ai_visible.trouble_cue: {text, form} 두 키를 가져야 한다")
        cue_raw = {"text": "", "form": ""}
    cue_form = cue_raw.get("form")
    if cue_form not in CUE_FORMS:
        problems.append(f"ai_visible.trouble_cue.form: {sorted(CUE_FORMS)} 중 하나여야 한다")
    return AiVisible(
        situation_summary=_require_text(
            "ai_visible.situation_summary", section.get("situation_summary"), problems
        ),
        original_request=_require_text(
            "ai_visible.original_request", section.get("original_request"), problems
        ),
        problematic_ai_response=_require_text(
            "ai_visible.problematic_ai_response", section.get("problematic_ai_response"), problems
        ),
        trouble_cue=TroubleCue(
            text=_require_text("ai_visible.trouble_cue.text", cue_raw.get("text"), problems),
            form=str(cue_form or ""),
        ),
        prior_evidence=_require_text_list(
            "ai_visible.prior_evidence", section.get("prior_evidence", []), problems
        ),
    )


def _validate_stimuli(section: Mapping[str, Any], problems: list[str]) -> dict[str, str]:
    raw = section.get("stimuli")
    if not isinstance(raw, dict) or set(raw) != set(CONDITIONS):
        problems.append("derivation.stimuli: C1·C2·C3·C4 네 키를 정확히 가져야 한다 (§5.3)")
        return {condition: "" for condition in CONDITIONS}
    return {
        condition: _require_text(f"derivation.stimuli.{condition}", raw[condition], problems)
        for condition in CONDITIONS
    }


def _validate_stimuli_meta(
    section: Mapping[str, Any], stimuli: Mapping[str, str], problems: list[str]
) -> dict[str, TextMetrics]:
    """NT-23 — `stimuli_meta`가 실제 원문의 계량과 일치해야 한다."""
    raw = section.get("stimuli_meta")
    if not isinstance(raw, dict) or set(raw) != set(CONDITIONS):
        problems.append("derivation.stimuli_meta: C1·C2·C3·C4 네 키를 정확히 가져야 한다")
        raw = {}
    meta: dict[str, TextMetrics] = {}
    for condition in CONDITIONS:
        measured = measure(stimuli.get(condition, ""))
        entry = raw.get(condition) if isinstance(raw, dict) else None
        if not isinstance(entry, dict) or set(entry) != {"chars", "sentences", "questions"}:
            problems.append(
                f"derivation.stimuli_meta.{condition}: {{chars, sentences, questions}} 세 키가 필요하다"
            )
        elif entry != measured.as_dict():
            problems.append(
                f"derivation.stimuli_meta.{condition}: 원문 계량과 불일치 — "
                f"기재 {entry} vs 실제 {measured.as_dict()} (NT-23)"
            )
        meta[condition] = measured
    return meta


def _validate_question_contract(
    stimuli: Mapping[str, str], residual: ResidualUncertainty, problems: list[str]
) -> None:
    """NT-22 — 자극 질문 수 계약과 C2·C4 question stem 동일성 (§0.4·§5.3).

    이 검사가 §5.4의 기동 게이트가 말하는 "질문 수 불일치"다. C2·C4가 같은 stem을 쓰지
    않으면 elicitation 효과와 질문 내용이 혼입된다(초안 §7.5).
    """
    from app.core.text_metrics import count_questions

    for condition, expected in QUESTION_COUNT_BY_CONDITION.items():
        actual = count_questions(stimuli.get(condition, ""))
        if actual != expected:
            problems.append(
                f"derivation.stimuli.{condition}: 질문 수 {actual} — 계약값 {expected} (NT-22)"
            )
    stem = residual.question_stem
    if stem:
        for condition in ("C2", "C4"):
            if stem not in stimuli.get(condition, ""):
                problems.append(
                    f"derivation.stimuli.{condition}: residual_uncertainty.question_stem을 "
                    "그대로 포함해야 한다 (C2=C4 질문 동결 — §0.4)"
                )


def _validate_referent_map(section: Mapping[str, Any], problems: list[str]) -> tuple[ReferentEntry, ...]:
    raw = section.get("referent_map")
    if not isinstance(raw, list):
        problems.append("derivation.referent_map: 리스트여야 한다 (§6.4)")
        return ()
    entries: list[ReferentEntry] = []
    for index, item in enumerate(raw):
        label = f"derivation.referent_map[{index}]"
        if not isinstance(item, dict) or set(item) != {"patterns", "proposition"}:
            problems.append(f"{label}: {{patterns, proposition}} 두 키를 가져야 한다")
            continue
        patterns = _require_text_list(f"{label}.patterns", item.get("patterns"), problems)
        if not patterns:
            problems.append(f"{label}.patterns: 최소 1개의 지시표현이 필요하다")
        entries.append(
            ReferentEntry(
                patterns=patterns,
                proposition=_require_text(f"{label}.proposition", item.get("proposition"), problems),
            )
        )
    return tuple(entries)


def _validate_derivation(raw: Any, problems: list[str]) -> Derivation:
    section = _require_keys("derivation", raw, _DERIVATION_KEYS, problems)
    residual_raw = section.get("residual_uncertainty")
    if not isinstance(residual_raw, dict) or set(residual_raw) != {"text", "question_stem"}:
        problems.append("derivation.residual_uncertainty: {text, question_stem} 두 키가 필요하다")
        residual_raw = {"text": "", "question_stem": ""}
    residual = ResidualUncertainty(
        text=_require_text(
            "derivation.residual_uncertainty.text", residual_raw.get("text"), problems
        ),
        question_stem=_require_text(
            "derivation.residual_uncertainty.question_stem",
            residual_raw.get("question_stem"),
            problems,
        ),
    )
    stimuli = _validate_stimuli(section, problems)
    meta = _validate_stimuli_meta(section, stimuli, problems)
    _validate_question_contract(stimuli, residual, problems)
    return Derivation(
        warranted_uptake=_require_text(
            "derivation.warranted_uptake", section.get("warranted_uptake"), problems
        ),
        prohibited_inference=_require_text_list(
            "derivation.prohibited_inference", section.get("prohibited_inference", []), problems
        ),
        residual_uncertainty=residual,
        focal_repair_relevant_content=_require_text(
            "derivation.focal_repair_relevant_content",
            section.get("focal_repair_relevant_content"),
            problems,
        ),
        stimuli=MappingProxyType(stimuli),
        stimuli_meta=MappingProxyType(meta),
        neutral_fallback=_require_text(
            "derivation.neutral_fallback", section.get("neutral_fallback"), problems
        ),
        referent_map=_validate_referent_map(section, problems),
    )


def _validate_document(participant_no: str, document: Mapping[str, Any], problems: list[str]) -> None:
    _require_keys("dossier", document, _TOP_LEVEL_KEYS, problems)
    if document.get("participant_no") != participant_no:
        problems.append(
            f"participant_no: 파일명({participant_no})과 값({document.get('participant_no')!r})이 다르다"
        )
    _require_text("version", document.get("version"), problems)

    locked_at = document.get("locked_at")
    if locked_at is not None:
        if not isinstance(locked_at, str):
            problems.append("locked_at: null 또는 ISO-8601 문자열이어야 한다")
        else:
            try:
                datetime.fromisoformat(locked_at)
            except ValueError:
                problems.append(f"locked_at: ISO-8601로 읽을 수 없다 — {locked_at!r}")

    locked_hash = document.get("hash")
    if locked_hash is not None and (
        not isinstance(locked_hash, str) or len(locked_hash) != 64
    ):
        problems.append("hash: null 또는 64자리 sha256 hex여야 한다")

    # researcher_only는 **존재와 키만** 본다 — 값은 이 모듈이 읽지 않는다(§1.2, NT-04).
    _require_keys(
        "researcher_only",
        document.get("researcher_only"),
        _RESEARCHER_ONLY_KEYS,
        problems,
        exact=False,
    )


# --------------------------------------------------------------------------- #
# 로드
# --------------------------------------------------------------------------- #


@lru_cache
def load(participant_no: str) -> Dossier:
    """dossier 1건을 검증해서 로드한다. 계약 위반이면 `DossierContractError`.

    반환값에는 `researcher_only`가 없다 — 이 함수를 지난 값은 LLM 경로에 닿아도 §1.2를
    깨지 않는다(단, payload allowlist는 §6.2가 따로 강제한다).
    """
    if participant_no not in PARTICIPANT_NUMBERS:
        raise KeyError(f"알 수 없는 참가자 번호: {participant_no!r} (허용: P00–P12)")

    document, path, is_dummy = read_raw(participant_no)
    problems: list[str] = []
    _validate_document(participant_no, document, problems)
    sampling = _validate_sampling(document.get("sampling"), problems)
    ai_visible = _validate_ai_visible(document.get("ai_visible"), problems)
    derivation = _validate_derivation(document.get("derivation"), problems)
    if problems:
        joined = "\n  - ".join(problems)
        raise DossierContractError(f"{path} 자산 계약 위반 (§5.2·§5.4):\n  - {joined}")

    return Dossier(
        participant_no=participant_no,
        version=str(document["version"]),
        locked_at=document.get("locked_at"),
        locked_hash=document.get("hash"),
        content_hash=compute_document_hash(document),
        is_dummy=is_dummy,
        source_path=path,
        sampling=sampling,
        ai_visible=ai_visible,
        derivation=derivation,
    )


def load_all() -> dict[str, Dossier]:
    return {participant_no: load(participant_no) for participant_no in PARTICIPANT_NUMBERS}


def validate_all() -> dict[str, Dossier]:
    """§5.4 기동 게이트 — 서버 기동 시 dossier 전수 스키마 검증.

    한 건이라도 계약을 어기면 예외가 올라가 **기동이 실패한다**. 부분 로드로 뜨지 않는다.
    """
    return load_all()


def reset_cache() -> None:
    """자산 파일을 바꾼 뒤(테스트·개발) 캐시를 비운다."""
    load.cache_clear()
