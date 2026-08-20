"""dossier lock (구현명세서 §5.3 lock 절차 · §1.4 · 부록 D.2).

    python scripts/lock_dossier.py P05
    python scripts/lock_dossier.py P05 --check      # 검증만, 파일 수정 없음
    python scripts/lock_dossier.py --all            # 실값 dossier 전부

하는 일은 **계약 검증 → `locked_at`·`hash` 기입** 둘뿐이다.

`hash`는 hash 필드 자신을 제외한 canonical JSON의 sha256이다(§5.3 — 자기참조 회피).
`locked_at`은 포함되므로, lock 이후 어느 층이든 한 글자만 바뀌어도 `is_locked`가 False가
되고 콘솔 R4·모집 게이트가 그 사실을 표시한다.

**이 스크립트가 하지 않는 것**: 2인 코더 판정·adjudication은 시스템 밖이다(§5.3 —
`evidence_code.coders`가 그 기록을 참조한다). 자극 작성 QC(§5.4)도 사람의 일이고, 시스템은
`stimulus.qc` 필드의 **존재만** 검증한다. lock은 "이 파일 내용으로 세션을 받겠다"는 선언이지
품질 판정이 아니다.

⚠ lock된 dossier는 **해당 참가자 세션 시작 후 변경 금지**다(§1.4). 다시 lock해야 하면
`locked_at`을 지우고 변경 근거를 남긴 뒤 이 스크립트를 다시 돌린다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assets import dossier_loader  # noqa: E402
from app.assets.files import QA_PARTICIPANT_NO, dossier_path, is_participant_no  # noqa: E402


def _load_document(participant_no: str) -> tuple[dict, Path, bool]:
    path, is_dummy = dossier_path(participant_no)
    return json.loads(path.read_text(encoding="utf-8")), path, is_dummy


def lock_one(participant_no: str, *, check_only: bool, now: str) -> int:
    """1건 lock. 반환 0 = 성공, 1 = 실패."""
    if not is_participant_no(participant_no):
        print(f"❌ {participant_no}: 알 수 없는 참가자 번호 (P00–P30)")
        return 1

    # ① 계약 검증 — 로더를 그대로 쓴다. lock 전용 검증기를 따로 만들면 둘이 갈라진다.
    dossier_loader.reset_cache()
    try:
        dossier = dossier_loader.load(participant_no)
    except (dossier_loader.DossierContractError, FileNotFoundError) as exc:
        print(f"❌ {participant_no}: 계약 위반 — lock하지 않는다\n{exc}")
        return 1

    document, path, is_dummy = _load_document(participant_no)
    if is_dummy:
        print(f"❌ {participant_no}: 스키마 더미는 lock 대상이 아니다 ({path}) — <TODO: PH-03>")
        return 1

    content_hash = dossier_loader.compute_document_hash({**document, "locked_at": now})

    if check_only:
        state = "lock됨" if dossier.is_locked else "lock 전"
        print(f"✅ {participant_no}: 계약 통과 · {state} · hash {dossier.content_hash[:12]}…")
        if not all(bool(value) for key, value in dossier.stimulus.qc.items() if key.endswith("_identity")):
            print(f"   ⚠ stimulus.qc 미완 — 독립 second researcher QC 기록이 필요하다 (§5.4)")
        return 0

    if dossier.is_locked:
        print(f"✅ {participant_no}: 이미 lock됨 ({dossier.locked_at}) — 변경 없음")
        return 0

    document["locked_at"] = now
    document["hash"] = content_hash
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dossier_loader.reset_cache()

    relocked = dossier_loader.load(participant_no)
    if not relocked.is_locked:  # pragma: no cover — 방어
        print(f"❌ {participant_no}: lock 기입 후에도 hash가 일치하지 않는다")
        return 1
    print(f"🔒 {participant_no}: lock 완료 — {now} · hash {content_hash[:12]}…")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="dossier lock (§5.3)")
    parser.add_argument("participant_no", nargs="*", help="예: P05")
    parser.add_argument("--all", action="store_true", help="실값 dossier 전부 (P00 제외)")
    parser.add_argument("--check", action="store_true", help="검증만 — 파일을 고치지 않는다")
    args = parser.parse_args(argv)

    if args.all:
        from app.assets.files import available_participant_numbers, dossier_path as _path

        targets = [
            no
            for no in available_participant_numbers()
            if no != QA_PARTICIPANT_NO and not _path(no)[1]
        ]
        if not targets:
            print("실값 dossier가 없다 — 스키마 더미만 있다 (<TODO: PH-03>)")
            return 0
    elif args.participant_no:
        targets = [no.strip().upper() for no in args.participant_no]
    else:
        parser.error("참가자 번호 또는 --all이 필요하다")

    now = datetime.now(UTC).isoformat()
    failures = sum(lock_one(no, check_only=args.check, now=now) for no in targets)
    if failures:
        print(f"\n{failures}건 실패")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
