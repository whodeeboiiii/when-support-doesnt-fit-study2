"""테스트 헬퍼 (구현명세서 §3 SS·F · §8.2).

v1.0.1의 B-루프 헬퍼(`complete_branch` ×4)는 v2.0 설계 전환으로 사라졌다. 신판은 **focal
1회 + 대안 3 + pairwise 3**을 안다.

의도적으로 **얇게** 유지한다: 요청을 대신 보내 주기만 하고 상태를 계산하지 않는다. 헬퍼가
상태를 알기 시작하면 테스트가 서버 대신 헬퍼를 검증하게 된다. 다만 **문항 수는 자산에서
읽는다** — 문항이 placeholder라 개수가 바뀔 수 있고, 헬퍼에 숫자를 박으면 자산 교체가
테스트를 깨뜨린다.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import ADMIN_PASS, ADMIN_USER

ADMIN_AUTH = (ADMIN_USER, ADMIN_PASS)

#: §2.8 알림을 부르는 모듈들. `from … import notify`로 들여왔으므로 **호출부마다** 갈아끼운다.
NOTIFY_CALL_SITES = (
    "app.api.admin",
    "app.api.participant",
    "app.llm.ai2_pipeline",
    "app.llm.checker",
    "app.notify.watch",
)


def route_table(app) -> list[tuple[str, tuple[str, ...]]]:
    """앱이 실제로 여는 (경로, 메서드) 목록.

    FastAPI 0.141의 `include_router`는 하위 라우터를 `_IncludedRouter`로 감싸므로
    `app.routes`를 그냥 훑으면 개별 경로가 보이지 않는다 — `original_router`로 들어간다.
    """
    routes: list[tuple[str, tuple[str, ...]]] = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        candidates = original.routes if original is not None else [route]
        for candidate in candidates:
            methods = getattr(candidate, "methods", None)
            if methods:
                routes.append((candidate.path, tuple(sorted(methods))))
    return sorted(set(routes))


def capture_notifications(monkeypatch) -> list[tuple[str, dict[str, Any]]]:
    """§2.8 트리거 발화를 가로챈다 (전송은 하지 않는다). 반환 리스트에 (event, fields)가 쌓인다."""
    import importlib

    captured: list[tuple[str, dict[str, Any]]] = []

    async def _record(event, summary: str, **fields: Any) -> bool:
        captured.append((str(event), {"summary": summary, **fields}))
        return True

    for module_name in NOTIFY_CALL_SITES:
        monkeypatch.setattr(importlib.import_module(module_name), "notify", _record)
    return captured


# --------------------------------------------------------------------------- #
# 제출 payload
# --------------------------------------------------------------------------- #


def ratings_payload(value: int = 4) -> dict[str, Any]:
    """§4.8 focal 5 construct + MC 2 — 전 문항에 같은 값. 값 자체는 관심사가 아니다."""
    from app.assets import rating_items

    count = rating_items.load().item_count
    return {"items": [{"position": position, "value": value} for position in range(1, count + 1)]}


def pairwise_payload(contrast: str, value: int = 4) -> dict[str, Any]:
    """§4.10 — contrast별 문항 수만큼."""
    from app.assets import pairwise_items

    count = len(pairwise_items.load().items_for(contrast))
    return {"items": [{"position": position, "value": value} for position in range(1, count + 1)]}


# --------------------------------------------------------------------------- #
# 세션 진행
# --------------------------------------------------------------------------- #


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


async def presurvey(client: AsyncClient, likert: int = 4) -> dict[str, Any]:
    """v1.0.1 §4.2 · D-44 — 전 문항 필수.

    값은 **자산에서** 만든다. 문항 수도 유형도 placeholder라 바뀔 수 있고(PH-01), 여기에
    응답표를 박아 두면 자산 교체가 관계없는 테스트를 깨뜨린다(`ratings_payload`와 같은 규율).
    """
    from app.assets import presurvey as asset

    survey = asset.load()
    responses: list[dict[str, Any]] = []
    for position, item in enumerate(survey.items, start=1):
        if item.type == "single_choice":
            value: Any = item.options[0].value
        elif item.type == "multi_choice":
            value = [item.options[0].value]
        else:
            value = likert
        responses.append({"position": position, "value": value})

    response = await client.post("/api/presurvey", json={"responses": responses})
    assert response.status_code == 200, response.text
    return response.json()


async def edit_checkpoint(client: AsyncClient, segment: str, text: str) -> dict[str, Any]:
    """§4.2 — segment 1건 수정 (D-25)."""
    response = await client.post(
        "/api/checkpoint/edit", json={"segment": segment, "text": text}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def confirm_checkpoint(client: AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/checkpoint/confirm")
    assert response.status_code == 200, response.text
    return response.json()


async def reach_focal(client: AsyncClient, participant_no: str = "P00") -> dict[str, Any]:
    """SS00 → SS04·F0까지 한 번에 (P0 → P1 → P1S → P2 → P3)."""
    await open_and_join(client, participant_no)
    await consent(client)
    await presurvey(client)
    await confirm_checkpoint(client)
    return await advance(client, "P3")


async def complete_focal(
    client: AsyncClient,
    *,
    user1: str = "장기 계획 말고 두 선택지 비교만 해줘",
    has_more: bool = False,
    disposition: str = "reply",
    end_type: str = "stop_here",
) -> dict[str, Any]:
    """P4 → P7까지 focal 전체 (§3.2 F0 → F5). 반환 상태는 P7(종료 안내)이다."""
    response = await client.post("/api/focal/user1", json={"text": user1})
    assert response.status_code == 200, response.text

    body: dict[str, Any] = {"has_more": has_more}
    if has_more:
        body |= {"free_text": "사실 한 가지 더 있었어", "provenance": "preexisting"}
    response = await client.post("/api/focal/sidecar", json=body)
    assert response.status_code == 200, response.text

    response = await client.post("/api/focal/ai2")
    assert response.status_code == 200, response.text
    await advance(client, "P6")

    payload: dict[str, Any] = {"disposition": disposition}
    if disposition == "reply":
        payload["text"] = "알겠어, 그렇게 정리해줘"
    else:
        payload |= {"end_type": end_type, "reason": "지금은 여기까지면 충분해서"}
    response = await client.post("/api/focal/downstream", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def submit_ratings(client: AsyncClient, value: int = 4) -> dict[str, Any]:
    """§4.8 — SS05 → SS06. 제출과 동시에 대안 노출 행 3건이 생긴다."""
    response = await client.post("/api/ratings", json=ratings_payload(value))
    assert response.status_code == 200, response.text
    return response.json()


async def complete_alt_exposures(client: AsyncClient) -> dict[str, Any]:
    """§4.9 — 세 대안을 순차로 넘긴다. 3번째에서 SS07로 간다."""
    current = await state(client)
    while current["screen"] == "P9":
        current = await advance(client, "P9")
    return current


async def complete_pairwise(client: AsyncClient, value: int = 4) -> dict[str, Any]:
    """§4.10 — 세 pair를 배정 순서대로 제출한다. 3번째에서 SS08로 간다."""
    current = await state(client)
    while current["screen"] == "P10":
        position = current["pair_index"]
        # contrast는 서버가 정한다 — 문항 수를 알기 위해 payload 크기만 맞춘다.
        count = len(current["data"]["items"])
        response = await client.post(
            f"/api/pairwise/{position}",
            json={"items": [{"position": index, "value": value} for index in range(1, count + 1)]},
        )
        assert response.status_code == 200, response.text
        current = response.json()
    return current


async def complete_session(
    client: AsyncClient, participant_no: str = "P00", **focal: Any
) -> dict[str, Any]:
    """SS00 → SS10 완주 (§11.2 Definition of Done 1행)."""
    await reach_focal(client, participant_no)
    await complete_focal(client, **focal)
    await advance(client, "P7")
    await submit_ratings(client)
    await complete_alt_exposures(client)
    await complete_pairwise(client)
    await advance(client, "P11")
    response = await client.post("/api/debrief/confirm")
    assert response.status_code == 200, response.text
    return response.json()
