"""dossier 파일 위치 해석 (구현명세서 §2.3 · §2.4 · §2.9 · §5.1 · CLAUDE.md 자산 원칙).

`dossier_loader`(ai_visible·stimulus·evidence_code)와 `dossier_private`(researcher_only)가
**같은 파일**을 서로 다른 층만 읽는다. 파일을 찾는 일만 여기 둔다 — 두 로더가 서로를
import하지 않게 하려면 공통부가 별도 모듈이어야 한다(§1.2 구현 규율, NT-04).

파일 배치 (§2.3 · §2.9 "dossier·배정표 실값은 커밋하지 않는다"):

    dossiers/P00.json              QA 전용 합성 실값 — 커밋 (§5.5, 초안 신 §7.6 worked example)
    dossiers/Pnn.json              P01–P30 **실값** — 커밋하지 않는다(.gitignore).
                                   반입 절차 `<TODO: PH-04>`
    dossiers/schema_dummy/Pnn.json 스키마 준수 더미 — 커밋. 실값이 없을 때 로드된다.

실값이 있으면 실값이 이긴다. 없으면 더미로 내려가되 `is_dummy=True`로 표시해서 콘솔(R1·R4)·
기동 로그가 "이 참가자는 아직 lock 전"임을 감출 수 없게 한다(§5.3 lock 절차·NT-42).

**참가자 번호 범위는 P00–P30이다**(§2.5 — "참가자 번호는 Study 1의 P번호를 그대로 쓴다.
P01–P30 중 배정표에 있는 24명 + P00"). 즉 이 모듈은 "누가 참가자인가"를 모른다 — 그것은
배정표(`core/assignment.py`)가 안다. 여기는 **번호가 문법적으로 유효한가**만 본다. 둘을
합치면 dossier가 없는 번호로 세션을 만들려는 시도가 배정표 검증 대신 파일 없음으로 터진다.

`DOSSIER_DIR` 환경변수(§2.4 신설)로 디렉터리를 갈아끼울 수 있다 — PH-04의 볼륨 마운트가
그 자리다. 미설정이면 리포의 `dossiers/`다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: 리포 루트 = backend/app/assets/files.py 에서 3단계 위.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: §5.1 — Study 1의 P번호 범위. 이 중 24개가 배정표의 행이 된다(§5.2).
PARTICIPANT_NUMBER_MAX = 30
PARTICIPANT_NUMBERS: tuple[str, ...] = tuple(
    f"P{n:02d}" for n in range(PARTICIPANT_NUMBER_MAX + 1)
)
QA_PARTICIPANT_NO = "P00"

#: §5.2 배정표 dummy가 쓰는 24명 (P01–P24). schema_dummy도 이 범위로 커밋한다.
DUMMY_PARTICIPANT_NUMBERS: tuple[str, ...] = tuple(f"P{n:02d}" for n in range(1, 25))


class DossierNotFound(FileNotFoundError):
    """실값도 더미도 없다 — 기동 게이트(§5.4)·세션 생성(§9.1)에서 걸러야 하는 상태다."""


def dossier_dir() -> Path:
    """§2.4 `DOSSIER_DIR` — 미설정이면 리포의 `dossiers/`.

    설정을 `core/config.py`가 아니라 여기서 읽는 이유는 import 방향이다: `assets/`가
    `core/config`를 부르면 자산 로더가 pydantic settings에 묶인다. 이 값은 비밀정보가
    아니라 경로 하나이므로 환경변수를 직접 본다.
    """
    override = os.environ.get("DOSSIER_DIR", "").strip()
    return Path(override) if override else REPO_ROOT / "dossiers"


def schema_dummy_dir() -> Path:
    return dossier_dir() / "schema_dummy"


def is_participant_no(value: str) -> bool:
    """`P00`–`P30` 형식인가. 배정표에 있는지는 여기서 묻지 않는다(§5.1)."""
    return value in PARTICIPANT_NUMBERS


def dossier_path(participant_no: str) -> tuple[Path, bool]:
    """(경로, is_dummy). 실값 → 더미 순으로 찾는다."""
    real = dossier_dir() / f"{participant_no}.json"
    if real.is_file():
        return real, False
    dummy = schema_dummy_dir() / f"{participant_no}.json"
    if dummy.is_file():
        return dummy, True
    raise DossierNotFound(
        f"{participant_no} dossier가 없다: {real} 도 {dummy} 도 찾을 수 없다 "
        "(<TODO: PH-03 — 실값 작성·lock>)"
    )


def available_participant_numbers() -> tuple[str, ...]:
    """실값이든 더미든 dossier 파일이 있는 번호 (§5.4 기동 게이트의 대상 집합)."""
    found: list[str] = []
    for participant_no in PARTICIPANT_NUMBERS:
        try:
            dossier_path(participant_no)
        except DossierNotFound:
            continue
        found.append(participant_no)
    return tuple(found)


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
