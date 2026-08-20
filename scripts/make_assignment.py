"""배정표 생성 (구현명세서 §5.2 · §10.1 · D-30 · NT-32).

    # dossier에서 strata를 읽어 실값 배정표를 만든다
    python scripts/make_assignment.py --from-dossiers --seed 20260820 --out assignments/assignment_v1.json

    # CSV로 strata를 주는 경우 (participant_no,a_level,mismatch_locus)
    python scripts/make_assignment.py --strata strata.csv --seed 20260820 --out assignments/assignment_v1.json

    # dummy 표 재생성 (P01–P24, 결정론 seed)
    python scripts/make_assignment.py --dummy

    # §10.1 — 임의 strata 분포 20종에 대해 제약 전수 통과 확인
    python scripts/make_assignment.py --self-test

**이 스크립트는 오프라인 도구다.** 런타임은 결과 파일을 읽기만 한다(§0.3 — "배정을 계산하지
않는다"). 배정표는 **생성 후 금지**이고 재생성은 새 seed·새 버전·전원 재배정을 뜻하며
모집 전에만 가능하다(§1.4).

§5.2의 절차를 그대로 옮긴다.

    ① focal 배정 — restricted randomization: 각 A-level의 참가자를 네 조건에 가능한 한
      균등(조건 간 max−min ≤ 1)하게, 동률이면 mismatch_locus 편중 최소화, 그 안에서 seed 무작위
    ② focal group(6명)마다 나머지 세 조건의 순열 6종을 무작위 1:1 배정
    ③ pair 순서 6종을 focal group마다 1:1(전체 각 4회)
    ④ 좌우: contrast별로 전체 12/12, focal group 내 3/3
    ⑤ 제약 전수 재검증 → 실패 시 seed+1 재시도(재시도 횟수 기록)
    ⑥ 생성 로그(`assignment_v1.log`: seed, 시도 횟수, strata 분포표)를 함께 산출

**배정표는 dossier보다 먼저 동결된다** — 그러나 strata 입력(a_level)은 lock된 dossier에서
나온다(§5.2 마지막 항). `--from-dossiers`가 그 경로다.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from itertools import permutations
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assets.dossier_loader import CONDITIONS  # noqa: E402
from app.assets.files import DUMMY_PARTICIPANT_NUMBERS  # noqa: E402
from app.core.assignment import (  # noqa: E402
    CONTRAST_PAIR,
    CONTRASTS,
    EXPECTED_N,
    AssignmentRow,
    check_constraints,
    strata_spread,
)

#: §5.2 ⑤ — 제약 실패 시 seed+1로 재시도. 상한을 두는 이유는 무한 루프 방지뿐이다.
MAX_SEED_RETRIES = 200

DUMMY_SEED = 20260820
DUMMY_OUT = REPO_ROOT / "assignments" / "assignment_dummy.json"


# --------------------------------------------------------------------------- #
# strata 입력
# --------------------------------------------------------------------------- #


def strata_from_csv(path: Path) -> list[dict[str, str]]:
    """`participant_no,a_level,mismatch_locus` 세 열."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    missing = [row for row in rows if not row.get("participant_no")]
    if missing:
        raise SystemExit(f"{path}: participant_no가 빈 행이 있다")
    return [
        {
            "participant_no": row["participant_no"].strip().upper(),
            "a_level": (row.get("a_level") or "").strip(),
            "mismatch_locus": (row.get("mismatch_locus") or "").strip(),
        }
        for row in rows
    ]


