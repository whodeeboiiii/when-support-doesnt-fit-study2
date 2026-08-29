"""incident dossier 로더 — 스키마 v2 (구현명세서 §5.3 · §5.4 · §1.2).

이 모듈이 돌려주는 어떤 값에도 `researcher_only` 층은 들어 있지 않다. 회고 stance·미전송
생각·ideal response는 §1.2 표에서 AI2·checker 전부 **금지**이고, 그 경계를 "조심해서 쓰기"가
아니라 **타입으로** 지킨다 — 이 로더는 researcher_only를 파싱조차 하지 않고, 필요한
콘솔(R3·R4)은 `dossier_private.py`를 따로 부른다(NT-04).

층별 지위 (§1.2·§5.3)
- `ai_visible`   : checkpoint packet 그 자체. AI2·checker·참가자 화면·콘솔·export 전부 허용.
                   ⚠ AI2·checker에 가는 것은 **참가자 수정본(effective)**이다(D-25) —
                   원문 그대로가 아니다. overlay는 `EffectiveAiVisible`이 만든다.
- `stimulus`     : R/U/Q segment + 조립 계량 + neutral_fallback + QC. 참가자에게는 **조립된
                   AI1 문자열만** 나가고 segment 구분·조건 라벨은 나가지 않는다(§1.2).
                   조립에는 둘이 있다 — `assemble()`은 자산 그대로(hash·계량·계약의 기준),
                   `presented()`는 거기에 무대지시를 얹은 표시·전달본이다(D-40).
- `evidence_code`: 연구자 코딩 층. 콘솔·export·배정표 생성에만 쓰이고, `llm/`에는
                   `prohibited_inference` 하나만 전달된다(§5.3 layer 접근 규율).
- `researcher_only` : 이 모듈의 관할이 아니다.

**v1과 달라진 것**(§5.3 "삭제된 키"): `sampling` → `evidence_code`, `trouble_cue.form` 폐기
(cue form 분류 삭제 — §1.5-2), `derivation.warranted_uptake` → `evidence_code.permitted_operation`,
`focal_repair_relevant_content`·`referent_map` 삭제(normalization 폐기 — D-34),
`stimuli.C1–C4` 전문 저장 → **`r`/`u`/`q` segment 조립**(D-35).

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
from typing import Any, Mapping, Sequence

from app.assets.files import available_participant_numbers, is_participant_no, read_raw
from app.core.text_metrics import TextMetrics, count_questions, measure

#: §0.4 실험 조건. ID 예약 규칙(§1.5) — C1–C4는 실험 조건 전용이다.
CONDITIONS: tuple[str, ...] = ("C1", "C2", "C3", "C4")

#: §5.4 조립 표 — 조건 → 이어 붙일 segment 키의 순서. **단일 공백 연결**(D-35).
STIMULUS_RECIPE: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"C1": ("r",), "C2": ("r", "q"), "C3": ("r", "u"), "C4": ("r", "u", "q")}
)
SEGMENT_KEYS: tuple[str, ...] = ("r", "u", "q")

#: §5.4 — 조립 결과의 질문 수 계약. elicitation segment(q)를 가진 조건만 정확히 1개다.
QUESTION_COUNT_BY_CONDITION: Mapping[str, int] = MappingProxyType(
    {"C1": 0, "C2": 1, "C3": 0, "C4": 1}
)

#: §4.4 [PI 확정 2026-08-26 · D-40 · 문안 개정 2026-08-28 · D-45 · A-level 분기 2026-08-29 · D-47]
#: — u(uptake) 뒤 **무대지시**. A-level별 1개이고, 한 참가자에게는 조건과 무관하게 1종이다.
#:
#: u는 "그 단정을 접고 …해 보겠습니다"처럼 **하겠다는 선언**으로 끝난다. 그대로 두면 참가자가
#: "왜 해준다고만 하고 실제로는 안 하지?"라고 읽는다(P08 세션에서 실제로 나온 반응). 실제
#: 지원이 이어졌다고 **가정한다**는 것을 알리는 한 줄이 그 자리에 있어야 한다.
#:
#: 자극 본문이 아니라 무대지시이므로 화면에서는 **회색**으로 표시하지만(§4.4), 문자열 자체는
#: 참가자가 본 AI1의 일부다 — 그래서 `presented()`가 만드는 표시·전달본에 들어가고 AI2
#: payload의 focal AI1에도 그대로 실린다(D-40). `assemble()`(locked 자산의 결정론 조립)은
#: 손대지 않는다: hash·`stimuli_meta`·자산 계약이 그 문자열을 기준으로 걸려 있다.
#:
#: **A-level로 갈리는 이유**(D-47). uptake가 후속 행위의 선언인 사건(A2)과, 확장을 멈추는
#: 것이 uptake의 전부인 사건(A1)은 무대지시가 가리켜야 하는 것이 다르다. A1의 u는 "여기서
#: 일단 멈추고 그대로 두겠습니다"(P14) · "더 이어가지 않겠습니다"(P17)로 끝나는데 거기에
#: "그 후 적절한 답변 제공"을 붙이면 자극과 정면으로 어긋난다. A1은 제공이 아니라 **범위가
#: 유지된 채 이어졌다**는 것을 알리고, A0은 아무 것도 붙이지 않는다(빈 문자열 — 무표시).
#:
#: A2 문안이 행위 중립인 이유(D-45): u가 약속하는 일은 사건마다 비교·판단·재검토·범위
#: 좁히기·추천으로 갈린다. 사건별 행위 명사를 채우면 dossier마다 문안 QC와 계약 테스트가
#: 늘고 "u 안에 실제 내용을 적지 않는다" 규칙이 새므로, D-45가 그 경로를 기각했다. D-47은
#: 그 결정을 유지한다 — 갈리는 것은 **A-level 3종**이지 사건 24종이 아니다.
#:
#: ⚠ 여기가 `a_level`을 읽는 **유일한 표시 경로**다. A-level은 incident descriptor이고
#: (§1.5-4) 배정표 제약·export 열 밖에서는 조건·분기·검증의 입력이 될 수 없다 — D-47은
#: **표시 문안 선택 1건에 한한 예외**이며, 다른 분기가 늘지 않는지는 NT-47이 지킨다.
UPTAKE_NOTE_BY_A_LEVEL: Mapping[str, str] = MappingProxyType(
    {
        "A0": "",
        "A1": "(이후 응답은 위 범위 안에서 이어짐)",
        "A2": "(그 후 적절한 답변 제공)",
    }
)

#: 무대지시가 붙는 자리 — u **바로 뒤**다. C3(r u)는 문말, C4(r u q)는 q 앞이 된다.
#: q 뒤가 아닌 이유: q는 "다음 응답을 위해 남은 질문"이라 마지막에 있어야 하고(STO1 문항이
#: "마지막에 한 질문"을 지칭한다), 무대지시가 가리키는 것은 u가 약속한 지원이기 때문이다.
UPTAKE_NOTE_AFTER = "u"

#: §5.3 — evidence-bounded actionability. **incident descriptor다**(§1.5-4).
#: 조건·분기·검증의 입력으로 쓰면 결함이다. 배정표 제약과 export 열, 그리고 **무대지시 문안
#: 선택**(D-47 — `UPTAKE_NOTE_BY_A_LEVEL` 한 곳)에만 쓴다.
A_LEVELS: frozenset[str] = frozenset({"A0", "A1", "A2"})

#: §5.3 `<TODO: PH-03b — broad locus 목록 확정>`. 초판 5종.
MISMATCH_LOCI: frozenset[str] = frozenset(
    {
        "content_depth",
        "affective_tone_intensity",
        "context_memory_use",
        "interpretation",
        "trajectory_timing",
    }
)

#: §5.3 provenance hierarchy (초안 §7.3). export가 사건별 구성비를 산출한다(§7.7).
PROVENANCE_VALUES: frozenset[str] = frozenset(
    {"verbatim_log", "participant_quote", "researcher_paraphrase"}
)

#: §4.2 — 참가자가 P2에서 수정할 수 있는 segment. `prior_evidence`는 줄 단위 하나의 텍스트다.
EDITABLE_SEGMENTS: tuple[str, ...] = (
    "situation_summary",
    "prior_evidence",
    "original_request",
    "problematic_ai_response",
    "trouble_cue",
)

#: §3.4·§2.8 — 이 segment가 수정되면 자극의 전제가 흔들릴 수 있다. R2 경보 + notify.
ALERT_SEGMENTS: frozenset[str] = frozenset({"trouble_cue", "problematic_ai_response"})

#: §6.5·§5.4 — neutral_fallback 길이 상한. `llm/integrity_rules.MAX_OUTPUT_CHARS`와 같은 값.
FALLBACK_MAX_CHARS = 1_200

#: §5.4 — segment에 researcher_only 문자열이 섞였는지 보는 부분 일치 임계(승계).
LEAK_MATCH_CHARS = 8

_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "participant_no",
        "version",
        "locked_at",
        "hash",
        "evidence_code",
        "ai_visible",
        "researcher_only",
        "stimulus",
    }
)
_EVIDENCE_CODE_KEYS: frozenset[str] = frozenset(
    {
        "a_level",
        "mismatch_locus",
        "mismatch_locus_text",
        "directional_constraint",
        "permitted_operation",
        "residual_uncertainty",
        "consequential_justification",
        "prohibited_inference",
        "coders",
        "adjudicated_at",
    }
)
_AI_VISIBLE_KEYS: frozenset[str] = frozenset(
    {
        "situation_summary",
        "prior_evidence",
        "original_request",
        "problematic_ai_response",
        "trouble_cue",
        "provenance",
        "excerpt_note",
    }
)
_STIMULUS_KEYS: frozenset[str] = frozenset(
    {"r", "u", "q", "stimuli_meta", "neutral_fallback", "qc"}
)
#: §5.4 QC 필드 — 시스템은 절차를 강제하지 않고 **필드의 존재만** 검증한다.
_QC_KEYS: frozenset[str] = frozenset(
    {
        "r_identity",
        "u_identity",
        "q_identity",
        "permitted_boundary",
        "leakage",
        "minimum_q",
        "reviewer",
        "at",
    }
)
#: §5.3 researcher_only 필수 필드. 이 모듈은 **존재만** 확인하고 값은 읽지 않는다.
_RESEARCHER_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "retrospective_stance",
        "unsent_at_the_time",
        "mismatch_interpretation",
        "original_trajectory",
        "ideal_response_reported",
        "correction_labor_notes",
    }
)

#: §5.3 provenance는 ai_visible의 **텍스트 필드 전부**를 덮어야 한다(§5.4 기동 게이트).
_PROVENANCE_REQUIRED: frozenset[str] = frozenset(EDITABLE_SEGMENTS)


class DossierContractError(ValueError):
    """자산 계약 위반 (NT-20·NT-22·NT-23). 기동 게이트가 이 예외로 기동을 끊는다."""


# --------------------------------------------------------------------------- #
# 값 객체 — 전부 frozen. 로드된 자산은 런타임에서 변형되지 않는다(§1.4 자극 immutability).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AiVisible:
    """§1.2 표의 'dossier ai_visible layer' — checkpoint packet 원문.

    ⚠ **이 값이 그대로 AI2에 가지 않는다**(D-25). LLM·P4 이후 화면이 보는 것은 참가자
    수정본을 얹은 `EffectiveAiVisible`이다. 원문은 P2(수정 대상)와 콘솔·export에만 나간다.
    `trouble_cue`가 dataclass가 아니라 **문자열 하나**인 것이 v2의 변화다(§1.5-2 — cue form
    분류 폐기).
    """

    situation_summary: str
    prior_evidence: tuple[str, ...]
    original_request: str
    problematic_ai_response: str
    trouble_cue: str
    provenance: Mapping[str, str]
    excerpt_note: str

    def segment(self, name: str) -> str:
        """§4.2 편집 단위 1건의 현재 문자열. `prior_evidence`는 줄 단위 하나의 텍스트다."""
        if name == "prior_evidence":
            return "\n".join(self.prior_evidence)
        if name not in EDITABLE_SEGMENTS:
            raise KeyError(f"편집 가능 segment가 아니다: {name!r} (§4.2)")
        return str(getattr(self, name))

    def segments(self) -> dict[str, str]:
        return {name: self.segment(name) for name in EDITABLE_SEGMENTS}

    def as_dict(self) -> dict[str, Any]:
        """콘솔 표시용 평면 사본. LLM payload 조립은 `EffectiveAiVisible`이 한다."""
        return {
            "situation_summary": self.situation_summary,
            "prior_evidence": list(self.prior_evidence),
            "original_request": self.original_request,
            "problematic_ai_response": self.problematic_ai_response,
            "trouble_cue": self.trouble_cue,
            "provenance": dict(self.provenance),
            "excerpt_note": self.excerpt_note,
        }


@dataclass(frozen=True, slots=True)
class EffectiveAiVisible:
    """§3.4 — 참가자 수정본을 얹은 checkpoint (D-25의 "effective checkpoint").

    **§6.2 allowlist의 ②가 이 타입이다.** `llm/context.py`의 시그니처가 `AiVisible`이 아니라
    이것을 받는 이유는 한 가지다: AI2가 원문을 보면 안 된다(§1.2 표 — "dossier ai_visible
    원문(수정 전)"은 AI2 ❌). 타입을 갈라 두면 원문을 넘기는 호출이 컴파일 단계에서 눈에
    띈다.

    `edited_segments`는 **어느 segment가 바뀌었는가**의 목록이고 원문은 담지 않는다 —
    수정 전 원문은 R-1의 금지 문자열이다(§6.4).
    """

    situation_summary: str
    prior_evidence: tuple[str, ...]
    original_request: str
    problematic_ai_response: str
    trouble_cue: str
    edited_segments: tuple[str, ...] = ()

    @property
    def edited(self) -> bool:
        return bool(self.edited_segments)

    def as_dict(self) -> dict[str, Any]:
        """§4.2·§4.4·§4.9·§4.10 화면 payload 조립용. 조건 라벨·provenance는 넣지 않는다."""
        return {
            "situation_summary": self.situation_summary,
            "prior_evidence": list(self.prior_evidence),
            "original_request": self.original_request,
            "problematic_ai_response": self.problematic_ai_response,
            "trouble_cue": self.trouble_cue,
        }


def build_effective(
    ai_visible: AiVisible, edits: Mapping[str, str] | None = None
) -> EffectiveAiVisible:
    """§3.4 — 원문 + segment별 최종 수정본 → effective checkpoint.

    `edits`는 `checkpoint_edits`에서 segment별 **마지막 행**만 추린 것이다(누적 저장, 최종본 =
    마지막 행 — §3.4). 여기서 검증하지 않는 이유: 빈 문자열 거부(400)는 저장 시점의 규칙이고
    (§4.2), 이미 저장된 값을 조립 시점에 다시 판정하면 두 규칙이 갈라진다.
    """
    applied = {
        name: text
        for name, text in (edits or {}).items()
        if name in EDITABLE_SEGMENTS and text is not None
    }
    prior = applied.get("prior_evidence")
    return EffectiveAiVisible(
        situation_summary=applied.get("situation_summary", ai_visible.situation_summary),
        prior_evidence=(
            tuple(line for line in prior.split("\n") if line.strip())
            if prior is not None
            else ai_visible.prior_evidence
        ),
        original_request=applied.get("original_request", ai_visible.original_request),
        problematic_ai_response=applied.get(
            "problematic_ai_response", ai_visible.problematic_ai_response
        ),
        trouble_cue=applied.get("trouble_cue", ai_visible.trouble_cue),
        edited_segments=tuple(name for name in EDITABLE_SEGMENTS if name in applied),
    )


@dataclass(frozen=True, slots=True)
class EvidenceCode:
    """§5.3 evidence_code 층 — 연구자 코딩. `llm/`에는 `prohibited_inference`만 나간다."""

    a_level: str
    mismatch_locus: str
    mismatch_locus_text: str
    directional_constraint: str
    permitted_operation: str
    residual_uncertainty: str
    consequential_justification: str
    prohibited_inference: tuple[str, ...]
    coders: str
    adjudicated_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "a_level": self.a_level,
            "mismatch_locus": self.mismatch_locus,
            "mismatch_locus_text": self.mismatch_locus_text,
            "directional_constraint": self.directional_constraint,
            "permitted_operation": self.permitted_operation,
            "residual_uncertainty": self.residual_uncertainty,
            "consequential_justification": self.consequential_justification,
            "prohibited_inference": list(self.prohibited_inference),
            "coders": self.coders,
            "adjudicated_at": self.adjudicated_at,
        }


@dataclass(frozen=True, slots=True)
class Stimulus:
    """§5.3 stimulus 층 — R/U/Q segment. **네 전문을 저장하지 않는다**(D-35)."""

    r: str
    u: str
    q: str
    stimuli_meta: Mapping[str, TextMetrics]
    neutral_fallback: str
    qc: Mapping[str, Any]

    def segment(self, key: str) -> str:
        if key not in SEGMENT_KEYS:
            raise KeyError(f"알 수 없는 segment: {key!r} (r·u·q — §5.3)")
        return str(getattr(self, key))


@dataclass(frozen=True, slots=True)
class Dossier:
    participant_no: str
    version: str
    locked_at: str | None
    #: §5.3 lock 시점에 기입되는 전체 JSON sha256. lock 전에는 None이다.
    locked_hash: str | None
    #: 지금 파일 내용으로 계산한 hash — §8.4 audit의 '자산 버전·hash' 자리.
    content_hash: str
    #: 스키마 더미로 내려왔는가 (§2.9 — 실값 미반입 상태). R1·R4·기동 로그가 표시한다(NT-42).
    is_dummy: bool
    source_path: Path
    evidence_code: EvidenceCode
    ai_visible: AiVisible
    stimulus: Stimulus

    @property
    def is_locked(self) -> bool:
        """§5.3 lock 절차 완료 여부. locked_at·hash가 있고 현재 내용과 일치해야 한다."""
        return bool(self.locked_at) and self.locked_hash == self.content_hash

    @property
    def uptake_note(self) -> str:
        """§4.4 · D-47 — 이 사건의 무대지시 문면. **A0은 빈 문자열**(무표시)이다.

        `a_level`을 읽는 유일한 표시 경로다(§1.5-4의 좁은 예외). 화면이 회색으로 그릴 자리를
        찾는 `ai1_note`와 `presented()`가 실제로 끼워 넣는 문자열이 같은 값이어야 하므로,
        둘 다 이 속성을 쓴다 — 두 곳에서 따로 고르면 회색 위치와 문면이 갈라진다.
        """
        return UPTAKE_NOTE_BY_A_LEVEL[self.evidence_code.a_level]

    def _parts(self, condition: str, *, with_note: bool) -> tuple[str, ...]:
        """§5.4 조립 레시피를 한 번만 걷는다 — `assemble()`·`presented()`의 공통 몸통."""
        recipe = STIMULUS_RECIPE.get(condition)
        if recipe is None:
            raise KeyError(f"알 수 없는 조건: {condition!r}")
        note = self.uptake_note
        parts: list[str] = []
        for key in recipe:
            parts.append(self.stimulus.segment(key))
            # A0은 문면이 비어 있다 — 빈 조각을 끼우면 공백 하나가 남는다(D-47).
            if with_note and note and key == UPTAKE_NOTE_AFTER:
                parts.append(note)
        return tuple(parts)

    def assemble(self, condition: str) -> str:
        """§5.4 AI1 자극 = R/U/Q segment의 **결정론 조립** (D-35).

        AI1은 checkpoint 수정과 무관하게 locked 그대로다(§3.4) — 이 함수에 수정본이 들어올
        자리가 없다는 것이 그 불변식의 구현이다.

        ⚠ 이것은 **자산의 조립 결과**다 — hash(`stimulus_hash`)·`stimuli_meta`·자산 계약
        테스트가 이 문자열을 본다. 참가자에게 보이고 AI2에 실리는 것은 `presented()`이고,
        둘은 C3·C4에서 무대지시 한 줄만큼 다르다(D-40).
        """
        return " ".join(self._parts(condition, with_note=False))

    def presented(self, condition: str) -> str:
        """§4.4 · D-40 — **참가자가 본 AI1**. 조립 자극 + (u가 있으면) 무대지시.

        화면(P4·P6·P7·P8 카드·P9·P10·P11) · AI2 payload의 focal AI1 · `turns.ai1` 기록이
        전부 이 함수를 쓴다. 한 함수인 것이 요점이다 — 화면에는 무대지시가 있고 AI2에는
        없으면, 참가자는 "이미 답변을 받은 대화"를 이어가는데 AI2는 그 사실을 모른 채
        그 답변을 처음부터 다시 하게 된다(P6에서 AI1과 AI2가 나란히 보이므로 바로 어긋나 보인다).

        C1·C2에는 u가 없으므로 `assemble()`과 같은 문자열이다. **A0 사건도 마찬가지다** —
        무대지시 문면이 비어 있어 네 조건 전부 `assemble()`과 같다(D-47).
        """
        return " ".join(self._parts(condition, with_note=True))

    def has_uptake_note(self, condition: str) -> bool:
        """이 조건의 AI1에 무대지시가 붙는가 — u가 있고(C3·C4) **문면이 비어 있지 않을** 때다.

        A0은 문면이 없으므로 C3·C4에서도 False다(D-47).
        """
        return bool(self.uptake_note) and UPTAKE_NOTE_AFTER in STIMULUS_RECIPE.get(condition, ())

    def stimulus_hash(self, condition: str) -> str:
        """§8.1 `focal_runs.stimulus_hash`·`alt_exposures.stimulus_hash` — 조립 결과의 sha256."""
        return hashlib.sha256(self.assemble(condition).encode("utf-8")).hexdigest()

    def all_stimuli(self) -> dict[str, str]:
        """네 조건의 조립 결과. **콘솔 R4 전용**이다 — 참가자 payload에 통째로 싣지 않는다(NT-31)."""
        return {condition: self.assemble(condition) for condition in CONDITIONS}


# --------------------------------------------------------------------------- #
# 해시
# --------------------------------------------------------------------------- #


def compute_document_hash(document: Mapping[str, Any]) -> str:
    """§5.3 "hash 필드 제외 canonical JSON sha256"(승계).

    `hash` 필드 자신은 제외하고 계산한다 — 포함하면 값을 적는 순간 hash가 달라져 자기
    참조가 된다. 그 밖의 전 필드(researcher_only 포함)가 대상이므로 어느 층이 바뀌어도
    lock 검증이 깨진다. `locked_at`은 포함한다.
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
    return tuple(
        _require_text(f"{section}[{index}]", entry, problems) for index, entry in enumerate(value)
    )


def _validate_evidence_code(raw: Any, problems: list[str]) -> EvidenceCode:
    section = _require_keys("evidence_code", raw, _EVIDENCE_CODE_KEYS, problems)

    a_level = section.get("a_level")
    if a_level not in A_LEVELS:
        problems.append(f"evidence_code.a_level: {sorted(A_LEVELS)} 중 하나여야 한다 (§1.5-4)")
        a_level = "A0"
    locus = section.get("mismatch_locus")
    if locus not in MISMATCH_LOCI:
        problems.append(
            f"evidence_code.mismatch_locus: {sorted(MISMATCH_LOCI)} 중 하나여야 한다 "
            "(<TODO: PH-03b>)"
        )
        locus = ""

    adjudicated_at = section.get("adjudicated_at")
    if adjudicated_at is not None and not isinstance(adjudicated_at, str):
        problems.append("evidence_code.adjudicated_at: null 또는 ISO-8601 문자열이어야 한다")
        adjudicated_at = None

    return EvidenceCode(
        a_level=str(a_level),
        mismatch_locus=str(locus),
        mismatch_locus_text=_require_text(
            "evidence_code.mismatch_locus_text", section.get("mismatch_locus_text"), problems
        ),
        directional_constraint=_require_text(
            "evidence_code.directional_constraint", section.get("directional_constraint"), problems
        ),
        permitted_operation=_require_text(
            "evidence_code.permitted_operation", section.get("permitted_operation"), problems
        ),
        residual_uncertainty=_require_text(
            "evidence_code.residual_uncertainty", section.get("residual_uncertainty"), problems
        ),
        consequential_justification=_require_text(
            "evidence_code.consequential_justification",
            section.get("consequential_justification"),
            problems,
        ),
        prohibited_inference=_require_text_list(
            "evidence_code.prohibited_inference", section.get("prohibited_inference", []), problems
        ),
        coders=str(section.get("coders", "")),
        adjudicated_at=adjudicated_at,
    )


def _validate_provenance(raw: Any, problems: list[str]) -> Mapping[str, str]:
    """§5.4 기동 게이트 — provenance 키가 ai_visible 텍스트 필드 **전부**를 덮어야 한다."""
    if not isinstance(raw, dict):
        problems.append("ai_visible.provenance: 객체여야 한다 (§5.3)")
        return MappingProxyType({})
    missing = sorted(_PROVENANCE_REQUIRED - set(raw))
    if missing:
        problems.append(f"ai_visible.provenance: 텍스트 필드 미커버 — {missing} (§5.4)")
    values: dict[str, str] = {}
    for field, value in raw.items():
        if value not in PROVENANCE_VALUES:
            problems.append(
                f"ai_visible.provenance.{field}: {sorted(PROVENANCE_VALUES)} 중 하나여야 한다"
            )
        values[str(field)] = str(value)
    return MappingProxyType(values)


def _validate_ai_visible(raw: Any, problems: list[str]) -> AiVisible:
    section = _require_keys("ai_visible", raw, _AI_VISIBLE_KEYS, problems)
    return AiVisible(
        situation_summary=_require_text(
            "ai_visible.situation_summary", section.get("situation_summary"), problems
        ),
        prior_evidence=_require_text_list(
            "ai_visible.prior_evidence", section.get("prior_evidence", []), problems
        ),
        original_request=_require_text(
            "ai_visible.original_request", section.get("original_request"), problems
        ),
        problematic_ai_response=_require_text(
            "ai_visible.problematic_ai_response", section.get("problematic_ai_response"), problems
        ),
        # v2 — cue form 분류 폐기(§1.5-2). trouble_cue는 텍스트 하나다.
        trouble_cue=_require_text("ai_visible.trouble_cue", section.get("trouble_cue"), problems),
        provenance=_validate_provenance(section.get("provenance"), problems),
        excerpt_note=str(section.get("excerpt_note", "")),
    )


def _assembled(segments: Mapping[str, str], condition: str) -> str:
    return " ".join(segments.get(key, "") for key in STIMULUS_RECIPE[condition])


def _validate_segment_contract(segments: Mapping[str, str], problems: list[str]) -> None:
    """NT-22 — segment 질문 수 + 조립 결과 질문 수 + 조건 간 동일성 (§5.4 · §0.4).

    조건 간 동일성(C2⊃q = C4⊃q, C3⊃u = C4⊃u, R 4조건 동일)은 **조립 방식에서 이미 따라
    나온다** — 같은 segment를 이어 붙이기 때문이다. 그래도 검사하는 이유는 조립 레시피가
    바뀌면 그 사실이 조용히 통과하지 않게 하기 위해서다(§0.4 동결 항목).
    """
    for key in SEGMENT_KEYS:
        expected = 1 if key == "q" else 0
        actual = count_questions(segments.get(key, ""))
        if actual != expected:
            problems.append(
                f"stimulus.{key}: 질문 {actual}개 — 계약값 {expected}개 (§5.4 · NT-22)"
            )

    for condition, expected in QUESTION_COUNT_BY_CONDITION.items():
        actual = count_questions(_assembled(segments, condition))
        if actual != expected:
            problems.append(
                f"조립({condition}): 질문 {actual}개 — 계약값 {expected}개 (NT-22)"
            )

    r = segments.get("r", "")
    for condition in CONDITIONS:
        if not _assembled(segments, condition).startswith(r):
            problems.append(f"조립({condition}): R prefix가 4조건 동일해야 한다 (§0.4 · NT-22)")
    if segments.get("q", "") not in _assembled(segments, "C2"):
        problems.append("조립(C2): q segment를 그대로 포함해야 한다 (C2=C4 Q 동결 — §0.4)")
    if segments.get("q", "") not in _assembled(segments, "C4"):
        problems.append("조립(C4): q segment를 그대로 포함해야 한다 (C2=C4 Q 동결 — §0.4)")
    if segments.get("u", "") not in _assembled(segments, "C3"):
        problems.append("조립(C3): u segment를 그대로 포함해야 한다 (C3=C4 U 동결 — §0.4)")
    if segments.get("u", "") not in _assembled(segments, "C4"):
        problems.append("조립(C4): u segment를 그대로 포함해야 한다 (C3=C4 U 동결 — §0.4)")


def _validate_stimuli_meta(
    raw: Any, segments: Mapping[str, str], problems: list[str]
) -> dict[str, TextMetrics]:
    """NT-23 — `stimuli_meta`가 **조립 결과**의 계량과 일치해야 한다."""
    if not isinstance(raw, dict) or set(raw) != set(CONDITIONS):
        problems.append("stimulus.stimuli_meta: C1·C2·C3·C4 네 키를 정확히 가져야 한다")
        raw = {}
    meta: dict[str, TextMetrics] = {}
    for condition in CONDITIONS:
        measured = measure(_assembled(segments, condition))
        entry = raw.get(condition)
        if not isinstance(entry, dict) or set(entry) != {"chars", "sentences", "questions"}:
            problems.append(
                f"stimulus.stimuli_meta.{condition}: {{chars, sentences, questions}} 세 키가 필요하다"
            )
        elif entry != measured.as_dict():
            problems.append(
                f"stimulus.stimuli_meta.{condition}: 조립 결과 계량과 불일치 — "
                f"기재 {entry} vs 실제 {measured.as_dict()} (NT-23)"
            )
        meta[condition] = measured
    return meta


def _validate_fallback(text: str, problems: list[str]) -> None:
    """NT-21 — neutral_fallback은 질문 0·비확장·길이 상한 통과 (§6.5)."""
    if not text:
        return
    questions = count_questions(text)
    if questions:
        problems.append(f"stimulus.neutral_fallback: 질문 {questions}개 — 0이어야 한다 (§6.5)")
    if len(text.strip()) > FALLBACK_MAX_CHARS:
        problems.append(
            f"stimulus.neutral_fallback: {len(text.strip())}자 — 상한 {FALLBACK_MAX_CHARS}자 (R-4)"
        )


def _validate_stimulus(raw: Any, problems: list[str]) -> Stimulus:
    section = _require_keys("stimulus", raw, _STIMULUS_KEYS, problems)
    segments = {
        key: _require_text(f"stimulus.{key}", section.get(key), problems) for key in SEGMENT_KEYS
    }
    _validate_segment_contract(segments, problems)
    meta = _validate_stimuli_meta(section.get("stimuli_meta"), segments, problems)
    fallback = _require_text("stimulus.neutral_fallback", section.get("neutral_fallback"), problems)
    _validate_fallback(fallback, problems)
    qc = _require_keys("stimulus.qc", section.get("qc"), _QC_KEYS, problems)
    return Stimulus(
        r=segments["r"],
        u=segments["u"],
        q=segments["q"],
        stimuli_meta=MappingProxyType(meta),
        neutral_fallback=fallback,
        qc=MappingProxyType(dict(qc)),
    )


def _validate_no_researcher_only_leak(
    document: Mapping[str, Any], segments: Sequence[str], problems: list[str]
) -> None:
    """§5.4 — 세 segment 어디에도 researcher_only 문자열이 없어야 한다(8자 이상 부분 일치).

    이 검사가 여기 있는 이유: 자산 작성자가 researcher_only의 문장을 자극에 옮겨 붙이면
    §1.2의 방화벽이 **자산 수준에서** 이미 깨진 것이고, 런타임 R-1은 그때 정상 응답을
    위반으로 잡게 된다. 자산 게이트에서 먼저 끊는 편이 낫다.
    """
    layer = document.get("researcher_only")
    if not isinstance(layer, dict):
        return
    haystack = " ".join(segments)
    if not haystack.strip():
        return
    for field, value in layer.items():
        text = str(value or "").strip()
        if len(text) < LEAK_MATCH_CHARS:
            continue
        if text in haystack:
            problems.append(
                f"stimulus: researcher_only.{field} 문자열이 segment에 등장한다 (§5.4 · §1.2)"
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
    if locked_hash is not None and (not isinstance(locked_hash, str) or len(locked_hash) != 64):
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
    if not is_participant_no(participant_no):
        raise KeyError(f"알 수 없는 참가자 번호: {participant_no!r} (허용: P00–P30)")

    document, path, is_dummy = read_raw(participant_no)
    problems: list[str] = []
    _validate_document(participant_no, document, problems)
    evidence_code = _validate_evidence_code(document.get("evidence_code"), problems)
    ai_visible = _validate_ai_visible(document.get("ai_visible"), problems)
    stimulus = _validate_stimulus(document.get("stimulus"), problems)
    _validate_no_researcher_only_leak(document, (stimulus.r, stimulus.u, stimulus.q), problems)
    if problems:
        joined = "\n  - ".join(problems)
        raise DossierContractError(f"{path} 자산 계약 위반 (§5.3·§5.4):\n  - {joined}")

    return Dossier(
        participant_no=participant_no,
        version=str(document["version"]),
        locked_at=document.get("locked_at"),
        locked_hash=document.get("hash"),
        content_hash=compute_document_hash(document),
        is_dummy=is_dummy,
        source_path=path,
        evidence_code=evidence_code,
        ai_visible=ai_visible,
        stimulus=stimulus,
    )


def load_all() -> dict[str, Dossier]:
    """파일이 존재하는 참가자 전부. 없는 번호는 조용히 건너뛴다(§5.1 — 24명 + P00)."""
    return {
        participant_no: load(participant_no)
        for participant_no in available_participant_numbers()
    }


def validate_all() -> dict[str, Dossier]:
    """§5.4 기동 게이트 — 서버 기동 시 dossier 전수 스키마 검증.

    한 건이라도 계약을 어기면 예외가 올라가 **기동이 실패한다**. 부분 로드로 뜨지 않는다.
    """
    return load_all()


def reset_cache() -> None:
    """자산 파일을 바꾼 뒤(테스트·개발) 캐시를 비운다."""
    load.cache_clear()
