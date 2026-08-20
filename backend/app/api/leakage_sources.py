"""R-1 대조 문자열 · R-2 대안 segment 수집 (구현명세서 §6.4 · §1.2 · NT-04).

§6.4의 규칙 계층은 "출력에 **이 문자열들이** 있는가"를 묻는다.

| 규칙 | 대조 대상 | 판정 |
|---|---|---|
| R-1 | dossier `researcher_only` · sidecar · **checkpoint 수정 전 원문** · 평정 · User2 | 위반 |
| R-2 | **대안 AI1 3종의 u·q segment** | 위반 아님 — `alt_overlap` 플래그 |

**이 모듈이 `llm/` 밖에 있는 이유**가 핵심이다. R-1은 researcher_only를 읽어야 하는데,
`llm/`은 `assets.dossier_private`를 import할 수 없다(NT-04). 그래서 "금지 문자열을 아는 쪽"과
"판정하는 쪽"을 갈라 놓았다: 여기가 모아서 넘기고, `llm/integrity_rules`는 받은 문자열이
출력에 있는지만 본다. 판정기는 그 문자열이 **무엇인지** 끝까지 모른다.

**v2에서 대조 대상이 바뀌었다**(부록 H.2). 타 branch(User1/AI2)는 4-branch 설계와 함께
사라졌고, 대신 **checkpoint 수정 전 원문**이 들어왔다 — §1.2 표에서 "dossier ai_visible
원문(수정 전)"은 AI2 ❌이기 때문이다. 평정·User2도 §1.2 표의 금지 행이라 추가했다.

두 가지 규율이 딸린다.

1. **여기서 모은 문자열은 어떤 프롬프트에도 실리지 않는다.** 파이프라인은 이 값을 판정에만
   쓰고, 재생성 피드백에는 위반 **유형**만 넣는다(§6.4 · NT-01).
2. **복호화는 여기서 끝난다.** §2.9의 복호화 지점 열거에 "leakage 대조"가 명시돼 있다.
   평문은 이 함수의 반환값 밖으로 나가지 않으며, 위반 기록에는 **라벨만** 남는다.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.dossier_loader import STIMULUS_RECIPE, Dossier
from app.assets.dossier_private import load_researcher_only
from app.llm.integrity_rules import AltSegment, ForbiddenText
from app.models import tables
from app.security import fernet


def _decrypt(value: bytes | None) -> str:
    return fernet.decrypt(value) if value else ""


def _add(
    bucket: list[ForbiddenText], source: str, text: str, *, whole_only: bool = False
) -> None:
    if text and text.strip():
        bucket.append(
            ForbiddenText(rule="R-1", source=source, text=text, whole_only=whole_only)
        )


def researcher_only_texts(participant_no: str) -> list[ForbiddenText]:
    """R-1 — dossier researcher_only 층 (§5.3). 콘솔 밖으로 나가면 안 되는 값들이다."""
    bucket: list[ForbiddenText] = []
    for field, value in load_researcher_only(participant_no).items():
        _add(bucket, f"researcher_only.{field}", str(value))
    return bucket


def alt_segments(dossier: Dossier, focal_condition: str) -> list[AltSegment]:
    """R-2 — **focal 자극에 없는** u·q segment (§6.4).

    focal이 이미 포함한 segment는 대조에서 뺀다. C4가 focal이면 u도 q도 payload에 정당히
    들어 있으므로 대조 대상이 없다 — 그때 이 함수는 빈 목록을 돌려준다.

    조건 라벨을 담아 돌려주지만, 이 값은 `generations.alt_overlap`(연구자 층)으로만 가고
    프롬프트에는 실리지 않는다(§1.2).
    """
    used = set(STIMULUS_RECIPE.get(focal_condition, ()))
    segments: list[AltSegment] = []
    for condition, recipe in STIMULUS_RECIPE.items():
        if condition == focal_condition:
            continue
        for key in recipe:
            if key in used or key == "r":
                # `r`은 4조건 동일이므로 대조 의미가 없다(§0.4 — R 문면 4조건 동일).
                continue
            segments.append(
                AltSegment(condition=condition, segment=key, text=dossier.stimulus.segment(key))
            )
    # 같은 segment가 두 조건에 나타나므로(예: u는 C3·C4) 문자열 기준으로 접는다.
    seen: set[str] = set()
    unique: list[AltSegment] = []
    for entry in segments:
        if entry.text in seen:
            continue
        seen.add(entry.text)
        unique.append(entry)
    return unique


async def collect(
    db: AsyncSession, *, session_id: uuid.UUID, participant_no: str, focal_run_id: uuid.UUID
) -> list[ForbiddenText]:
    """이 세션의 AI2 출력에 등장하면 안 되는 문자열 전부 (R-1)."""
    bucket: list[ForbiddenText] = researcher_only_texts(participant_no)

    # sidecar 전 필드 (§1.2 — 어떤 LLM 경로에도 금지).
    sidecars = await db.execute(
        select(tables.SidecarEntry).where(
            tables.SidecarEntry.focal_run_id == focal_run_id
        )
    )
    for entry in sidecars.scalars().all():
        _add(bucket, "sidecar.free_text", _decrypt(entry.free_text))
        _add(bucket, "sidecar.reason_text", _decrypt(entry.reason_text))

    # checkpoint 수정 **전** 원문 (§1.2 — AI2는 수정본으로 대체된다).
    edits = await db.execute(
        select(tables.CheckpointEdit).where(tables.CheckpointEdit.session_id == session_id)
    )
    for row in edits.scalars().all():
        _add(bucket, f"checkpoint_original.{row.segment}", _decrypt(row.original))

    # User2 (§1.2 표 — AI2 ❌). AI2 생성 시점에는 보통 없지만, 재생성·재호출 경로에서
    # 이미 존재할 수 있으므로 대조에 넣는다.
    turns = await db.execute(
        select(tables.Turn).where(
            tables.Turn.focal_run_id == focal_run_id, tables.Turn.role == "user2"
        )
    )
    for turn in turns.scalars().all():
        _add(bucket, "user2", _decrypt(turn.text))

    # 평정 — 값은 숫자라 문자열 대조 대상이 아니지만, **문항 문면**은 금지다(§1.2 표).
    # 자산에서 읽으므로 DB 조회가 필요 없다.
    from app.assets import rating_items

    for item in rating_items.load().items:
        _add(bucket, f"rating_item.{item.item_id}", item.text, whole_only=True)

    return bucket


def sources(forbidden: Iterable[ForbiddenText]) -> list[str]:
    """디버깅·테스트용 라벨 목록. 값은 돌려주지 않는다."""
    return [entry.source for entry in forbidden]
