"""설계 동결·모집 게이트 (구현명세서 §10.5 · §11.3 · 부록 E.4).

§11.3의 마지막 줄 — "PH-IRB 계열·PH-03 착지 전에는 본 모집을 시작하지 않는다" — 은 규율이지
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
    assert "PH-03" in tags, "dossier 실값 미lock 상태를 게이트가 놓쳤다"
    assert {"PH-IRB-1", "PH-IRB-2"} <= tags
    assert "PH-01" in tags


def test_blocker_details_name_the_missing_thing() -> None:
    detail = next(blocker for blocker in freeze.blockers() if blocker.tag == "PH-03").detail
    assert "P01" in detail and "P00" not in detail, "P00은 QA 전용이라 게이트 대상이 아니다"


def test_asset_hashes_cover_every_frozen_asset() -> None:
    """§10.5 assets_hash — 어느 자산이 바뀌어도 지문이 달라져야 한다."""
    hashes = freeze.asset_hashes()
    assert set(hashes) == {
        "dossiers",
        "presurvey",
        "normalization_patterns",
        "rating_items",
        "consent_version",
    }
    assert len(hashes["dossiers"]) == 13  # P00–P12
    assert all(len(value) == 64 for value in hashes["dossiers"].values())


async def test_freeze_writes_once_and_never_overwrites(session) -> None:
    first, created = await freeze.freeze(session, frozen_at=datetime.now(UTC))
    assert created is True
    assert first.prompt_hash and first.spec_version
    assert set(first.assets_hash) >= {"dossiers", "presurvey"}

    again, created_again = await freeze.freeze(session, frozen_at=datetime.now(UTC))
    assert created_again is False and again.id == first.id


async def test_r1_shows_the_launch_gate_without_blocking_session_creation(
    client: AsyncClient,
) -> None:
    """게이트는 R1에 **표시**된다. 세션 생성은 그대로 된다 — 자동 차단 없음(§11.3 · D-10)."""
    body = (await client.get("/admin/participants", auth=ADMIN_AUTH)).json()
    assert {row["tag"] for row in body["launch_gate"]} >= {"PH-03", "PH-IRB-1"}
    assert body["study_version_frozen_at"] is None

    created = await client.post(
        "/admin/sessions", json={"participant_no": "P00"}, auth=ADMIN_AUTH
    )
    assert created.status_code == 201
