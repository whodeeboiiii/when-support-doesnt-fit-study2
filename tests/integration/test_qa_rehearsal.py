"""부록 D.1 QA 리허설 — CI 상주 (구현명세서 §10.2 · §11.1 NS4 완료 기준).

리허설을 사람이 손으로 도는 것은 QA 당일 1회지만, **그 경로가 언제나 살아 있는지**는 매
커밋 확인할 수 있다. 여기서는 D.1 체크리스트를 자동 실행하고 실패 0건을 요구한다.

수동 항목(실모델 1회·렌더 확인)은 통과로 위장하지 않는다 — 목록에 이름이 남고, 그 목록이
줄었는지도 함께 본다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests import helpers, qa_rehearsal

#: 자동화가 덮을 수 없다고 선언한 항목. 늘어나면 그 자체가 리뷰 대상이다.
EXPECTED_MANUAL = {"D1-3b", "D1-4b"}


@pytest.fixture
async def report(client: AsyncClient, session, llm, monkeypatch: pytest.MonkeyPatch):
    notifications = helpers.capture_notifications(monkeypatch)
    return await qa_rehearsal.run(client, session, llm=llm, notifications=notifications)


async def test_rehearsal_has_no_failures(report: qa_rehearsal.RehearsalReport) -> None:
    assert report.failures == [], "\n".join(
        f"{check.id} {check.title}: {check.detail}" for check in report.failures
    )


async def test_manual_items_are_the_declared_ones(report: qa_rehearsal.RehearsalReport) -> None:
    assert {check.id for check in report.manual_items} == EXPECTED_MANUAL


async def test_every_checklist_row_of_appendix_d1_is_covered(
    report: qa_rehearsal.RehearsalReport,
) -> None:
    """부록 D.1의 다섯 줄이 각각 최소 1항목으로 나타나는지."""
    prefixes = {check.id.split(":")[0] for check in report.checks}
    assert {"D1-1", "D1-2a", "D1-2b", "D1-2c", "D1-2d", "D1-2e", "D1-2f", "D1-3a", "D1-4", "D1-5"} <= (
        prefixes | {check.id.split(":")[0] for check in report.checks}
    )


async def test_notify_five_triggers_fire(report: qa_rehearsal.RehearsalReport) -> None:
    """§2.8 표 5종 — 하나라도 빠지면 운영 중 그 사건이 조용히 지나간다."""
    check = next(item for item in report.checks if item.id == "D1-4:notify")
    assert check.status == qa_rehearsal.PASS, check.detail


async def test_markdown_report_lists_every_check(report: qa_rehearsal.RehearsalReport) -> None:
    rendered = report.render_markdown()
    for check in report.checks:
        assert check.id in rendered
    assert "수동 확인이 남은 항목" in rendered
