"""first-opportunity · carryover 태깅 플래그 (구현명세서 §7.6 · 부록 B · NT-30).

§7.6이 요구하는 것은 **분석이 쓸 플래그 열**이지 자동 판정이 아니다. 그 구분이 이 모듈의
전부다.

| 플래그 | 산출 방식 |
|---|---|
| `first_opportunity` | 기계적 — 네 branch가 같은 사건을 반복하므로 **첫 표현 기회는 branch 1**이다 |
| `carryover_sensitive` | **사후 코딩 입력이 있어야** 산출된다 — "이전 branch에서 실질 동일 내용이 표현됐는가"는 사람의 판정이다(§7.6 sensitizing categories와 같은 층) |
| sensitivity 서브셋 | 기계적 — first-branch only / 첫 2 branch / first-opportunity / sequence별 |

`carryover_sensitive`를 코딩 없이 추정하지 않는 이유: 문자열 유사도로 "실질 동일 내용"을
판정하면 그 판정이 곧 결과 변수(§7.4 disposition·downstream)와 상관되는 측정 오차가 된다.
코딩이 없으면 열은 **빈 값**으로 남고 `carryover_source`가 `uncoded`라고 말한다 — 빈 값은
"아니오"가 아니다(§7.2 "부재≠정보 없음"과 같은 규율).

코딩 입력 형식(CSV):

    participant_no,branch_index,focal_content_expressed
    P01,1,true
    P01,2,false

`focal_content_expressed` = 그 branch에서 dossier `focal_repair_relevant_content`에 해당하는
내용이 표현됐는가(2인 코딩 결과). 이 파일은 시스템 밖에서 만든다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

#: §7.6 — 표현 코딩이 없을 때 `carryover_sensitive` 열이 말하는 것.
UNCODED = "uncoded"
CODED = "coded"

TRUE_TOKENS = frozenset({"1", "true", "t", "yes", "y", "예", "참"})
FALSE_TOKENS = frozenset({"0", "false", "f", "no", "n", "아니오", "거짓"})

#: 코딩 CSV의 필수 열.
CODING_COLUMNS = ("participant_no", "branch_index", "focal_content_expressed")


class CodingInputError(ValueError):
    """코딩 파일 형식 오류 — 조용히 무시하지 않는다(빈 코딩과 잘못된 코딩은 다르다)."""


@dataclass(frozen=True, slots=True)
class BranchFlags:
    """branch 1건의 태깅 플래그 (부록 B의 `first_opportunity`·`carryover_sensitive` 자리)."""

    first_opportunity: bool
    carryover_sensitive: bool | None
    carryover_source: str
    subset_first_branch_only: bool
    subset_first_two_branches: bool

    def as_row(self) -> dict[str, object]:
        return {
            "first_opportunity": self.first_opportunity,
            # None은 빈 칸으로 나간다 — False가 아니다.
            "carryover_sensitive": "" if self.carryover_sensitive is None else self.carryover_sensitive,
            "carryover_source": self.carryover_source,
            "subset_first_branch_only": self.subset_first_branch_only,
            "subset_first_two_branches": self.subset_first_two_branches,
        }


#: export가 반드시 실어야 하는 플래그 열 (NT-30).
FLAG_COLUMNS: tuple[str, ...] = tuple(
    BranchFlags(True, None, UNCODED, True, True).as_row().keys()
)


def _parse_bool(raw: str, where: str) -> bool:
    token = raw.strip().lower()
    if token in TRUE_TOKENS:
        return True
    if token in FALSE_TOKENS:
        return False
    raise CodingInputError(f"{where}: 참/거짓으로 읽을 수 없다 — {raw!r}")


def load_coding(path: Path) -> dict[tuple[str, int], bool]:
    """코딩 CSV → {(참가자, branch): 표현됨}."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in CODING_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise CodingInputError(f"{path}: 필수 열 누락 — {missing}")
        coding: dict[tuple[str, int], bool] = {}
        for line, row in enumerate(reader, start=2):
            participant_no = (row["participant_no"] or "").strip().upper()
            try:
                branch_index = int(row["branch_index"])
            except (TypeError, ValueError) as exc:
                raise CodingInputError(f"{path}:{line}: branch_index가 정수가 아니다") from exc
            coding[(participant_no, branch_index)] = _parse_bool(
                row["focal_content_expressed"] or "", f"{path}:{line}"
            )
    return coding


def flags_for(
    participant_no: str,
    branch_index: int,
    coding: Mapping[tuple[str, int], bool] | None = None,
) -> BranchFlags:
    """branch 1건의 플래그 (§7.6).

    `carryover_sensitive`는 **이전 branch 전부가 코딩돼 있을 때만** 산출한다 — 하나라도
    비어 있으면 "표현된 적 없음"인지 "아직 코딩 안 됨"인지 구분할 수 없다.
    """
    first_opportunity = branch_index == 1
    carryover: bool | None = None
    source = UNCODED
    if coding is not None:
        earlier = [(participant_no, index) for index in range(1, branch_index)]
        if all(key in coding for key in earlier):
            carryover = any(coding[key] for key in earlier)
            source = CODED
    return BranchFlags(
        first_opportunity=first_opportunity,
        carryover_sensitive=carryover,
        carryover_source=source,
        subset_first_branch_only=branch_index == 1,
        subset_first_two_branches=branch_index <= 2,
    )


def annotate(
    rows: Iterable[dict[str, object]],
    coding: Mapping[tuple[str, int], bool] | None = None,
) -> list[dict[str, object]]:
    """export 행 목록에 플래그 열을 붙인다. 행은 `participant_no`·`branch_index`를 가져야 한다."""
    annotated: list[dict[str, object]] = []
    for row in rows:
        flags = flags_for(str(row["participant_no"]), int(row["branch_index"]), coding)
        annotated.append({**row, **flags.as_row()})
    return annotated
