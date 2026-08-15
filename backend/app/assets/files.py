"""dossier 파일 위치 해석 (구현명세서 §2.9 · §5.2 · CLAUDE.md 자산 원칙).

`dossier_loader`(ai_visible·derivation)와 `dossier_private`(researcher_only)가 **같은 파일**을
서로 다른 층만 읽는다. 파일을 찾는 일만 여기 둔다 — 두 로더가 서로를 import하지 않게 하려면
공통부가 별도 모듈이어야 한다(§1.2 구현 규율, NT-04).

파일 배치 (§2.9 "dossier 파일은 리포에 커밋하지 않는다 … P00·스키마 더미만 커밋"):

    dossiers/P00.json              QA 전용 합성 실값 — 커밋 (부록 A.6)
    dossiers/Pnn.json              P01–P12 **실값** — 커밋하지 않는다(.gitignore).
                                   반입 절차 `<TODO: PH-04>`
    dossiers/schema_dummy/Pnn.json 스키마 준수 더미 — 커밋. 실값이 없을 때 로드된다.

실값이 있으면 실값이 이긴다. 없으면 더미로 내려가되 `is_dummy=True`로 표시해서 콘솔(R4)·
기동 로그가 "이 참가자는 아직 lock 전"임을 감출 수 없게 한다(§5.2 lock 절차·부록 D.2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: 리포 루트 = backend/app/assets/files.py 에서 3단계 위.
REPO_ROOT = Path(__file__).resolve().parents[3]
DOSSIER_DIR = REPO_ROOT / "dossiers"
SCHEMA_DUMMY_DIR = DOSSIER_DIR / "schema_dummy"

#: §5.1 — P00(QA 합성) + P01–P12(본실험 표본 12명, D-15).
PARTICIPANT_NUMBERS: tuple[str, ...] = tuple(f"P{n:02d}" for n in range(13))
QA_PARTICIPANT_NO = "P00"


class DossierNotFound(FileNotFoundError):
    """실값도 더미도 없다 — 기동 게이트(§5.4)에서 걸러야 하는 상태다."""


def dossier_path(participant_no: str) -> tuple[Path, bool]:
    """(경로, is_dummy). 실값 → 더미 순으로 찾는다."""
    real = DOSSIER_DIR / f"{participant_no}.json"
    if real.is_file():
        return real, False
    dummy = SCHEMA_DUMMY_DIR / f"{participant_no}.json"
    if dummy.is_file():
        return dummy, True
    raise DossierNotFound(
        f"{participant_no} dossier가 없다: {real} 도 {dummy} 도 찾을 수 없다 "
        "(<TODO: PH-03 — 실값 작성·lock>)"
    )


def read_raw(participant_no: str) -> tuple[dict[str, Any], Path, bool]:
    """파일 전문을 읽어 (문서, 경로, is_dummy)로 돌려준다.

    ⚠ 여기서 돌아온 문서에는 `researcher_only`가 들어 있다. **층 분리는 호출부의 책임**이며,
    LLM 경로에 닿는 모듈은 이 함수를 직접 쓰지 않고 `dossier_loader`를 쓴다(§1.2).
    """
    path, is_dummy = dossier_path(participant_no)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: dossier는 JSON 객체여야 한다")
    return document, path, is_dummy