def strata_from_dossiers(participant_numbers: Sequence[str] | None = None) -> list[dict[str, str]]:
    """§5.2 — lock된 dossier의 `evidence_code`에서 a_level·locus를 뽑는다."""
    from app.assets import dossier_loader
    from app.assets.files import QA_PARTICIPANT_NO, available_participant_numbers

    numbers = participant_numbers or [
        no for no in available_participant_numbers() if no != QA_PARTICIPANT_NO
    ]
    rows: list[dict[str, str]] = []
    for participant_no in numbers:
        dossier = dossier_loader.load(participant_no)
        rows.append(
            {
                "participant_no": participant_no,
                "a_level": dossier.evidence_code.a_level,
                "mismatch_locus": dossier.evidence_code.mismatch_locus,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# ① focal 배정 — restricted randomization
# --------------------------------------------------------------------------- #


def _assign_focal(strata: Sequence[dict[str, str]], rng: random.Random) -> dict[str, str]:
    """A-level 안에서 네 조건에 가능한 한 균등하게, locus 편중을 최소화하며 배정한다.

    구현은 탐욕적이다: 각 참가자를 볼 때 ① 전체에서 가장 덜 쓰인 조건들 중 ② 그 참가자의
    locus가 가장 덜 들어간 조건을 고르고 ③ 동률이면 seed 무작위로 정한다. 매 단계에서
    max−min ≤ 1을 유지하므로 결과가 §5.2 ①의 균등 요건을 만족한다.

    A-level별로 따로 도는 이유는 §5.2가 "각 A-level의 참가자를 네 조건에" 배정하라고 했기
    때문이다 — 전체 균등만 맞추면 A-level이 조건에 쏠릴 수 있다.
    """
    focal: dict[str, str] = {}
    overall = Counter({condition: 0 for condition in CONDITIONS})
    locus_use: dict[str, Counter] = {}

    by_level: dict[str, list[dict[str, str]]] = {}
    for row in strata:
        by_level.setdefault(row["a_level"], []).append(row)

    for a_level in sorted(by_level):
        members = list(by_level[a_level])
        rng.shuffle(members)
        level_counts = Counter({condition: 0 for condition in CONDITIONS})
        for row in members:
            locus = row["mismatch_locus"]
            counter = locus_use.setdefault(locus, Counter({c: 0 for c in CONDITIONS}))

            # ① A-level 안에서 가장 덜 쓰인 조건 → ② 전체에서 덜 쓰인 → ③ locus 편중 최소
            best = min(level_counts.values())
            candidates = [c for c in CONDITIONS if level_counts[c] == best]
            best = min(overall[c] for c in candidates)
            candidates = [c for c in candidates if overall[c] == best]
            best = min(counter[c] for c in candidates)
            candidates = [c for c in candidates if counter[c] == best]

            chosen = rng.choice(sorted(candidates))
            focal[row["participant_no"]] = chosen
            level_counts[chosen] += 1
            overall[chosen] += 1
            counter[chosen] += 1
    return focal


# --------------------------------------------------------------------------- #
# ②③④ 순열·좌우
# --------------------------------------------------------------------------- #


def _build_rows(
    strata: Sequence[dict[str, str]], focal: dict[str, str], rng: random.Random
) -> list[AssignmentRow]:
    by_focal: dict[str, list[dict[str, str]]] = {condition: [] for condition in CONDITIONS}
    for row in strata:
        by_focal[focal[row["participant_no"]]].append(row)

    pair_orders = list(permutations(CONTRASTS))
    rows: list[AssignmentRow] = []

    for condition in CONDITIONS:
        group = sorted(by_focal[condition], key=lambda item: item["participant_no"])
        rng.shuffle(group)

        # ② 나머지 세 조건의 순열 6종을 group에 1:1.
        alt_orders = list(permutations(sorted(set(CONDITIONS) - {condition})))
        rng.shuffle(alt_orders)
        # ③ pair 순서 6종도 group에 1:1 → 네 group 합계 각 4회.
        group_pair_orders = list(pair_orders)
        rng.shuffle(group_pair_orders)

        # ④ 좌우: group 내 3/3. contrast마다 절반은 뒤집는다.
        flips: dict[str, list[bool]] = {}
        for contrast in CONTRASTS:
            pattern = [False] * (len(group) // 2) + [True] * (len(group) - len(group) // 2)
            rng.shuffle(pattern)
            flips[contrast] = pattern

        for index, member in enumerate(group):
            sides: dict[str, tuple[str, str]] = {}
            for contrast in CONTRASTS:
                first, second = sorted(CONTRAST_PAIR[contrast])
                sides[contrast] = (
                    (second, first) if flips[contrast][index] else (first, second)
                )
            rows.append(
                AssignmentRow(
                    participant_no=member["participant_no"],
                    a_level=member["a_level"],
                    mismatch_locus=member["mismatch_locus"],
                    focal_condition=condition,
                    alt_order=alt_orders[index % len(alt_orders)],
                    pair_order=group_pair_orders[index % len(group_pair_orders)],
                    pair_sides=sides,
                )
            )
    return sorted(rows, key=lambda row: row.participant_no)


def generate(
    strata: Sequence[dict[str, str]], seed: int
) -> tuple[list[AssignmentRow], int, int]:
    """§5.2 ①–⑤. 반환 = (행, 실제 쓰인 seed, 시도 횟수).

    제약 검증에 실패하면 seed+1로 재시도한다 — 탐욕 배정 + 무작위 순열 조합이 드물게
    좌우 균형을 못 맞출 수 있어서다. 어느 seed가 쓰였는지는 결과와 로그에 남는다(§5.2 ⑥).
    """
    strict = len(strata) == EXPECTED_N
    for attempt in range(MAX_SEED_RETRIES):
        current = seed + attempt
        rng = random.Random(current)
        focal = _assign_focal(strata, rng)
        rows = _build_rows(strata, focal, rng)
        if not check_constraints(rows, strict_n=strict):
            return rows, current, attempt + 1
    raise SystemExit(
        f"seed {seed}부터 {MAX_SEED_RETRIES}회 시도했지만 §5.2 제약을 만족하는 표를 만들지 못했다. "
        "strata 분포를 확인하라."
    )


# --------------------------------------------------------------------------- #
# 출력
# --------------------------------------------------------------------------- #


def _document(rows: Sequence[AssignmentRow], *, version: str, seed: int, now: str) -> dict[str, Any]:
    problems = check_constraints(rows, strict_n=len(rows) == EXPECTED_N)
    return {
        "version": version,
        "generated_at": now,
        "seed": seed,
        "n": len(rows),
        "constraints_checked": {
            "focal_balance": not problems,
            "alt_order_latin": not problems,
            "pair_order_4x": not problems,
            "side_balance": not problems,
            "strata_spread": f"max_diff<={_max_diff(rows)}",
        },
        "rows": [row.as_dict() for row in rows],
    }


def _max_diff(rows: Sequence[AssignmentRow]) -> int:
    report = strata_spread(rows)
    diffs = [entry["max_diff"] for entry in report["a_level"].values()]
    return max(diffs) if diffs else 0


def _log(rows: Sequence[AssignmentRow], *, seed: int, attempts: int, now: str) -> str:
    report = strata_spread(rows)
    lines = [
        f"# 배정표 생성 로그 (§5.2 ⑥) — {now}",
        f"seed: {seed}",
        f"시도 횟수: {attempts}",
        f"n: {len(rows)}",
        "",
        "## focal 분포",
    ]
    focal_counts = Counter(row.focal_condition for row in rows)
    for condition in CONDITIONS:
        lines.append(f"- {condition}: {focal_counts[condition]}명")

    lines += ["", "## strata 분포 (A-level × focal condition)"]
    for a_level, entry in sorted(report["a_level"].items()):
        counts = " · ".join(f"{c}={entry['counts'][c]}" for c in CONDITIONS)
        lines.append(f"- {a_level} (n={entry['n']}): {counts} — max−min={entry['max_diff']}")

    lines += ["", "## mismatch_locus 분포"]
    for locus, count in sorted(Counter(row.mismatch_locus for row in rows).items()):
        lines.append(f"- {locus}: {count}명")

    if report["warnings"]:
        lines += ["", "## 경고 (§5.2 — '심한 편중 방지'는 가능한 범위)"]
        lines += [f"- {warning}" for warning in report["warnings"]]

    problems = check_constraints(rows, strict_n=len(rows) == EXPECTED_N)
    lines += ["", "## 제약 재검증 (NT-32)"]
    lines += [f"- ❌ {problem}" for problem in problems] or ["- ✅ 전 제약 통과"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# self-test (§10.1)
# --------------------------------------------------------------------------- #


def self_test() -> int:
    """임의 strata 분포 20종에 대해 제약 전수 통과 (NT-32).

    분포를 일부러 비틀어 본다 — A-level이 한쪽에 쏠린 경우(§5.2의 "A0가 1–2건")까지 포함해서
    **제약 검증이 통과하는지**를 본다. strata 편중은 경고이지 오류가 아니므로, 통과 기준은
    focal 균등·순열·좌우이고 편중은 로그에만 남는다.
    """
    from app.assets.dossier_loader import MISMATCH_LOCI

    loci = sorted(MISMATCH_LOCI)
    failures: list[str] = []
    for case in range(20):
        rng = random.Random(9_000 + case)
        # A-level 구성을 case마다 다르게 — 극단(A0=1)도 포함한다.
        if case % 4 == 0:
            levels = ["A0"] * 1 + ["A1"] * 11 + ["A2"] * 12
        elif case % 4 == 1:
            levels = ["A0"] * 8 + ["A1"] * 8 + ["A2"] * 8
        elif case % 4 == 2:
            levels = ["A2"] * EXPECTED_N
        else:
            levels = [rng.choice(["A0", "A1", "A2"]) for _ in range(EXPECTED_N)]
        rng.shuffle(levels)
        strata = [
            {
                "participant_no": f"P{n:02d}",
                "a_level": levels[n - 1],
                "mismatch_locus": rng.choice(loci),
            }
            for n in range(1, EXPECTED_N + 1)
        ]
        rows, seed, attempts = generate(strata, 20_260_820 + case)
        problems = check_constraints(rows)
        if problems:
            failures.append(f"case {case} (seed {seed}, {attempts}회): {problems}")
        else:
            warnings = strata_spread(rows)["warnings"]
            note = f" · 경고 {len(warnings)}건" if warnings else ""
            print(f"  case {case:2d}: ✅ seed {seed} ({attempts}회){note}")

    if failures:
        print("\n실패:")
        for failure in failures:
            print(f"  ❌ {failure}")
        return 1
    print("\nself-test 20/20 통과 (NT-32)")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _dummy_strata() -> list[dict[str, str]]:
    """dummy 표(P01–P24)의 strata — schema_dummy dossier에서 읽는다."""
    return strata_from_dossiers(DUMMY_PARTICIPANT_NUMBERS)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배정표 생성 (§5.2)")
    parser.add_argument("--strata", type=Path, help="participant_no,a_level,mismatch_locus CSV")
    parser.add_argument("--from-dossiers", action="store_true", help="lock된 dossier에서 strata 추출")
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "assignments" / "assignment_v1.json")
    parser.add_argument("--version", default="assignment_v1")
    parser.add_argument("--dummy", action="store_true", help="assignment_dummy.json 재생성")
    parser.add_argument("--self-test", action="store_true", help="§10.1 제약 self-test 20종")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.dummy:
        strata = _dummy_strata()
        seed, out, version = DUMMY_SEED, DUMMY_OUT, "assignment_dummy"
    elif args.from_dossiers:
        strata, seed, out, version = strata_from_dossiers(), args.seed, args.out, args.version
    elif args.strata:
        strata, seed, out, version = strata_from_csv(args.strata), args.seed, args.out, args.version
    else:
        parser.error("--strata · --from-dossiers · --dummy · --self-test 중 하나가 필요하다")

    if len(strata) != EXPECTED_N:
        print(
            f"⚠ strata {len(strata)}건 — N={EXPECTED_N} 고정이다(D-30). "
            "제약 검증이 부분 모드로 돈다.",
            file=sys.stderr,
        )

    rows, used_seed, attempts = generate(strata, seed)
    now = datetime.now(UTC).isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(_document(rows, version=version, seed=used_seed, now=now), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    log_path = out.with_suffix(".log")
    log_path.write_text(_log(rows, seed=used_seed, attempts=attempts, now=now), encoding="utf-8")
    print(f"배정표 {len(rows)}행 → {out}")
    print(f"생성 로그 → {log_path}  (seed {used_seed}, {attempts}회 시도)")
    for warning in strata_spread(rows)["warnings"]:
        print(f"  ⚠ {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
