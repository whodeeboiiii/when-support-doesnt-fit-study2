"""설계 동결과 모집 게이트 (구현명세서 §10.5 · §11.2 · 부록 E.4).

두 가지를 한 모듈에 둔다. 같은 질문의 앞뒤이기 때문이다 — **지금 이 구성으로 사람을 받아도
되는가**, 그리고 **받은 뒤 그 구성을 무엇으로 증명할 것인가**.

1. `blockers()` — §11.2의 마지막 줄("PH-03(dossier)·PH-08(배정표)·PH-06·PH-07(문항)·
   PH-IRB 착지 전 본 모집 금지")을 실행 가능한 점검으로 옮긴다(부록 H.2가 지정한 항목
   목록이 그대로다). **자동 차단 장치가 아니다** — 콘솔·스크립트가 상태를 보여 주고,
   시작 여부는 사람이 정한다(D-10과 같은 태도: 시스템은 판정하지 않는다).
2. `freeze()` — §10.5 "soft launch 종료 시 `study_version`에 spec_version·prompt_hash·
   model_strings·assets_hash(dossier 24 + assignment + prompt_config + items) 동결 기입".
   이후 변경은 §1.4 본실험 열만 적용된다.

`study_version`은 **한 번만** 쓴다. 두 번째 호출은 기존 행을 돌려주고 덮어쓰지 않는다 —
동결 기록이 바뀌면 그건 동결이 아니다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader, pairwise_items, rating_items, screen_copy
from app.assets import files
from app.assets.files import QA_PARTICIPANT_NO
from app.core import assignment
from app.core.config import get_settings
from app.llm import prompts
from app.models import tables

#: 부록 E.4 — 모집 게이트가 보는 TODO 태그. 문안에 이 문자열이 남아 있으면 미착지다.
IRB_TAGS: tuple[str, ...] = ("PH-IRB-1", "PH-IRB-2")

#: 부록 E.4 — 문항 자산은 `*_v1.json`이 실값이고 `_v0`은 placeholder다(§4.8·§4.10).
PLACEHOLDER_SUFFIX = "_v0.json"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class Blocker:
    """본 모집을 막는 사유 1건 (§11.2)."""

    tag: str
    detail: str


def blockers() -> list[Blocker]:
    """본 모집 전 착지해야 하는 항목 중 **아직 안 된 것**들 (§11.2 · 부록 H.2)."""
    found: list[Blocker] = []

    # PH-03 — dossier 실값 작성·2인 판정·lock. 배정표의 24명만 본다(P00은 QA 전용).
    try:
        table = assignment.load()
        targets = set(table.participant_numbers)
    except assignment.AssignmentContractError:
        table = None
        targets = set()

    dossiers = dossier_loader.load_all()
    unlocked = sorted(
        participant_no
        for participant_no, dossier in dossiers.items()
        if participant_no != QA_PARTICIPANT_NO
        and (not targets or participant_no in targets)
        and (dossier.is_dummy or not dossier.is_locked)
    )
    if unlocked:
        found.append(Blocker("PH-03", f"dossier 실값 lock 미완 — {', '.join(unlocked)} (§5.3)"))

    # PH-08 — 배정표 생성·동결. dummy로 내려가 있으면 미착지다(NT-42).
    if table is None:
        found.append(Blocker("PH-08", "배정표를 읽을 수 없다 — 제약 위반 또는 파일 없음 (§5.2)"))
    elif table.is_dummy:
        found.append(
            Blocker("PH-08", f"배정표가 dummy다 — {table.source_path.name} (§5.2 · NT-42)")
        )
    elif table is not None:
        # 배정표에 있는데 dossier가 없으면 세션 생성이 막힌다(§9.1 마지막 행).
        missing = sorted(targets - set(dossiers))
        if missing:
            found.append(
                Blocker("PH-03", f"배정표 참가자의 dossier 없음 — {', '.join(missing)} (§9.1)")
            )

    # PH-06 · PH-07 — 문항 문면. 2026-08-24 `_v1` 착지로 통과 상태다. **검사는 남긴다** —
    # `_v1`이 사라지면 로더가 `_v0`으로 내려가는데, 그 회귀를 잡는 것이 이 두 줄이다.
    if rating_items.load().is_placeholder:
        found.append(
            Blocker("PH-06", f"focal 문항 원문 미착지 — {rating_items.asset_path().name} (§4.8)")
        )
    if pairwise_items.load().is_placeholder:
        found.append(
            Blocker(
                "PH-07", f"pairwise 문항 원문 미착지 — {pairwise_items.asset_path().name} (§4.10)"
            )
        )

    # PH-IRB-1 · PH-IRB-2 — 동의서·디브리핑 정본. 초안 문안이 착지해도 표식은 남는다
    # (승인은 IRB가 한다) — `screen_copy`의 P1·P12 주석 참조.
    consent_text = screen_copy.CONSENT_TODO + screen_copy.DEBRIEF_TODO
    for tag in IRB_TAGS:
        if tag in consent_text:
            found.append(
                Blocker(tag, "IRB 승인 대기 — 초안 문안 착지본 사용 중 (§4.1·§4.12)")
            )

    settings = get_settings()
    if not settings.dev_mode and not (settings.main_model_id and settings.validator_model_id):
        found.append(Blocker("확인 1", "MAIN·VALIDATOR 모델 슬러그 미설정 (§2.2)"))

    return found


def asset_sources() -> dict[str, Any]:
    """§2.4 · PH-04 — **어디서 읽었는가**. 반입 직후 확인용이다.

    `blockers()`가 "무엇이 미착지인가"를 말한다면 이쪽은 "지금 읽고 있는 파일이 무엇인가"를
    말한다. 볼륨을 마운트한 뒤 가장 먼저 알아야 하는 것이 그거다 — 게이트가 PH-03을
    보고할 때, 볼륨이 안 붙은 것인지 파일이 아직 lock 전인지 구분되지 않으면 손을 못 댄다.
    """
    dossiers = dossier_loader.load_all()
    real = sorted(no for no, entry in dossiers.items() if not entry.is_dummy)
    dummy = sorted(no for no, entry in dossiers.items() if entry.is_dummy)
    locked = sorted(no for no, entry in dossiers.items() if entry.is_locked)

    try:
        table = assignment.load()
        assignment_entry: dict[str, Any] = {
            "path": str(table.source_path),
            "is_dummy": table.is_dummy,
            "version": table.version,
            "rows": len(table.rows),
        }
    except assignment.AssignmentContractError as exc:
        assignment_entry = {"path": None, "error": str(exc)}

    return {
        "dossier_dir": str(files.dossier_dir()),
        "dossier_dir_overridden": files.is_dossier_dir_overridden(),
        "schema_dummy_dir": str(files.schema_dummy_dir()),
        "dossiers": {"real": real, "dummy": dummy, "locked": locked},
        "assignment": assignment_entry,
        "focal_items": {
            "path": str(rating_items.asset_path()),
            "version": rating_items.load().version,
            "is_placeholder": rating_items.load().is_placeholder,
        },
        "pairwise_items": {
            "path": str(pairwise_items.asset_path()),
            "version": pairwise_items.load().version,
            "is_placeholder": pairwise_items.load().is_placeholder,
        },
        "consent_version": screen_copy.CONSENT_VERSION,
    }


def asset_hashes() -> dict[str, Any]:
    """§10.5 `assets_hash` — dossier 24 + assignment + prompt_config + items."""
    dossiers = {
        participant_no: dossier.content_hash
        for participant_no, dossier in sorted(dossier_loader.load_all().items())
    }
    try:
        table = assignment.load()
        assignment_entry: dict[str, Any] = {
            "version": table.version,
            "seed": table.seed,
            "is_dummy": table.is_dummy,
            "hash": _file_hash(table.source_path),
        }
    except assignment.AssignmentContractError as exc:  # pragma: no cover — 기동 게이트가 먼저 잡는다
        assignment_entry = {"error": str(exc)}

    return {
        "dossiers": dossiers,
        "assignment": assignment_entry,
        "focal_items": {
            "version": rating_items.load().version,
            "hash": _file_hash(rating_items.asset_path()),
        },
        "pairwise_items": {
            "version": pairwise_items.load().version,
            "hash": _file_hash(pairwise_items.asset_path()),
        },
        "consent_version": screen_copy.CONSENT_VERSION,
    }


def model_strings() -> dict[str, Any]:
    """§2.2 — soft launch 종료 시점의 모델 문자열."""
    settings = get_settings()
    return {
        "main_requested": settings.main_model_id,
        "validator_requested": settings.validator_model_id,
        "dev_mode": settings.dev_mode,
    }


async def current(db: AsyncSession) -> tables.StudyVersion | None:
    result = await db.execute(select(tables.StudyVersion).order_by(tables.StudyVersion.frozen_at))
    return result.scalars().first()


async def freeze(db: AsyncSession, *, frozen_at) -> tuple[tables.StudyVersion, bool]:
    """§10.5 동결 1회. 반환 두 번째 값은 "이번 호출이 새로 썼는가"다.

    시각을 인자로 받는 이유: 동결 시각은 **연구 기록**이므로 호출부(스크립트·콘솔)가
    자기 시계로 명시해 넘긴다.
    """
    existing = await current(db)
    if existing is not None:
        return existing, False

    document = prompts.config()
    row = tables.StudyVersion(
        spec_version=str(document.get("spec_version", "")),
        prompt_hash=prompts.config_hash(),
        model_strings=model_strings(),
        assets_hash=asset_hashes(),
        frozen_at=frozen_at,
    )
    db.add(row)
    await db.flush()
    return row, True
