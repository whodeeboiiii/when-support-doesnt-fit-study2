"""사전설문 자산 로더 (v1.0.1 명세 §4.2 · §7.1 · NT-05 — D-44로 v2.0에 복원).

**이 모듈은 v2.0 정본(D-31)이 삭제했던 것을 되살린 것이다.** 근거는 명세가 아니라 연구자
지시다(D-44, `PLACEHOLDERS.md` §10 · `PROGRESS.md`) — 그래서 참조 명세는 v1.0.1의 §4.2·§7.1
이고, 자산·계약·렌더 규칙은 그쪽을 글자 그대로 따른다. 되살린 범위도 그 두 절뿐이다:
문항 자산 · 화면 1개 · 저장 테이블 1개. v1.0.1의 다른 폐기 항목(williams·normalization 등)은
여전히 사용 금지다(CLAUDE.md Legacy 참조 규칙).

자산은 `fixtures/presurvey_items_v0.json`이다. 문항 원문 초안은 착지했고(초안 §7.4를 문항으로
옮긴 1차 번안), 남은 것은 독립 2인차 번안·합의와 PI 확인이다 `<TODO: PH-01>`. 승격
(= `presurvey_items_v1.json`을 놓는 것) 전까지 모집 게이트(`core/freeze.py`)는 PH-01을 계속
보고한다 — **파일명이 곧 상태 표시다**(`rating_items`·`pairwise_items`와 같은 규율).

§4.2의 렌더 규칙이 이 모듈의 핵심이다.

    문항 ID·역채점 메타는 참가자 payload로 새지 않는다(v4.2 규율 승계 — NT-05).

그래서 참가자에게 내려가는 것은 **제시 위치(position)와 보이는 것들뿐**이고, 응답도 위치로
돌아온다. 위치 → 문항 ID 매핑은 서버가 갖는다. 이 구조는 방어적일 뿐 아니라 저장 규약과도
맞는다 — `presurvey_responses`는 (item_id, value, display_order)를 요구한다(§8.1).

허용 필드를 **allowlist**로 고정한 이유: 자산에 새 메타 키가 추가돼도 payload가 자동으로
넓어지지 않는다. blocklist였다면 `_note`·`reverse`를 지운 다음 키가 조용히 새어 나간다.

⚠ 사전설문 응답은 **어떤 LLM 호출에도 들어가지 않는다**(§1.2 evidence boundary). `llm/`은 이
모듈을 import하지 않는다 — `tests/unit/test_evidence_boundary_static.py`가 정적으로 막는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.assets import screen_copy
from app.assets.files import REPO_ROOT

FIXTURES_DIR = REPO_ROOT / "fixtures"

#: **앞의 것이 우선**. `_v1`이 실값이고 `_v0`은 초안 placeholder다(PH-01). 목록을 둘로
#: 유지하는 이유는 `rating_items`와 같다 — `_v1`이 사라지면 로더가 `_v0`으로 내려가고
#: 모집 게이트가 다시 PH-01을 보고한다. 그 회귀 감지가 목록의 값이다.
ASSET_CANDIDATES: tuple[str, ...] = ("presurvey_items_v1.json", "presurvey_items_v0.json")
PLACEHOLDER_SUFFIX = "_v0.json"

#: 응답 유형. 자산 원문이 확정되면 이 목록이 바뀔 수 있다 `<TODO: PH-01>`.
CHOICE_TYPES = frozenset({"single_choice", "multi_choice"})
LIKERT_TYPES = frozenset({"likert_1_7"})
ITEM_TYPES = CHOICE_TYPES | LIKERT_TYPES

LIKERT_MIN = 1
LIKERT_MAX = 7

#: 참가자 payload에 실릴 수 있는 필드 (NT-05). 여기 없는 것은 무엇이든 서버에 남는다.
PARTICIPANT_FIELDS = frozenset(
    {
        "position",
        "type",
        "text",
        "options",
        "scale_min",
        "scale_max",
        "scale_min_label",
        "scale_max_label",
    }
)

#: 척도 앵커. §4.2는 앵커를 지정하지 않지만 숫자 7칸만 그리면 문항에 답할 수 없다 —
#: §4.8 평정과 **같은 앵커**를 쓴다(같은 1–7 척도이고, 두 화면의 표현이 갈리면 그것대로 혼란이다).
LIKERT_MIN_LABEL = screen_copy.RATINGS_SCALE_MIN_LABEL
LIKERT_MAX_LABEL = screen_copy.RATINGS_SCALE_MAX_LABEL

#: 자산 파일이 가질 수 있는 문항 키. `_note`·`reverse`·`section`은 **연구자 메타**다.
_ITEM_KEYS = frozenset({"id", "section", "type", "text", "options", "reverse", "_note"})


class PresurveyContractError(ValueError):
    """사전설문 자산 계약 위반 — 기동 게이트(§5.4와 같은 지위)에서 기동을 끊는다."""


@dataclass(frozen=True, slots=True)
class PresurveyOption:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class PresurveyItem:
    item_id: str
    section: str
    type: str
    text: str
    options: tuple[PresurveyOption, ...]
    reverse: bool

    def participant_view(self, position: int) -> dict[str, Any]:
        """참가자에게 내려가는 형태 — `item_id`·`reverse`·`section`·`_note`는 없다(NT-05)."""
        view: dict[str, Any] = {"position": position, "type": self.type, "text": self.text}
        if self.type in CHOICE_TYPES:
            view["options"] = [
                {"value": option.value, "label": option.label} for option in self.options
            ]
        else:
            view["scale_min"] = LIKERT_MIN
            view["scale_max"] = LIKERT_MAX
            view["scale_min_label"] = LIKERT_MIN_LABEL
            view["scale_max_label"] = LIKERT_MAX_LABEL
        return view


@dataclass(frozen=True, slots=True)
class Presurvey:
    version: str
    source_path: Path
    is_placeholder: bool
    items: tuple[PresurveyItem, ...]

    @property
    def item_count(self) -> int:
        return len(self.items)

    def participant_payload(self) -> list[dict[str, Any]]:
        """§4.2 렌더 payload. 제시 순서는 자산 순서 그대로다.

        명세서는 사전설문의 순서 무작위를 지시하지 않는다(무작위는 §4.8 평정 문항의 규칙 —
        D-37). 자산 순서를 그대로 쓰고 그 위치를 `display_order`로 저장한다.
        """
        return [item.participant_view(index + 1) for index, item in enumerate(self.items)]

    def item_at(self, position: int) -> PresurveyItem:
        if not 1 <= position <= len(self.items):
            raise KeyError(f"사전설문 문항 위치 범위 밖: {position}")
        return self.items[position - 1]

    def validate_response(self, position: int, value: Any) -> None:
        """제출값이 문항 유형과 맞는가. 틀리면 400 — 조용히 저장하지 않는다."""
        item = self.item_at(position)
        allowed = {option.value for option in item.options}
        if item.type == "single_choice":
            if value not in allowed:
                raise ValueError(f"문항 {position}: 선택지에 없는 값")
        elif item.type == "multi_choice":
            if not isinstance(value, list) or not value or not set(value) <= allowed:
                raise ValueError(f"문항 {position}: 선택지 목록에 없는 값")
        elif item.type in LIKERT_TYPES:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"문항 {position}: 정수 응답이 필요하다")
            if not LIKERT_MIN <= value <= LIKERT_MAX:
                raise ValueError(f"문항 {position}: {LIKERT_MIN}–{LIKERT_MAX} 범위를 벗어났다")


def asset_path() -> Path:
    for name in ASSET_CANDIDATES:
        candidate = FIXTURES_DIR / name
        if candidate.is_file():
            return candidate
    raise PresurveyContractError(
        f"사전설문 자산이 없다: {[str(FIXTURES_DIR / name) for name in ASSET_CANDIDATES]} "
        "(PH-01 자산 — `_v1`·`_v0` 어느 쪽도 없다)"
    )


def _parse_item(index: int, raw: Any, problems: list[str], seen: set[str]) -> PresurveyItem | None:
    label = f"items[{index}]"
    if not isinstance(raw, dict):
        problems.append(f"{label}: 객체여야 한다")
        return None
    unknown = sorted(set(raw) - _ITEM_KEYS)
    if unknown:
        problems.append(f"{label}: 스키마에 없는 키 — {unknown}")
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id:
        problems.append(f"{label}.id: 비어 있지 않은 문자열이어야 한다")
        return None
    if item_id in seen:
        problems.append(f"{label}.id: 중복 — {item_id!r}")
    seen.add(item_id)

    item_type = raw.get("type")
    if item_type not in ITEM_TYPES:
        problems.append(f"{label}.type: {sorted(ITEM_TYPES)} 중 하나여야 한다")
        return None

    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        problems.append(f"{label}.text: 비어 있지 않은 문자열이어야 한다")
        text = ""

    options: list[PresurveyOption] = []
    raw_options = raw.get("options", [])
    if item_type in CHOICE_TYPES:
        if not isinstance(raw_options, list) or not raw_options:
            problems.append(f"{label}.options: 선택형 문항은 선택지가 1개 이상 필요하다")
            raw_options = []
        for option_index, option in enumerate(raw_options):
            if (
                not isinstance(option, dict)
                or set(option) != {"value", "label"}
                or not isinstance(option.get("value"), str)
                or not isinstance(option.get("label"), str)
            ):
                problems.append(f"{label}.options[{option_index}]: {{value, label}} 두 키가 필요하다")
                continue
            options.append(PresurveyOption(value=option["value"], label=option["label"]))
    elif raw_options:
        problems.append(f"{label}.options: 척도 문항에는 선택지를 두지 않는다")

    reverse = raw.get("reverse", False)
    if not isinstance(reverse, bool):
        problems.append(f"{label}.reverse: bool이어야 한다")
        reverse = False

    return PresurveyItem(
        item_id=item_id,
        section=str(raw.get("section", "")),
        type=str(item_type),
        text=str(text),
        options=tuple(options),
        reverse=reverse,
    )


@lru_cache
def load() -> Presurvey:
    """자산 1건을 검증해서 로드한다. 계약 위반이면 `PresurveyContractError`."""
    path = asset_path()
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise PresurveyContractError(f"{path}: JSON 객체여야 한다")

    problems: list[str] = []
    version = document.get("version")
    if not isinstance(version, str) or not version:
        problems.append("version: 비어 있지 않은 문자열이어야 한다")
        version = ""

    raw_items = document.get("items")
    items: list[PresurveyItem] = []
    if not isinstance(raw_items, list) or not raw_items:
        problems.append("items: 1개 이상의 문항이 필요하다")
    else:
        seen: set[str] = set()
        for index, raw in enumerate(raw_items):
            parsed = _parse_item(index, raw, problems, seen)
            if parsed is not None:
                items.append(parsed)

    # §7.1 — 사전설문은 participant characterization 전용이다. 합산·소계 열이 자산에
    # 생기면 그 순간 moderator battery가 된다(초안 §7.4의 배제 결정).
    for banned in ("total", "subscales", "score", "sum"):
        if banned in document:
            problems.append(f"{banned}: 합산 필드는 두지 않는다 (§7.1)")

    if problems:
        joined = "\n  - ".join(problems)
        raise PresurveyContractError(f"{path} 자산 계약 위반 (§4.2):\n  - {joined}")
    return Presurvey(
        version=str(version),
        source_path=path,
        is_placeholder=path.name.endswith(PLACEHOLDER_SUFFIX),
        items=tuple(items),
    )


def validate() -> Presurvey:
    """기동 게이트 — dossier·문항 자산과 같은 자리에서 본다(§5.4)."""
    return load()


def reset_cache() -> None:
    load.cache_clear()
