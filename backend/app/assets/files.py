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

볼륨을 마운트할 때 두 가지가 걸린다(PH-04에서 닫았다).

1. **schema_dummy는 리포가 바닥이다.** 볼륨에는 실값만 올린다 — 24명이 한꺼번에 lock되지
   않고 한 명씩 착지하므로(§5.3), 볼륨에 실값 3건만 있으면 나머지 21명은 리포의 더미로
   내려가야 한다. 그러지 않으면 부분 착지 상태에서 기동 게이트가 죽는다.
   볼륨이 자기 더미를 갖고 있으면 그쪽이 이긴다(오버라이드 여지는 남긴다).
2. **오설정은 조용히 넘어가지 않는다.** `DOSSIER_DIR`가 설정됐는데 그런 디렉터리가 없으면
   `AssetLocationError`로 기동을 끊는다. 이 예외를 `DossierNotFound`로 두면
   `available_participant_numbers()`의 루프가 참가자마다 삼켜서 **dossier 0건으로 기동
   성공**하는 최악의 모양이 된다 — 오타 하나로 빈 연구가 뜬다.
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


class AssetLocationError(RuntimeError):
    """자산 **위치 설정**이 틀렸다 (§2.4 `DOSSIER_DIR`) — PH-04.

    `DossierNotFound`와 일부러 계보를 나눴다. 저쪽은 "이 참가자 파일이 없다"이고 루프가
    참가자별로 삼켜도 되는 상태지만, 이쪽은 "가리킨 디렉터리 자체가 없다"이며 **삼키면
    안 된다**. 삼키면 dossier 0건으로 기동이 성공한다.
    """


#: 리포에 커밋된 자산 자리. 볼륨 오버라이드가 있어도 **더미의 바닥**은 여기다.
REPO_DOSSIER_DIR = REPO_ROOT / "dossiers"


def dossier_dir() -> Path:
    """§2.4 `DOSSIER_DIR` — 미설정이면 리포의 `dossiers/`.

    설정을 `core/config.py`가 아니라 여기서 읽는 이유는 import 방향이다: `assets/`가
    `core/config`를 부르면 자산 로더가 pydantic settings에 묶인다. 이 값은 비밀정보가
    아니라 경로 하나이므로 환경변수를 직접 본다.

    설정된 경로가 디렉터리가 아니면 `AssetLocationError`다 — PH-04 반입에서 가장 흔한
    실패가 마운트 경로 오타이고, 그건 조용히 넘어갈 사고가 아니다.
    """
    override = os.environ.get("DOSSIER_DIR", "").strip()
    if not override:
        return REPO_DOSSIER_DIR
    path = Path(override)
    if not path.is_dir():
        raise AssetLocationError(
            f"DOSSIER_DIR={override!r} — 그런 디렉터리가 없다 (§2.4 · PH-04). "
            "볼륨 마운트 경로를 확인하라. 값을 비우면 리포의 dossiers/를 쓴다."
        )
    return path


def is_dossier_dir_overridden() -> bool:
    """§2.4 — 볼륨 오버라이드가 걸려 있는가(콘솔·반입 점검 표시용)."""
    return bool(os.environ.get("DOSSIER_DIR", "").strip())


def schema_dummy_dir() -> Path:
    """스키마 더미 자리. **볼륨 → 리포** 순으로 찾는다.

    볼륨에는 실값만 올리는 것이 정상 운용이다(§2.9 — 실값은 커밋하지 않는다). 그래서
    더미의 바닥은 항상 리포이며, 그 덕에 24명이 한 명씩 lock되는 동안에도 나머지 참가자가
    더미로 떠서 기동·시연이 계속된다.
    """
    override = dossier_dir() / "schema_dummy"
    if override.is_dir():
        return override
    return REPO_DOSSIER_DIR / "schema_dummy"


def is_participant_no(value: str) -> bool:
    """`P00`–`P30` 형식인가. 배정표에 있는지는 여기서 묻지 않는다(§5.1)."""
    return value in PARTICIPANT_NUMBERS


def dossier_search_paths(participant_no: str) -> tuple[tuple[Path, bool], ...]:
    """`(경로, is_dummy)` 후보를 **찾는 순서대로** 돌려준다 (§2.3 · PH-04).

    **볼륨은 오버레이다.** 세 단계를 이 순서로 본다:

        ① DOSSIER_DIR/Pnn.json        반입한 실값 (오버라이드가 없으면 ②와 같은 자리)
        ② <리포>/dossiers/Pnn.json    이미지에 실린 것 — 실질적으로 P00(QA)뿐이다
        ③ schema_dummy/Pnn.json       스키마 더미 (볼륨 → 리포)

    ②가 필요한 이유가 P00이다. `DOSSIER_DIR`를 볼륨으로 돌리는 순간 이미지 안의
    `dossiers/P00.json`이 탐색 범위 밖으로 나가서 **배포 환경에서 QA 워크스루(§10.2)가
    돌지 않는다**. 볼륨에 P00을 복사해 넣는 운용으로도 막을 수 있지만, 그러면 커밋된
    QA 자산이 두 벌이 되고 둘이 갈라질 수 있다 — 오버레이가 그 문제를 만들지 않는다.

    ①과 ②가 같은 경로일 때는 한 번만 본다(오버라이드 없는 로컬·CI가 그 경우다).
    """
    real_dirs: list[Path] = [dossier_dir()]
    if REPO_DOSSIER_DIR not in real_dirs:
        real_dirs.append(REPO_DOSSIER_DIR)
    candidates = [(directory / f"{participant_no}.json", False) for directory in real_dirs]
    candidates.append((schema_dummy_dir() / f"{participant_no}.json", True))
    return tuple(candidates)


def dossier_path(participant_no: str) -> tuple[Path, bool]:
    """(경로, is_dummy). 실값 → 더미 순으로 찾는다(§2.3 · PH-04 오버레이)."""
    for path, is_dummy in dossier_search_paths(participant_no):
        if path.is_file():
            return path, is_dummy
    looked = " · ".join(str(path) for path, _ in dossier_search_paths(participant_no))
    raise DossierNotFound(
        f"{participant_no} dossier가 없다 — 찾은 자리: {looked} "
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
