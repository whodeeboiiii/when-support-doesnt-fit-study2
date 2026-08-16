"""테스트 헬퍼 (구 리포 `tests/helpers.py`의 신판 — NS1에서 NS2로 이월한 항목).

구 헬퍼는 S00–S20 흐름 전용이라 반입하지 않았다. 신판은 §3의 SS·B와 §8.2의 엔드포인트만 안다.

의도적으로 **얇게** 유지한다: 요청을 대신 보내 주기만 하고 상태를 계산하지 않는다. 헬퍼가
상태를 알기 시작하면 테스트가 서버 대신 헬퍼를 검증하게 된다.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import ADMIN_PASS, ADMIN_USER

ADMIN_AUTH = (ADMIN_USER, ADMIN_PASS)

#: 평정 12문항 전부에 같은 값을 넣는 payload (§4.9 — 값 자체는 이 테스트들의 관심사가 아니다).
def ratings_payload(value: int = 4) -> dict[str, Any]:
    return {"items": [{"position": position, "value": value} for position in range(1, 13)]}


async def create_session(client: AsyncClient, participant_no: str = "P00") -> dict[str, Any]:
    """연구자 콘솔의 세션 생성 (§8.2 `POST /admin/sessions`)."""
    response = await client.post(
        "/admin/sessions", json={"participant_no": participant_no}, auth=ADMIN_AUTH
    )
    assert response.status_code == 201, response.text
    return response.json()


async def join(client: AsyncClient, participant_no: str, access_code: str) -> dict[str, Any]:
    response = await client.post(
        "/api/join", json={"participant_no": participant_no, "access_code": access_code}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def open_and_join(
    client: AsyncClient, participant_no: str = "P00"
) -> tuple[dict[str, Any], dict[str, Any]]:
    created = await create_session(client, participant_no)
    state = await join(client, participant_no, created["access_code"])
    return created, state


async def state(client: AsyncClient) -> dict[str, Any]:
    response = await client.get("/api/state")
    assert response.status_code == 200, response.text
    return response.json()


async def advance(client: AsyncClient, from_screen: str) -> dict[str, Any]:
    response = await client.post("/api/advance", json={"from_screen": from_screen})
    assert response.status_code == 200, response.text
    return response.json()


async def consent(client: AsyncClient) -> dict[str, Any]:
    from app.assets.screen_copy import CONSENT_ITEMS

    response = await client.post(
        "/api/consent", json={"items": {item.field: True for item in CONSENT_ITEMS}}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def presurvey(client: AsyncClient) -> dict[str, Any]:
    """자산이 placeholder이므로 문항 유형에 맞는 아무 값이나 넣는다 `<TODO: PH-01>`."""
    current = await state(client)
    responses = []
    for item in current["data"]["items"]:
        if item["type"] == "multi_choice":
            value: Any = [item["options"][0]["value"]]
        elif item["type"] == "single_choice":
            value = item["options"][0]["value"]
        else:
            value = 4
        responses.append({"position": item["position"], "value": value})
    response = await client.post("/api/presurvey", json={"responses": responses})
    assert response.status_code == 200, response.text
    return response.json()


async def reach_branch_block(client: AsyncClient, participant_no: str = "P00") -> dict[str, Any]:
    """SS00 → SS04(branch 1의 B0)까지 한 번에 (P0 → P1 → P2 → P3)."""
    await open_and_join(client, participant_no)
    await consent(client)
    await presurvey(client)
    response = await client.post("/api/checkpoint/confirm")
    assert response.status_code == 200, response.text
    return response.json()


async def complete_branch(
    client: AsyncClient,
    branch_index: int,
    disposition: str = "reply",
    *,
    sidecar_choice: str = "none",
    downstream_code: str = "pause",
) -> dict[str, Any]:
    """P4 → P9까지 한 branch 전체 (§3.2 B0 → B7)."""
    await advance(client, "P4")
    body: dict[str, Any] = {"disposition": disposition}
    if disposition == "reply":
        body["text"] = "장기 계획 말고 장단점만 정리해줘"
    response = await client.post(f"/api/branch/{branch_index}/user1", json=body)
    assert response.status_code == 200, response.text

    response = await client.post(
        f"/api/branch/{branch_index}/sidecar", json={"choice": sidecar_choice}
    )
    assert response.status_code == 200, response.text

    if disposition == "reply":
        response = await client.post(f"/api/branch/{branch_index}/ai2")
        assert response.status_code == 200, response.text
        await advance(client, "P7")
        response = await client.post(
            f"/api/branch/{branch_index}/downstream", json={"code": downstream_code}
        )
        assert response.status_code == 200, response.text

    response = await client.post(f"/api/branch/{branch_index}/ratings", json=ratings_payload())
    assert response.status_code == 200, response.text
    return response.json()
