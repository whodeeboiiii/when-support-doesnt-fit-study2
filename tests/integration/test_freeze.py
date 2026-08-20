"""설계 동결·모집 게이트 (구현명세서 §10.5 · §11.2 · 부록 E.4).

§11.2의 마지막 줄 — "PH-03·PH-08·PH-06·PH-07·PH-IRB 착지 전 본 모집 금지" — 은 규율이지
자동 차단 장치가 아니다. 그래서 검사도 **상태를 정확히 보고하는가**만 본다. 게이트가
막혔다고 API가 세션 생성을 거부하지는 않는다(D-10과 같은 태도: 판단은 사람이 한다).
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient

from app.core import freeze
from tests.helpers import ADMIN_AUTH


def test_blockers_report_the_current_placeholder_state() -> None:
    """지금은 더미 자산 단계다(§11.1) — 게이트가 그 사실을 정확히 말해야 한다."""
    tags = {blocker.tag for blocker in freeze.blockers()}
    # 부록 H.2가 지정한 게이트 항목 6종.
    assert tags >= {"PH-03", "PH-08", "PH-06", "PH-07", "PH-IRB-1", "PH-IRB-2"}
    assert "PH-03" in tags, "dossier 실값 미lock 상태를 게이트가 놓쳤다"
    assert "PH-08" in tags, "배정표가 dummy인 상태를 게이트가 놓쳤다 (NT-42)"
    # v1.0.1의 PH-01(사전설문)은 소멸했다(D-31).
    assert "PH-01" not in tags


def test_blocker_details_name_the_missing_thing() -> None:
    blockers = {blocker.tag: blocker.detail for blocker in freeze.blockers()}
    assert "P01" in blockers["PH-03"] and "P00" not in blockers["PH-03"], (
        "P00은 QA 전용이라 게이트 대상이 아니다"
    )
    assert "dummy" in blockers["PH-08"]
    assert "_v0.json" in blockers["PH-06"] and "_v0.json" in blockers["PH-07"]


def test_asset_hashes_cover_every_frozen_asset() -> None:
    """§10.5 assets_hash — 어느 자산이 바뀌어도 지문이 달라져야 한다."""
    hashes = freeze.asset_hashes()
    # §10.5 — dossier 24 + assignment + prompt_config + items.
    assert set(hashes) == {
        "dossiers",
        "assignment",
        "focal_items",
        "pairwise_items",
        "consent_version",
    }
    assert len(hashes["dossiers"]) >= 25  # P00 + 배정표 24명
    assert all(len(value) == 64 for value in hashes["dossiers"].values())
    assert hashes["assignment"]["is_dummy"] is True
    assert len(hashes["assignment"]["hash"]) == 64


async def test_freeze_writes_once_and_never_overwrites(session) -> None:
    first, created = await freeze.freeze(session, frozen_at=datetime.now(UTC))
    assert created is True
    assert first.prompt_hash and first.spec_version
    assert set(first.assets_hash) >= {"dossiers", "assignment", "focal_items"}

    again, created_again = await freeze.freeze(session, frozen_at=datetime.now(UTC))
    assert created_again is False and again.id == first.id


async def test_r1_shows_the_launch_gate_without_blocking_session_creation(
    client: AsyncClient,
) -> None:
    """게이트는 R1에 **표시**된다. 세션 생성은 그대로 된다 — 자동 차단 없음(§11.2 · D-10)."""
    body = (await client.get("/admin/participants", auth=ADMIN_AUTH)).json()
    assert {row["tag"] for row in body["launch_gate"]} >= {"PH-03", "PH-08", "PH-IRB-1"}
    assert body["study_version_frozen_at"] is None

    created = await client.post(
        "/admin/sessions", json={"participant_no": "P00"}, auth=ADMIN_AUTH
    )
    assert created.status_code == 201
