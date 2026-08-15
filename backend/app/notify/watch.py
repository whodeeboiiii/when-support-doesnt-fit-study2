"""직전 상태와 비교해야 판정되는 알림 트리거 (구현명세서 §2.8 · §2.2.2).

§2.8의 5트리거 중 3개(AI2 fallback·checker skipped·연구자 abort)는 "그 일이 일어난 자리"에서
바로 `notify()`를 부르면 된다. 나머지 2개는 상태가 필요하다.

- `provider_reported_model` 변경: 지난번에 본 문자열과 비교해야 한다(§2.2.2-②).
  **자동 차단은 하지 않는다** — PI 판단·cohort 분리 사안이므로 알리기만 한다.
- 서버 오류(5xx) 누적: 연속 카운터가 필요하다.

둘 다 프로세스 메모리에 둔다. 영속 기록은 이미 `llm_calls.provider_reported_model`(§8.4)이
갖고 있고, 여기서는 경보만 담당한다. 12세션 규모·단일 서비스라 이걸로 충분하다(§2.8).
"""

from __future__ import annotations

import logging

from app.notify.discord import NotifyEvent, notify

logger = logging.getLogger(__name__)

#: §2.8 "서버 오류(5xx) 누적" — 명세는 임계값을 고정하지 않는다.
#: 3회 연속을 개시값으로 둔다 [파일럿 확정: QA·soft launch 튜닝 창에서 1회 조정 가능].
SERVER_ERROR_STREAK_THRESHOLD = 3

_server_error_streak = 0
_last_provider_model: dict[str, str] = {}


def reset() -> None:
    """테스트·재시작 경계용. 프로덕션에서는 성공 1건이 스트릭을 지운다."""
    global _server_error_streak
    _server_error_streak = 0
    _last_provider_model.clear()


def record_server_success() -> None:
    global _server_error_streak
    _server_error_streak = 0


async def record_server_error(detail: str | None = None) -> None:
    """5xx 1건. 임계 도달 **순간에만** 1회 발화한다(스팸 방지)."""
    global _server_error_streak
    _server_error_streak += 1
    if _server_error_streak == SERVER_ERROR_STREAK_THRESHOLD:
        await notify(
            NotifyEvent.SERVER_ERROR_STREAK,
            f"서버 오류가 연속 {_server_error_streak}회 발생했다",
            detail=detail,
        )


async def check_provider_model(role: str, reported: str | None) -> None:
    """§2.2.2-② 응답 모델 문자열이 바뀌면 알린다(모델 동결 §1.4의 관측 장치)."""
    if not reported:
        return
    previous = _last_provider_model.get(role)
    _last_provider_model[role] = reported
    if previous is None or previous == reported:
        return
    await notify(
        NotifyEvent.PROVIDER_MODEL_CHANGED,
        f"{role} 응답 모델 문자열이 바뀌었다",
        previous=previous,
        current=reported,
    )
