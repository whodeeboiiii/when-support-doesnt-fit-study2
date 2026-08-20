"""암호화·복호화 통제 (구현명세서 §2.9 · §8.1 — NT-28).

    NT-28 암호화 필드(🔒) 평문 저장 0건, 복호화 audit 기록

두 층으로 본다.

1. **저장 층**: 세션을 끝까지 돌린 뒤 **DB 전 테이블을 통째로 훑어** 참가자·연구자가 쓴
   문자열이 한 번도 평문으로 나타나지 않는지 본다. 컬럼별 검사가 아니라 전수 훑기인 이유는
   §8.1이 나열하지 않은 자리(예: `events.payload`)로 평문이 새는 경우를 잡기 위해서다.
2. **접근 층**: 복호화 지점이 §2.9의 둘(콘솔·export) + 명세된 예외 둘(참가자 P10 재표시,
   R-1·R-2 규칙 대조)로 한정되는지 **정적으로** 세고, 콘솔·export 경로가 `audit_logs`에
   기록을 남기는지 실행으로 확인한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from analysis import export_trajectory
from app.models import Base, tables
from app.security import fernet
from tests import helpers
from tests.helpers import ADMIN_AUTH

BACKEND = Path(__file__).resolve().parents[2] / "backend"

USER1_TEXT = "평문검사용참가자발화센티넬"
SIDECAR_TEXT = "평문검사용사이드카센티넬"
FLAG_REASON = "평문검사용플래그사유센티넬"
ABORT_REASON = "평문검사용중단사유센티넬"

#: §2.9 — 복호화가 허용된 모듈과 그 근거. 새 모듈이 늘면 이 표를 고치는 결정이 먼저다.
#: ②(분석 export)는 `analysis/`에 있어 이 정적 검사의 대상 밖이다(런타임 코드가 아니다).
ALLOWED_DECRYPT_MODULES: dict[str, str] = {
    "app/api/admin_views.py": "§2.9 ① 콘솔 표시 (audit 기록)",
    "app/api/state_payload.py": "§4.10 P10 — 참가자 본인 텍스트 재표시",
    "app/api/leakage_sources.py": "§6.5 R-1·R-2 대조 (평문 대조를 규칙이 요구)",
    "app/api/branch.py": "§6.2 — AI2 payload에 넣을 정규화본 User1 (allowlist 3종 중 하나)",
}


async def _dump_all_rows(session) -> str:
    """전 테이블의 모든 값을 한 문자열로. bytes는 그대로 붙여 평문 누출을 잡는다."""
    chunks: list[str] = []
    for table in Base.metadata.sorted_tables:
        for row in (await session.execute(table.select())).all():
            for value in row:
                chunks.append(value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value))
    return "\n".join(chunks)


async def _run_session(client: AsyncClient) -> str:
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    await helpers.advance(client, "P4")
    await client.post("/api/branch/1/user1", json={"disposition": "reply", "text": USER1_TEXT})
    await client.post(
        "/api/branch/1/sidecar",
        json={"choice": "has", "free_text": SIDECAR_TEXT, "relevance": 4},
    )
    await client.post("/api/branch/1/ai2")
    await client.post(
        f"/admin/sessions/{created['session_id']}/flag",
        json={"reason": FLAG_REASON},
        auth=ADMIN_AUTH,
    )
    return created["session_id"]


async def test_nt28_no_plaintext_of_protected_fields_anywhere_in_the_database(
    client: AsyncClient, session
) -> None:
    session_id = await _run_session(client)
    await client.post(
        f"/admin/sessions/{session_id}/abort", json={"reason": ABORT_REASON}, auth=ADMIN_AUTH
    )

    dump = await _dump_all_rows(session)
    for sentinel in (USER1_TEXT, SIDECAR_TEXT, FLAG_REASON, ABORT_REASON):
        assert sentinel not in dump, f"평문 저장: {sentinel}"


async def test_nt28_protected_columns_hold_fernet_tokens(client: AsyncClient, session) -> None:
    """🔒 컬럼은 ciphertext(bytes)만 담는다 — 평문 컬럼을 따로 두지 않는다(§8.1)."""
    await _run_session(client)

    turn = (
        await session.execute(select(tables.Turn).where(tables.Turn.role == "user1"))
    ).scalars().one()
    entry = (await session.execute(select(tables.SidecarEntry))).scalars().one()
    generation = (
        await session.execute(
            select(tables.Generation).where(tables.Generation.final.is_(True))
        )
    ).scalars().one()

    for value in (turn.text, turn.text_normalized, entry.free_text, generation.output_text):
        assert isinstance(value, bytes) and value.startswith(b"gAAAA"), "Fernet 토큰이 아니다"
    assert fernet.decrypt(turn.text) == USER1_TEXT
    assert fernet.decrypt(entry.free_text) == SIDECAR_TEXT


async def test_nt28_console_view_records_a_decrypt_row(client: AsyncClient, session) -> None:
    session_id = await _run_session(client)
    before = len((await session.execute(select(tables.AuditLog))).scalars().all())

    await client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)
    logs = list((await session.execute(select(tables.AuditLog))).scalars().all())
    assert len(logs) > before
    assert any(log.action == "decrypt" for log in logs[before:])
    # audit에는 **값이 아니라 대상**만 남는다(§2.9).
    assert all(USER1_TEXT not in (log.target or "") for log in logs)


async def test_nt28_export_records_a_decrypt_row(client: AsyncClient, session) -> None:
    await _run_session(client)
    await export_trajectory.collect(session, actor="qa", include_text=True)
    logs = list((await session.execute(select(tables.AuditLog))).scalars().all())
    assert {"export", "decrypt"} <= {log.action for log in logs if log.actor == "qa"}


def test_nt28_decrypt_call_sites_are_the_documented_ones() -> None:
    """§2.9 — 복호화 지점이 조용히 늘어나지 않는지 정적으로 센다.

    새 모듈에서 `fernet.decrypt`를 부르기 시작하면 그 자체가 명세 개정 대상이다
    (§2.9는 복호화 지점을 2곳으로 못박고, 예외는 명세서 문면으로 정당화해야 한다).
    """
    callers: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "decrypt":
                callers.add(str(path.relative_to(BACKEND)))
    # 정의 자체가 있는 모듈은 제외한다.
    callers.discard("app/security/fernet.py")
    assert callers == set(ALLOWED_DECRYPT_MODULES), (
        f"복호화 지점 변경 — 명세 §2.9 확인 필요: {sorted(callers)}"
    )


def test_encrypted_fields_match_the_spec_list() -> None:
    """§2.9 암호화 대상 목록과 §8.1 🔒 컬럼이 일치하는지 본다."""
    from sqlalchemy import LargeBinary

    encrypted = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, LargeBinary)
    }
    assert encrypted == {
        "turns.text",
        "turns.text_normalized",
        "generations.output_text",
        "sidecar_entries.free_text",
        "sidecar_entries.reason_text",
        "sessions.abort_reason",
    }
