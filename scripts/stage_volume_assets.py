"""배포 볼륨 반입본 준비·검증 (PH-04 — `docs/배포_자산_반입_v1.md` §3).

    python scripts/stage_volume_assets.py            # 검증만
    python scripts/stage_volume_assets.py --out DIR  # 검증 + 반입본 생성

반입은 되돌리기 어렵다. 잘못 올린 dossier는 그 참가자의 세션이 실제로 뜬 뒤에야 티가 나고,
그때는 이미 자극이 나간 뒤다. 그래서 **올리기 전에** 문서 §3.3의 요건을 기계로 건다.

거는 것 다섯.

1. 파일명 `Pnn.json`이 문서의 `participant_no`와 일치한다 — 어긋나면 로더가 거부한다.
2. dossier 계약을 통과한다(`dossier_loader.load`) — 기동 게이트(§5.4)와 같은 검증이다.
3. **lock돼 있다**(§5.3). lock 전 dossier가 볼륨에 올라가면 내용이 바뀔 수 있는 자극으로
   세션이 돌고, 재현성(§6.6)이 깨진다.
4. 배정표에 있는 번호다 — 배정되지 않은 참가자의 dossier를 볼륨에 두지 않는다.
5. **P00은 반입 대상이 아니다.** 이미지에 있고 탐색 ②가 잡는다(문서 §2 규칙 2).
   볼륨에 복사하면 QA 자산이 두 벌이 되어 갈라진다.

배정표는 `assignments/assignment_v1.json` 실값만 반입한다 — 더미가 볼륨에 올라가면
`ASSIGNMENT_PATH`가 그것을 **실값으로** 물고 기동한다(문서 §2 규칙 3의 반대 방향 사고).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

#: 리포 자산을 본다 — 로컬에 `DOSSIER_DIR` 오버라이드가 걸려 있어도 스테이징 대상은
#: 어디까지나 "지금 리포에 있는 실값"이다.
os.environ["DOSSIER_DIR"] = str(REPO_ROOT / "dossiers")

from app.assets import dossier_loader  # noqa: E402
from app.core import assignment  # noqa: E402

#: 이미지에 실려 있으므로 볼륨에 올리지 않는다(문서 §2 규칙 2).
IMAGE_RESIDENT = {"P00"}

ASSIGNMENT_SOURCE = REPO_ROOT / "assignments" / "assignment_v1.json"


def real_dossier_numbers() -> list[str]:
    """리포 `dossiers/` 바로 아래의 실값 파일. `schema_dummy/`는 보지 않는다."""
    directory = REPO_ROOT / "dossiers"
    numbers = []
    for path in sorted(directory.glob("P[0-9][0-9].json")):
        numbers.append(path.stem)
    return numbers


def inspect() -> tuple[list[str], list[str], list[str]]:
    """(반입 대상, 문제, 참고) — 문제가 하나라도 있으면 반입하지 않는다."""
    problems: list[str] = []
    notes: list[str] = []

    try:
        table = assignment.validate()
    except Exception as error:  # noqa: BLE001 — 배정표가 없으면 검증 자체가 불가능하다
        return [], [f"배정표를 읽을 수 없다: {error}"], notes
    if table.is_dummy:
        problems.append(
            "배정표가 더미다 — 실값 `assignments/assignment_v1.json`이 없으면 반입하지 않는다 (PH-08)"
        )
    assigned = set(table.participant_numbers)

    staged: list[str] = []
    for number in real_dossier_numbers():
        if number in IMAGE_RESIDENT:
            notes.append(f"{number}: 이미지 자산 — 볼륨 반입 제외 (탐색 ②가 잡는다)")
            continue
        try:
            dossier = dossier_loader.load(number)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{number}: 계약 검증 실패 — {error}")
            continue
        if dossier.is_dummy:
            problems.append(f"{number}: 더미로 읽혔다 — 실값 파일이 아니다")
            continue
        if not dossier.is_locked:
            problems.append(
                f"{number}: lock 전이다 — `python scripts/lock_dossier.py {number}` 먼저 (§5.3)"
            )
            continue
        if number not in assigned:
            problems.append(f"{number}: 배정표에 없는 번호다 — 반입 대상이 아니다")
            continue
        staged.append(number)

    missing = sorted(assigned - set(staged))
    if missing:
        notes.append(
            f"아직 실값이 없는 배정 참가자 {len(missing)}명: {', '.join(missing)} "
            "— 더미로 뜬다(정상). 세션 전까지 착지하면 된다 (PH-03)"
        )
    return staged, problems, notes


def write_staging(staged: list[str], out: Path) -> None:
    dossiers = out / "dossiers"
    assignments = out / "assignments"
    if out.exists():
        shutil.rmtree(out)
    dossiers.mkdir(parents=True)
    assignments.mkdir(parents=True)
    for number in staged:
        shutil.copy2(REPO_ROOT / "dossiers" / f"{number}.json", dossiers / f"{number}.json")
    shutil.copy2(ASSIGNMENT_SOURCE, assignments / ASSIGNMENT_SOURCE.name)
    # 반입본은 실값이다 — 다른 사용자가 읽지 못하게 둔다.
    for path in out.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    out.chmod(0o700)


def print_upload_commands(out: Path, staged: list[str]) -> None:
    print()
    print("반입 명령 (Railway CLI 5.44 실측 문법 — 디렉터리째 올라간다)")
    print(f"  railway volume files upload {out}/dossiers /dossiers --overwrite")
    print(f"  railway volume files upload {out}/assignments /assignments --overwrite")
    print()
    print("반입 후 확인")
    print("  railway volume files list /dossiers --json")
    print("  railway ssh -- python scripts/freeze_study_version.py --check")
    print()
    print("⚠ `ASSIGNMENT_PATH`는 배정표를 올린 **뒤에** 설정한다 — 먼저 설정하면 기동이 끊긴다.")
    print(f"  반입본은 실값이다. 확인이 끝나면 지워라: rm -rf {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="배포 볼륨 반입본 준비·검증 (PH-04)")
    parser.add_argument("--out", type=Path, help="반입본을 만들 디렉터리 (생략하면 검증만)")
    args = parser.parse_args(argv)

    staged, problems, notes = inspect()

    print("볼륨 반입 대상 (PH-04 · docs/배포_자산_반입_v1.md)")
    print(f"  dossier 실값 lock : {len(staged)}건 — {', '.join(staged) or '없음'}")
    print(f"  배정표            : {ASSIGNMENT_SOURCE.name}"
          f"{'' if ASSIGNMENT_SOURCE.is_file() else ' (없음)'}")
    for note in notes:
        print(f"  · {note}")

    if problems:
        print()
        print(f"❌ 반입하지 않는다 — 문제 {len(problems)}건")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    if not staged:
        print()
        print("반입할 실값 dossier가 없다 — 아직 올릴 것이 없다 (PH-03 대기).")
        return 0

    print()
    print(f"✅ 요건 통과 — {len(staged)}건 반입 가능")
    if args.out:
        write_staging(staged, args.out.resolve())
        print(f"   반입본 생성: {args.out.resolve()}")
        print_upload_commands(args.out.resolve(), staged)
    else:
        print("   `--out DIR`를 주면 반입본을 만들고 업로드 명령을 출력한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
