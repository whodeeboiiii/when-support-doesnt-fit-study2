"""설계 동결과 모집 게이트 (구현명세서 §10.5 · §11.3 · 부록 E.4).

두 가지를 한 모듈에 둔다. 같은 질문의 앞뒤이기 때문이다 — **지금 이 구성으로 사람을 받아도
되는가**, 그리고 **받은 뒤 그 구성을 무엇으로 증명할 것인가**.

1. `blockers()` — §11.3의 마지막 줄("PH-IRB 계열·PH-03 착지 전에는 본 모집을 시작하지
   않는다")을 실행 가능한 점검으로 옮긴다. dossier 실값 lock, IRB 문안 착지, 프롬프트
   lock, 모델 슬러그 설정을 본다. **자동 차단 장치가 아니다** — 콘솔·스크립트가 상태를
   보여 주고, 시작 여부는 사람이 정한다(D-10과 같은 태도: 시스템은 판정하지 않는다).
2. `freeze()` — §10.5 "soft launch 종료 시 `study_version`에 spec_version·prompt_hash·
   model_strings·assets_hash 동결 기입". 이후 변경은 §1.4 본실험 열만 적용된다.

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

from app.assets import dossier_loader, presurvey, rating_items, screen_copy
from app.assets.files import QA_PARTICIPANT_NO
from app.core.config import get_settings
from app.llm import prompts
from app.models import tables

#: 부록 E.4 — 모집 게이트가 보는 TODO 태그. 문안에 이 문자열이 남아 있으면 미착지다.
IRB_TAGS: tuple[str, ...] = ("PH-IRB-1", "PH-IRB-2")

#: 부록 E.4 PH-01 — 실값 자산은 `presurvey_items_v1.json`이다. v0은 placeholder다(§4.2).
PRESURVEY_PLACEHOLDER_SUFFIX = "_v0.json"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class Blocker:
    """본 모집을 막는 사유 1건 (§11.3)."""

    tag: str
    detail: str


def blockers() -> list[Blocker]:
    """본 모집 전 착지해야 하는 항목 중 **아직 안 된 것**들."""
    found: list[Blocker] = []

    unlocked = [
        participant_no
        for participant_no, dossier in dossier_loader.load_all().items()
        if participant_no != QA_PARTICIPANT_NO and (dossier.is_dummy or not dossier.is_locked)
    ]
    if unlocked:
        found.append(
            Blocker("PH-03", f"dossier 실값 lock 미완 — {', '.join(sorted(unlocked))} (§5.2)")
        )

    consent_text = screen_copy.CONSENT_TODO + screen_copy.DEBRIEF_TODO
    for tag in IRB_TAGS:
        if tag in consent_text:
            found.append(Blocker(tag, "문안 미착지 — 동의서·디브리핑 정본 필요 (§4.1·§4.11)"))

    if presurvey.asset_path().name.endswith(PRESURVEY_PLACEHOLDER_SUFFIX):
        found.append(
            Blocker("PH-01", f"사전설문 문항 원문 미착지 — {presurvey.asset_path().name} (§4.2)")
        )

    settings = get_settings()
    if not settings.dev_mode and not (settings.main_model_id and settings.validator_model_id):
        found.append(Blocker("확인 1", "MAIN·VALIDATOR 모델 슬러그 미설정 (§2.2.1)"))

    return found


def asset_hashes() -> dict[str, Any]:
    """§10.5 `assets_hash` — 동결 시점의 자산 지문 묶음."""
    dossiers = {
        participant_no: dossier.content_hash
        for participant_no, dossier in sorted(dossier_loader.load_all().items())
    }
    return {
        "dossiers": dossiers,
        "presurvey": {
            "version": presurvey.load().version,
            "hash": _file_hash(presurvey.asset_path()),
        },
        "normalization_patterns": prompts.config()["normalization_patterns_version"],
        # §7.3 12문항은 코드 상수다 — 파일이 없으므로 원문에서 지문을 만든다.
        "rating_items": hashlib.sha256(
            "\n".join(item.text for item in rating_items.RATING_ITEMS).encode("utf-8")
        ).hexdigest(),
        "consent_version": screen_copy.CONSENT_VERSION,
    }


def model_strings() -> dict[str, Any]:
    """§2.2.2-③ — soft launch 종료 시점의 모델 문자열."""
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
