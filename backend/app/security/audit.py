"""연구자 행위 audit (구현명세서 §2.7 · §2.9 · §8.1 `audit_logs`).

"모든 콘솔 조회·flag·abort·dossier 열람은 `audit_logs`에 기록한다"(§2.7)와 "복호화 조회는
audit 기록"(§2.9)이 이 모듈 하나를 지난다. 기록 대상은 **누가·무엇을 했는가**이지 값이
아니다 — 복호화한 참가자 원문을 audit에 옮겨 적으면 §2.9의 "복호화 지점은 정확히 2곳"
약속이 무의미해진다.

`llm_calls`(§8.1)는 별도 테이블이다. 모델 호출 1건의 기록은 `llm/gateway/calls.py`가 남긴다.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AuditLog


class AuditAction(StrEnum):
    """§8.1 `audit_logs.action` 목록."""

    VIEW = "view"
    DECRYPT = "decrypt"
    EXPORT = "export"
    FLAG = "flag"
    ABORT = "abort"
    CODE_ISSUE = "code_issue"
    #: §9.1.1 — 연구자 되돌리기. 참가자 응답을 지우는 유일한 경로라 감사 대상이다.
    REWIND = "rewind"


async def record(
    session: AsyncSession,
    *,
    actor: str,
    action: AuditAction,
    target: str | None = None,
) -> AuditLog:
    """콘솔·export 행위 1건을 남긴다.

    `target`은 식별자만 넣는다(예: `session:<uuid>`, `dossier:P03`). 자유 텍스트 사유는
    `events`(§8.1)의 암호화 payload가 담당한다 — audit은 접근 이력이지 내용 저장소가 아니다.
    """
    row = AuditLog(actor=actor, action=str(action), target=target)
    session.add(row)
    await session.flush()
    return row
