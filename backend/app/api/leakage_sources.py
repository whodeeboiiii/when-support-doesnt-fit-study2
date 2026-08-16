"""R-1·R-2 대조 문자열 수집 (구현명세서 §6.5 · §1.2 · NT-04).

§6.5의 규칙 계층은 "출력에 **이 문자열들이** 있는가"를 묻는다.

| 규칙 | 대조 대상 |
|---|---|
| R-1 | dossier `researcher_only` 값 · sidecar 유래 문자열 |
| R-2 | 타 branch의 User1 / AI2 문자열 |

**이 모듈이 `llm/` 밖에 있는 이유**가 핵심이다. R-1은 researcher_only를 읽어야 하는데,
`llm/`은 `assets.dossier_private`를 import할 수 없다(NT-04). 그래서 "금지 문자열을 아는 쪽"과
"판정하는 쪽"을 갈라 놓았다: 여기가 모아서 넘기고, `llm/integrity_rules`는 받은 문자열이
출력에 있는지만 본다. 판정기는 그 문자열이 **무엇인지** 끝까지 모른다.

두 가지 규율이 딸린다.

1. **여기서 모은 문자열은 어떤 프롬프트에도 실리지 않는다.** 파이프라인은 이 값을 판정에만
   쓰고, 재생성 피드백에는 위반 **유형**만 넣는다(§6.5 · NT-01).
2. **복호화는 여기서 끝난다.** §2.9의 복호화 지점 2곳(콘솔·export)과 별개로, R-1·R-2는
   저장된 암호문을 평문으로 대조할 것을 규칙 자체가 요구한다. 평문은 이 함수의 반환값
   밖으로 나가지 않으며, 위반 기록에는 **라벨만** 남는다(`ForbiddenText.source`).
"""

from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.dossier_private import load_researcher_only
from app.llm.integrity_rules import ForbiddenText
from app.models import tables
from app.security import fernet


def _decrypt(value: bytes | None) -> str:
    return fernet.decrypt(value) if value else ""


def _add(
    bucket: list[ForbiddenText], rule: str, source: str, text: str, *, whole_only: bool = False
) -> None:
    if text and text.strip():
        bucket.append(
            ForbiddenText(rule=rule, source=source, text=text, whole_only=whole_only)
        )


def researcher_only_texts(participant_no: str) -> list[ForbiddenText]:
    """R-1 전반부 — dossier researcher_only 층 (§5.2). 콘솔 밖으로 나가면 안 되는 값들이다."""
    bucket: list[ForbiddenText] = []
    for field, value in load_researcher_only(participant_no).items():
        _add(bucket, "R-1", f"researcher_only.{field}", str(value))
    return bucket


async def collect(
    db: AsyncSession, *, session_id: uuid.UUID, participant_no: str, branch_id: uuid.UUID
) -> list[ForbiddenText]:
    """이 branch의 AI2 출력에 등장하면 안 되는 문자열 전부."""
    bucket: list[ForbiddenText] = researcher_only_texts(participant_no)

    # R-1 후반부 — sidecar 전 필드(§1.2: 어떤 LLM 경로에도 금지). 세션 전체를 본다.
    sidecars = await db.execute(
        select(tables.SidecarEntry, tables.Branch.branch_index)
        .join(tables.Branch, tables.SidecarEntry.branch_id == tables.Branch.id)
        .where(tables.Branch.session_id == session_id)
    )
    for entry, index in sidecars.all():
        _add(bucket, "R-1", f"sidecar[b{index}].free_text", _decrypt(entry.free_text))
        _add(bucket, "R-1", f"sidecar[b{index}].reason_text", _decrypt(entry.reason_text))

    # R-2 — 타 branch의 User1·AI2 (§3.4 branch 격리, NT-10).
    turns = await db.execute(
        select(tables.Turn, tables.Branch.branch_index, tables.Turn.branch_id)
        .join(tables.Branch, tables.Turn.branch_id == tables.Branch.id)
        .where(
            tables.Branch.session_id == session_id,
            tables.Turn.role.in_(["user1", "ai2"]),
        )
    )
    rows = turns.all()
    current_user1 = next(
        (
            _decrypt(turn.text)
            for turn, _index, turn_branch in rows
            if turn_branch == branch_id and turn.role == "user1"
        ),
        "",
    )
    user1_by_branch = {
        turn_branch: _decrypt(turn.text)
        for turn, _index, turn_branch in rows
        if turn.role == "user1"
    }

    for turn, index, turn_branch in rows:
        if turn_branch == branch_id:
            continue
        if turn.role == "user1":
            _add(bucket, "R-2", f"branch{index}.user1", _decrypt(turn.text))
            continue
        # 타 branch AI2는 **전문 일치**로만 본다(같은 정책·같은 dossier에서 나온 문구 겹침은
        # 격리 실패가 아니다). 게다가 그 branch의 User1이 이번과 같으면 출력이 같은 것이
        # 정상이므로 대조에서 아예 뺀다.
        if user1_by_branch.get(turn_branch, "") == current_user1:
            continue
        _add(bucket, "R-2", f"branch{index}.ai2", _decrypt(turn.text), whole_only=True)
    return bucket


def sources(forbidden: Iterable[ForbiddenText]) -> list[str]:
    """디버깅·테스트용 라벨 목록. 값은 돌려주지 않는다."""
    return [entry.source for entry in forbidden]
