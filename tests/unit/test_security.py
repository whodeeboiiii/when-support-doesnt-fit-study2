"""암호화·audit (§2.9 · §2.7 · §8.1 — v5.0 `test_crypto.py` 계열 이식)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AuditLog
from app.security import audit, fernet


def test_encrypt_roundtrip() -> None:
    plaintext = "AI에게 보내지 않은 생각입니다."
    token = fernet.encrypt(plaintext)
    assert isinstance(token, bytes)
    assert plaintext.encode("utf-8") not in token  # 평문이 그대로 남지 않는다 (NT-28)
    assert fernet.decrypt(token) == plaintext


def test_missing_key_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings, get_settings

    settings = get_settings()
    patched = Settings(**{**settings.model_dump(), "fernet_key": None})
    monkeypatch.setattr(fernet, "get_settings", lambda: patched)
    with pytest.raises(fernet.MissingFernetKey):
        fernet.encrypt("x")


async def test_audit_records_actor_action_target(session: AsyncSession) -> None:
    await audit.record(
        session, actor="researcher-1", action=audit.AuditAction.DECRYPT, target="session:abc"
    )
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert [(row.actor, row.action, row.target) for row in rows] == [
        ("researcher-1", "decrypt", "session:abc")
    ]


def test_audit_actions_match_spec_list() -> None:
    """§8.1 `audit_logs.action` — view/decrypt/export/flag/abort/code_issue."""
    assert {str(action) for action in audit.AuditAction} == {
        "view",
        "decrypt",
        "export",
        "flag",
        "abort",
        "code_issue",
    }
