"""referential normalization — 규칙 기반 자동 (구현명세서 §6.4 · 부록 A.3 · D-04/O-3).

**왜 있는가**: §0.4가 AI1 원문을 AI2 payload에서 제외했다. 그러면 "응, 그렇게 해줘"의 지시
대상이 사라진다. 이 모듈은 그 지시만 복원한다 — 의미를 보태지 않는다.

**입력은 셋뿐이다**(NT-03): `user1` 원문, 해당 참가자의 `referent_map`, config의 지시표현 패턴
목록. dossier의 다른 층·타 branch·sidecar·조건 라벨은 이 함수의 시그니처에 존재하지 않는다.
"들어오지 않게 조심한다"가 아니라 **받을 자리가 없다**.

**판정은 셋 중 하나다**(§6.4-③).
- 유일 매칭 → 해당 proposition으로 **최소 치환**
- 복수 referent 지시(NP-03) → 전 proposition 병기 치환
- 다의·무매칭 → **치환하지 않는다**(NP-04, ambiguity 유지). 임의 보완은 금지다.

전 조건 동일 규칙이다(NT-11) — 이 모듈은 condition·branch_index·sequence를 인자로 받지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from app.llm import prompts

REPO_ROOT = Path(__file__).resolve().parents[3]
PATTERNS_PATH = REPO_ROOT / "fixtures" / "normalization_patterns_v1.json"

#: 부록 A.3 — 매칭 없음·다의 해소 불가. 패턴이 아니라 "치환하지 않음"의 결과 코드다.
NO_SUBSTITUTION_ID = "NP-04"

#: 부록 A.3 치환 결과 형식. 원문 병기로 **정보 추가 없이 지시만 복원**한다.
NORMALIZED_TEMPLATE = '사용자 메시지(정규화): "{substituted}" (원문: "{raw}")'

#: 병기 치환(NP-03)의 연결자. 접속사를 넣으면 없던 의미 관계가 생기므로 구두점만 쓴다.
MULTI_JOINER = ", "


class PatternAssetError(ValueError):
    """패턴 자산 계약 위반 — 기동 게이트에서 끊는다(§5.4와 같은 지위)."""


@dataclass(frozen=True, slots=True)
class ReferringPattern:
    id: str
    regex: re.Pattern[str]
    #: single = referent 1개 지시 / multi = 복수 referent 지시(NP-03)
    mode: str


@dataclass(frozen=True, slots=True)
class Referent:
    """`derivation.referent_map` 1건 + 안정적인 id.

    id는 자산 순서에서 파생한다(`R-01`, `R-02`, …). §5.2 스키마에 id 필드가 없고, §8.1
    `normalizations.referent_id`는 값을 요구하기 때문이다. 자산의 순서를 바꾸면 id가 바뀌므로
    lock 이후에는 순서도 고정 대상이다(§1.4).
    """

    id: str
    patterns: tuple[str, ...]
    proposition: str


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """§8.1 `normalizations` 1행 + payload에 실릴 문자열."""

    applied: bool
    #: AI2 payload에 들어갈 문자열. 치환했으면 A.3 형식(원문 병기), 아니면 원문 그대로.
    text: str
    #: 치환문(치환한 경우에만). 원문은 호출부가 이미 갖고 있다.
    substituted: str | None
    matched_pattern_id: str
    referent_id: str | None


@lru_cache
def load_patterns() -> tuple[ReferringPattern, ...]:
    """부록 A.3 패턴 목록. 버전은 prompt_config가 기록한 값과 일치해야 한다(§6.7)."""
    if not PATTERNS_PATH.is_file():
        raise PatternAssetError(f"패턴 자산이 없다: {PATTERNS_PATH}")
    document = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
    expected_version = prompts.config().get("normalization_patterns_version")
    if document.get("version") != expected_version:
        raise PatternAssetError(
            f"패턴 자산 버전 불일치 — 자산 {document.get('version')!r} vs "
            f"prompt_config {expected_version!r} (§6.7 재현성)"
        )
    patterns: list[ReferringPattern] = []
    for index, raw in enumerate(document.get("patterns", [])):
        if not isinstance(raw, dict) or not {"id", "regex", "mode"} <= set(raw):
            raise PatternAssetError(f"patterns[{index}]: {{id, regex, mode}}가 필요하다")
        if raw["mode"] not in {"single", "multi"}:
            raise PatternAssetError(f"patterns[{index}].mode: single 또는 multi여야 한다")
        if raw["id"] == NO_SUBSTITUTION_ID:
            raise PatternAssetError(
                f"{NO_SUBSTITUTION_ID}는 패턴이 아니라 '치환하지 않음'의 결과 코드다 (부록 A.3)"
            )
        try:
            compiled = re.compile(raw["regex"])
        except re.error as exc:
            raise PatternAssetError(f"patterns[{index}].regex: 정규식이 아니다 — {exc}") from exc
        patterns.append(ReferringPattern(id=str(raw["id"]), regex=compiled, mode=str(raw["mode"])))
    if not patterns:
        raise PatternAssetError("패턴이 하나도 없다 (부록 A.3)")
    return tuple(patterns)


def validate_patterns() -> tuple[ReferringPattern, ...]:
    """기동 게이트에서 호출한다 — 자산이 깨진 채로 세션을 받지 않는다(§5.4)."""
    return load_patterns()


def reset_cache() -> None:
    load_patterns.cache_clear()


def referents_from(referent_map: Sequence[object]) -> tuple[Referent, ...]:
    """dossier의 `referent_map`(patterns·proposition)에 순서 기반 id를 붙인다."""
    referents: list[Referent] = []
    for index, entry in enumerate(referent_map, start=1):
        patterns = tuple(getattr(entry, "patterns", ()))
        proposition = str(getattr(entry, "proposition", ""))
        referents.append(Referent(id=f"R-{index:02d}", patterns=patterns, proposition=proposition))
    return tuple(referents)


def _matching_referents(user1: str, referents: Sequence[Referent]) -> list[tuple[Referent, str]]:
    """user1 안에 등장하는 지시표현을 가진 referent들. (referent, 매칭된 표면형) 목록."""
    matches: list[tuple[Referent, str]] = []
    for referent in referents:
        present = [pattern for pattern in referent.patterns if pattern and pattern in user1]
        if present:
            # 최소 치환을 위해 **가장 긴** 표면형을 쓴다 — 짧은 조각만 바꾸면 문장이 깨진다.
            matches.append((referent, max(present, key=len)))
    return matches


def _no_substitution(user1: str) -> NormalizationResult:
    return NormalizationResult(
        applied=False,
        text=user1,
        substituted=None,
        matched_pattern_id=NO_SUBSTITUTION_ID,
        referent_id=None,
    )


def normalize(user1: str, referent_map: Sequence[object]) -> NormalizationResult:
    """§6.4 — 지시 복원 1회. 입력은 {user1, referent_map, patterns}뿐이다(NT-03).

    조건·branch를 인자로 받지 않으므로 전 조건에서 같은 입력은 같은 출력이다(NT-11).
    """
    raw = user1.strip()
    if not raw:
        return _no_substitution(user1)

    referents = referents_from(referent_map)
    for pattern in load_patterns():
        match = pattern.regex.search(raw)
        if not match:
            continue

        if pattern.mode == "multi":
            if len(referents) < 2:
                # "둘 다"가 가리킬 대상이 둘이 아니다 — 해소 불가이므로 그대로 둔다.
                return _no_substitution(user1)
            substituted = raw.replace(
                match.group(0), MULTI_JOINER.join(r.proposition for r in referents), 1
            )
            referent_id = "+".join(r.id for r in referents)
        else:
            matches = _matching_referents(raw, referents)
            if len(matches) != 1:
                # 0건 = 무매칭, 2건 이상 = 다의. 둘 다 §6.4의 "치환하지 않음"이다.
                return _no_substitution(user1)
            referent, surface = matches[0]
            substituted = raw.replace(surface, referent.proposition, 1)
            referent_id = referent.id

        return NormalizationResult(
            applied=True,
            text=NORMALIZED_TEMPLATE.format(substituted=substituted, raw=raw),
            substituted=substituted,
            matched_pattern_id=pattern.id,
            referent_id=referent_id,
        )

    return _no_substitution(user1)
