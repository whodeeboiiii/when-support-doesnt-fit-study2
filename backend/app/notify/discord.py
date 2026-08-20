"""운영 알림 — Discord webhook `notify()` 단일 함수 (구현명세서 §2.8 — v5.0 §2.8 ADAPT).

§2.8의 트리거는 **6종**이다 — v1.0.1의 5종 + `checkpoint_cue_edited`(v2 신설, D-25).
두 가지 규율이 이 모듈의 전부다(v5.0에서 승계).

1. **알림이 파이프라인을 죽이지 않는다.** webhook 장애·타임아웃은 삼키고 로그만 남긴다 —
   §9.1의 dead-end 금지는 알림 경로에도 적용된다.
2. **payload에 참가자 원문이 들어가지 않는다.** 참가자 번호·세션 id·상태값·카운트만 보낸다.
   Discord는 연구 시스템 밖이므로(§9.3) User1·sidecar·AI2·checkpoint 수정 내용은 금지다.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: 알림 1건에 쓰는 상한. 이 경로에서 오래 기다리면 참가자 요청이 같이 늦어진다.
NOTIFY_TIMEOUT_S = 5.0


class NotifyEvent(StrEnum):
    """§2.8 트리거 표 — 6종. 새 트리거를 늘리려면 명세 개정이 먼저다."""

    AI2_FALLBACK_USED = "ai2_fallback_used"
    CHECKER_SKIPPED = "checker_skipped"
    PROVIDER_MODEL_CHANGED = "provider_model_changed"
    RESEARCHER_ABORT = "researcher_abort"
    SERVER_ERROR_STREAK = "server_error_streak"
    #: v2 신설(§2.8 · §3.4) — checkpoint의 `trouble_cue`·`problematic_ai_response` 수정.
    #: 자극의 전제가 흔들릴 수 있어 연구자가 Zoom에서 **즉시 구두 확인**해야 한다.
    #: 시스템은 막지 않는다 — 계속/abort 판단은 사람이 한다(부록 D.3).
    CHECKPOINT_CUE_EDITED = "checkpoint_cue_edited"


async def _post(url: str, content: str) -> None:
    async with httpx.AsyncClient(timeout=NOTIFY_TIMEOUT_S) as http:
        response = await http.post(url, json={"content": content})
        response.raise_for_status()


def _format(event: NotifyEvent, summary: str, fields: dict[str, object]) -> str:
    detail = " · ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    line = f"[{get_settings().study_version}] **{event}** — {summary}"
    return f"{line}\n{detail}" if detail else line


async def notify(event: NotifyEvent, summary: str, **fields: object) -> bool:
    """§2.8 알림 1건. 전송했으면 True.

    webhook 미설정은 정상 상태다(로컬·CI). 그때는 로그만 남기고 False를 돌려준다.
    """
    content = _format(event, summary, fields)
    url = get_settings().discord_webhook_url
    if not url:
        logger.info("notify(미설정): %s", content)
        return False

    try:
        await _post(url, content)
    except Exception:  # noqa: BLE001 — 알림 실패로 참가자 경로를 끊지 않는다
        logger.exception("Discord 알림 전송 실패: %s", event)
        return False
    return True
