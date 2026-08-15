"""운영 알림 (§2.8 — v5.0 `notify` 이식).

두 규율만 본다: 알림이 파이프라인을 죽이지 않는다, 그리고 트리거 목록이 명세의 5종이다.
"""

from __future__ import annotations

import pytest

from app.notify import watch
from app.notify.discord import NotifyEvent, notify


def test_trigger_list_is_exactly_the_five_in_spec() -> None:
    assert {str(event) for event in NotifyEvent} == {
        "ai2_fallback_used",
        "checker_skipped",
        "provider_model_changed",
        "researcher_abort",
        "server_error_streak",
    }


async def test_notify_without_webhook_is_a_no_op() -> None:
    """webhook 미설정은 로컬·CI의 정상 상태다 — 예외가 아니라 False."""
    sent = await notify(NotifyEvent.AI2_FALLBACK_USED, "fallback 사용", participant_no="P00")
    assert sent is False


async def test_notify_swallows_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """§9.1 dead-end 금지는 알림 경로에도 적용된다."""
    from app.notify import discord

    monkeypatch.setattr(discord.get_settings(), "discord_webhook_url", "https://example.invalid/hook")

    async def boom(url: str, content: str) -> None:
        raise RuntimeError("webhook down")

    monkeypatch.setattr(discord, "_post", boom)
    assert await notify(NotifyEvent.CHECKER_SKIPPED, "checker 생략") is False


async def test_provider_model_change_fires_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """§2.2.2-② 최초 변경 감지에만 발화한다 — 자동 차단은 하지 않는다."""
    fired: list[tuple[str, str]] = []

    async def record(event, summary, **fields):  # noqa: ANN001, ANN003
        fired.append((str(event), summary))
        return True

    monkeypatch.setattr(watch, "notify", record)

    await watch.check_provider_model("main", "anthropic/claude-opus-4.8")
    await watch.check_provider_model("main", "anthropic/claude-opus-4.8")
    assert fired == []

    await watch.check_provider_model("main", "anthropic/claude-opus-4.9")
    assert [event for event, _ in fired] == ["provider_model_changed"]


async def test_server_error_streak_fires_at_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: list[str] = []

    async def record(event, summary, **fields):  # noqa: ANN001, ANN003
        fired.append(str(event))
        return True

    monkeypatch.setattr(watch, "notify", record)

    for _ in range(watch.SERVER_ERROR_STREAK_THRESHOLD - 1):
        await watch.record_server_error()
    assert fired == []

    await watch.record_server_error()
    assert fired == ["server_error_streak"]

    # 임계 도달 후 반복 발화하지 않는다(스팸 방지).
    await watch.record_server_error()
    assert fired == ["server_error_streak"]
