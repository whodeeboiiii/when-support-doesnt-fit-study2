"""배정표 로더·검증 (구현명세서 §5.2 · §3.3 · §0.4 · NT-32).

**시스템은 배정을 계산하지 않는다.** 배정표(`assignments/assignment_v1.json`)를 읽을 뿐이고,
표는 오프라인 스크립트(`scripts/make_assignment.py`)가 seed·제약 로그와 함께 사전 생성한다
(D-30 · 초안 §7.2 restricted randomization 사전 명시). v1.0.1의 `core/williams.py`가 여기로
대체됐다 — 런타임에 조건을 산출하는 코드는 v2.0에 존재하지 않는다.

이 모듈이 하는 일은 둘이다.

1. **읽기** — 참가자 번호 → 배정 행(focal condition · 대안 노출 순서 · pair 순서 · 좌우).
2. **기동 시 전수 검증**(NT-32) — 24행·focal 6/조건·focal group 내 alt_order 6순열 각 1회·
   pair_order 6순열 각 4회·좌우 12/12·alt_order에 focal 미포함·strata 편중. 위반이면
   **기동을 실패시킨다**(§5.2 로더 항). 배정이 깨진 채 세션을 받으면 그 세션은 설계 밖이다.

`ASSIGNMENT_PATH` 미존재 시 `assignment_dummy.json`으로 내려가며 `is_dummy=True`로 표시한다
(§2.4·NT-42) — 콘솔 R1과 모집 게이트가 그 상태를 감출 수 없게 한다.

⚠ **`llm/`은 이 모듈을 import할 수 없다**(NT-04). 배정표는 §1.2 표에서 AI2·checker 전부
금지다 — 조건 라벨이 그 안에 있기 때문이다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from itertools import permutations
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.assets.dossier_loader import A_LEVELS, CONDITIONS, MISMATCH_LOCI

REPO_ROOT = Path(__file__).resolve().parents[3]

#: §5.2 — 실값(미커밋) · dummy(커밋). 실값이 없으면 dummy로 내려간다.
DEFAULT_ASSIGNMENT_PATH = REPO_ROOT / "assignments" / "assignment_v1.json"
DUMMY_ASSIGNMENT_PATH = REPO_ROOT / "assignments" / "assignment_dummy.json"

#: §0.4 — **N=24 고정, fallback 없음**(D-30).
EXPECTED_N = 24
#: §5.2 ① focal 6명/조건.
FOCAL_PER_CONDITION = EXPECTED_N // len(CONDITIONS)

#: §1.5-6 — 이 세 쌍만 존재한다. 코드에 다른 pair를 만들지 않는다.
CONTRASTS: tuple[str, ...] = ("sequence", "scope", "stopping")

#: §0.4 pairwise — Sequence(C2 vs C4) · Scope(C1 vs C3) · Stopping(C3 vs C4).
CONTRAST_PAIR: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "sequence": frozenset({"C2", "C4"}),
        "scope": frozenset({"C1", "C3"}),
        "stopping": frozenset({"C3", "C4"}),
    }
)

#: §5.2 ② focal group(6명)마다 나머지 세 조건의 순열 6종 각 1회.
ALT_ORDER_COUNT = 6
#: §5.2 ③ pair 순서 6종을 focal group마다 1:1 → 전체 각 4회.
PAIR_ORDER_REPEATS = EXPECTED_N // ALT_ORDER_COUNT

PAIR_ORDER_PERMUTATIONS: tuple[tuple[str, ...], ...] = tuple(permutations(CONTRASTS))

#: §5.2 ⑤ strata 편중 제약. "가능한 범위"이며 산술적으로 불가능하면 경고에 그친다.
STRATA_MAX_DIFF = 1


class AssignmentContractError(ValueError):
    """배정표 계약 위반 (NT-32). 기동 게이트가 이 예외로 기동을 끊는다."""


@dataclass(frozen=True, slots=True)
class AssignmentRow:
    """§5.2 스키마의 한 행 = 참가자 1명의 배정 전부."""

    participant_no: str
    a_level: str
    mismatch_locus: str
    focal_condition: str
    #: focal을 **제외한** 세 조건의 순열 (§3.3 — focal 포함이면 기동 실패).
    alt_order: tuple[str, ...]
    pair_order: tuple[str, ...]
    #: contrast → (left, right)
    pair_sides: Mapping[str, tuple[str, str]]

    def alt_condition(self, position: int) -> str:
        """§3.3 `alt_index` 1–3 → 그 위치에 표시할 대안 조건."""
        if not 1 <= position <= len(self.alt_order):
            raise KeyError(f"alt position 범위 밖: {position} (1–{len(self.alt_order)})")
        return self.alt_order[position - 1]

    def contrast_at(self, position: int) -> str:
        """§3.3 `pair_index` 1–3 → 그 위치의 contrast."""
        if not 1 <= position <= len(self.pair_order):
            raise KeyError(f"pair position 범위 밖: {position} (1–{len(self.pair_order)})")
        return self.pair_order[position - 1]

    def sides(self, contrast: str) -> tuple[str, str]:
        """§4.10 — (좌, 우). 어느 쪽이 focal인지는 여기서 말하지 않는다."""
        try:
            return self.pair_sides[contrast]
        except KeyError as exc:
            raise KeyError(f"알 수 없는 contrast: {contrast!r}") from exc

    def as_dict(self) -> dict[str, Any]:
        """콘솔 R1·R4·export용. **참가자 payload에는 나가지 않는다**(§1.2)."""
        return {
            "participant_no": self.participant_no,
            "a_level": self.a_level,
            "mismatch_locus": self.mismatch_locus,
            "focal_condition": self.focal_condition,
            "alt_order": list(self.alt_order),
            "pair_order": list(self.pair_order),
            "pair_sides": {key: list(value) for key, value in self.pair_sides.items()},
        }


@dataclass(frozen=True, slots=True)
class AssignmentTable:
    version: str
    generated_at: str
    seed: int
    is_dummy: bool
    source_path: Path
    rows: Mapping[str, AssignmentRow]
    constraints_checked: Mapping[str, Any]

    @property
    def participant_numbers(self) -> tuple[str, ...]:
        """§5.1 — 배정표의 행이 곧 참가자 목록이다."""
        return tuple(sorted(self.rows))

    def row(self, participant_no: str) -> AssignmentRow:
        try:
            return self.rows[participant_no]
        except KeyError as exc:
            raise KeyError(f"배정표에 없는 참가자: {participant_no!r} (§5.1)") from exc

    def has(self, participant_no: str) -> bool:
        return participant_no in self.rows


# --------------------------------------------------------------------------- #
# 파싱
# --------------------------------------------------------------------------- #


def assignment_path() -> tuple[Path, bool]:
    """(경로, is_dummy). §2.4 `ASSIGNMENT_PATH` → 실값 → dummy 순.

    ⚠ 오버라이드가 설정됐는데 그 파일이 없으면 **dummy로 내려가지 않고 끊는다**(PH-04).
    조용히 내려가면 오타 하나로 **더미 배정표를 실은 채 기동이 성공**한다. `is_dummy`가
    R1과 모집 게이트에 뜨긴 하지만, 명시적으로 경로를 지정한 설정이 무시되는 것 자체가
    사고다 — 지정했으면 그 파일이어야 한다.
    """
    override = os.environ.get("ASSIGNMENT_PATH", "").strip()
    if override:
        path = Path(override)
        if not path.is_file():
            raise AssignmentContractError(
                f"ASSIGNMENT_PATH={override!r} — 그런 파일이 없다 (§2.4 · PH-04). "
                "볼륨 마운트 경로를 확인하라. 값을 비우면 리포의 assignments/를 쓴다."
            )
        return path, False
    if DEFAULT_ASSIGNMENT_PATH.is_file():
        return DEFAULT_ASSIGNMENT_PATH, False
    if DUMMY_ASSIGNMENT_PATH.is_file():
        return DUMMY_ASSIGNMENT_PATH, True
    raise AssignmentContractError(
        f"배정표가 없다: {DEFAULT_ASSIGNMENT_PATH} 도 {DUMMY_ASSIGNMENT_PATH} 도 찾을 수 없다 "
        "(<TODO: PH-08 — 배정표 생성·동결>)"
    )


def _parse_row(raw: Any, index: int, problems: list[str]) -> AssignmentRow | None:
    label = f"rows[{index}]"
    if not isinstance(raw, dict):
        problems.append(f"{label}: 객체여야 한다")
        return None

    participant_no = str(raw.get("participant_no", "")).strip().upper()
    if not participant_no:
        problems.append(f"{label}.participant_no: 필수")
        return None

    a_level = raw.get("a_level")
    if a_level not in A_LEVELS:
        problems.append(f"{label}.a_level: {sorted(A_LEVELS)} 중 하나여야 한다")
        a_level = "A0"
    locus = raw.get("mismatch_locus")
    if locus not in MISMATCH_LOCI:
        problems.append(f"{label}.mismatch_locus: {sorted(MISMATCH_LOCI)} 중 하나여야 한다")
        locus = ""

    focal = raw.get("focal_condition")
    if focal not in CONDITIONS:
        problems.append(f"{label}.focal_condition: C1–C4 중 하나여야 한다")
        focal = CONDITIONS[0]

    alt_order = tuple(str(item) for item in raw.get("alt_order") or ())
    if sorted(alt_order) != sorted(set(CONDITIONS) - {focal}):
        # §3.3 — "배정표 행의 alt_order가 focal을 포함하면 로더가 기동을 끊는다"(NT-32).
        problems.append(
            f"{label}.alt_order: focal({focal})을 제외한 세 조건의 순열이어야 한다 — 실제 {list(alt_order)}"
        )

    pair_order = tuple(str(item) for item in raw.get("pair_order") or ())
    if sorted(pair_order) != sorted(CONTRASTS):
        problems.append(f"{label}.pair_order: {list(CONTRASTS)}의 순열이어야 한다")

    sides_raw = raw.get("pair_sides")
    sides: dict[str, tuple[str, str]] = {}
    if not isinstance(sides_raw, dict) or set(sides_raw) != set(CONTRASTS):
        problems.append(f"{label}.pair_sides: 세 contrast를 정확히 가져야 한다")
    else:
        for contrast, pair in sides_raw.items():
            if not isinstance(pair, list) or len(pair) != 2:
                problems.append(f"{label}.pair_sides.{contrast}: [left, right] 두 값이어야 한다")
                continue
            left, right = str(pair[0]), str(pair[1])
            if frozenset({left, right}) != CONTRAST_PAIR[contrast]:
                problems.append(
                    f"{label}.pair_sides.{contrast}: {sorted(CONTRAST_PAIR[contrast])} 두 조건이어야 한다 "
                    f"— 실제 {[left, right]} (§0.4)"
                )
            sides[str(contrast)] = (left, right)

    return AssignmentRow(
        participant_no=participant_no,
        a_level=str(a_level),
        mismatch_locus=str(locus),
        focal_condition=str(focal),
        alt_order=alt_order,
        pair_order=pair_order,
        pair_sides=MappingProxyType(sides),
    )


# --------------------------------------------------------------------------- #
# 제약 검증 (NT-32) — 생성 스크립트와 로더가 **같은 함수**를 쓴다
# --------------------------------------------------------------------------- #


def check_constraints(rows: Sequence[AssignmentRow], *, strict_n: bool = True) -> list[str]:
    """§5.2 제약 전수 검증. 위반 사유 목록을 돌려준다(빈 목록 = 통과).

    생성 스크립트(`--self-test`)와 기동 로더가 이 함수를 공유한다 — 생성이 통과시킨 표를
    로더가 거부하거나 그 반대가 되면, 어느 쪽이 정본인지 알 수 없어진다.

    `strict_n=False`는 self-test에서 부분 표를 볼 때만 쓴다.
    """
    problems: list[str] = []

    numbers = [row.participant_no for row in rows]
    duplicates = sorted({no for no in numbers if numbers.count(no) > 1})
    if duplicates:
        problems.append(f"참가자 번호 중복: {duplicates}")

    if strict_n and len(rows) != EXPECTED_N:
        problems.append(f"행 수 {len(rows)} — N={EXPECTED_N} 고정이다 (D-30)")

    # ① focal 균등 — 조건당 6명.
    by_focal: dict[str, list[AssignmentRow]] = {condition: [] for condition in CONDITIONS}
    for row in rows:
        by_focal.setdefault(row.focal_condition, []).append(row)
    if strict_n:
        for condition in CONDITIONS:
            count = len(by_focal.get(condition, []))
            if count != FOCAL_PER_CONDITION:
                problems.append(
                    f"focal {condition}: {count}명 — 조건당 {FOCAL_PER_CONDITION}명이어야 한다 (§5.2 ①)"
                )

    # ② focal group 내 alt_order 6순열 각 1회.
    for condition, group in sorted(by_focal.items()):
        if not group:
            continue
        orders = [row.alt_order for row in group]
        expected = set(permutations(sorted(set(CONDITIONS) - {condition})))
        if strict_n and (len(orders) != len(set(orders)) or set(orders) != expected):
            problems.append(
                f"focal {condition}: alt_order 6순열이 각 1회여야 한다 (§5.2 ② · NT-32) — "
                f"실제 {len(set(orders))}종"
            )

    # ③ pair_order 6순열 각 4회 (focal group마다 1:1).
    if strict_n:
        for condition, group in sorted(by_focal.items()):
            orders = [row.pair_order for row in group]
            if sorted(orders) != sorted(PAIR_ORDER_PERMUTATIONS):
                problems.append(
                    f"focal {condition}: pair_order 6순열이 각 1회여야 한다 (§5.2 ③)"
                )
        counts = {perm: 0 for perm in PAIR_ORDER_PERMUTATIONS}
        for row in rows:
            if row.pair_order in counts:
                counts[row.pair_order] += 1
        off = {perm: n for perm, n in counts.items() if n != PAIR_ORDER_REPEATS}
        if off:
            problems.append(
                f"pair_order 전체 분포: 각 {PAIR_ORDER_REPEATS}회여야 한다 — 어긋난 순열 {len(off)}종 (NT-32)"
            )

    # ④ 좌우 균형 — contrast별 전체 12/12, focal group 내 3/3.
    if strict_n:
        for contrast in CONTRASTS:
            first = sorted(CONTRAST_PAIR[contrast])[0]
            left_total = sum(1 for row in rows if row.pair_sides.get(contrast, ("",))[0] == first)
            if left_total != EXPECTED_N // 2:
                problems.append(
                    f"좌우 균형 {contrast}: {first}이 좌측인 행 {left_total} — "
                    f"{EXPECTED_N // 2}이어야 한다 (§5.2 ④)"
                )
            for condition, group in sorted(by_focal.items()):
                if not group:
                    continue
                left_group = sum(
                    1 for row in group if row.pair_sides.get(contrast, ("",))[0] == first
                )
                if left_group != len(group) // 2:
                    problems.append(
                        f"좌우 균형 {contrast} (focal {condition}): {left_group}/{len(group)} — "
                        f"{len(group) // 2}이어야 한다 (§5.2 ④)"
                    )

    return problems


def strata_spread(rows: Sequence[AssignmentRow]) -> dict[str, Any]:
    """§5.2 ⑤ strata 편중 — 산술적으로 불가능하면 **경고**이지 오류가 아니다.

    A0가 1–2건이면 네 조건 분산이 불가능하다(§5.2). 스크립트는 이를 로그의 경고로 남기고,
    로더는 기동을 끊지 않는다 — 표본이 그렇게 생긴 것을 시스템이 판정할 일이 아니다.
    """
    report: dict[str, Any] = {"a_level": {}, "warnings": []}
    for a_level in sorted(A_LEVELS):
        members = [row for row in rows if row.a_level == a_level]
        if not members:
            continue
        counts = {
            condition: sum(1 for row in members if row.focal_condition == condition)
            for condition in CONDITIONS
        }
        diff = max(counts.values()) - min(counts.values())
        report["a_level"][a_level] = {"counts": counts, "n": len(members), "max_diff": diff}
        if diff > STRATA_MAX_DIFF:
            report["warnings"].append(
                f"{a_level}: n={len(members)}이라 조건 간 max−min={diff} "
                f"(목표 ≤{STRATA_MAX_DIFF} — §5.2 ⑤ '가능한 범위')"
            )
    return report


# --------------------------------------------------------------------------- #
# 로드
# --------------------------------------------------------------------------- #


def parse(document: Mapping[str, Any], *, source_path: Path, is_dummy: bool) -> AssignmentTable:
    """문서 → 표. 계약 위반이면 `AssignmentContractError`."""
    problems: list[str] = []
    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list):
        raise AssignmentContractError(f"{source_path}: rows 배열이 없다 (§5.2)")

    parsed = [
        row
        for row in (_parse_row(raw, index, problems) for index, raw in enumerate(raw_rows))
        if row is not None
    ]
    problems.extend(check_constraints(parsed))
    if problems:
        joined = "\n  - ".join(problems)
        raise AssignmentContractError(
            f"{source_path} 배정표 계약 위반 (§5.2 · NT-32):\n  - {joined}"
        )

    return AssignmentTable(
        version=str(document.get("version", "")),
        generated_at=str(document.get("generated_at", "")),
        seed=int(document.get("seed", 0)),
        is_dummy=is_dummy,
        source_path=source_path,
        rows=MappingProxyType({row.participant_no: row for row in parsed}),
        constraints_checked=MappingProxyType(dict(document.get("constraints_checked") or {})),
    )


@lru_cache
def load() -> AssignmentTable:
    """§5.2 로더 — 기동 시 제약 전수 검증(NT-32). 위반이면 기동 실패."""
    path, is_dummy = assignment_path()
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssignmentContractError(f"{path}: 배정표는 JSON 객체여야 한다")
    return parse(document, source_path=path, is_dummy=is_dummy)


def validate() -> AssignmentTable:
    """§5.4 기동 게이트에서 부르는 이름."""
    return load()


def reset_cache() -> None:
    load.cache_clear()
