"""부록 D.1 QA 리허설 — CI 상주 (구현명세서 §10.2 · §11.1 V2-4 완료 기준).

리허설을 사람이 손으로 도는 것은 QA 당일 1회지만, **그 경로가 언제나 살아 있는지**는 매
커밋 확인할 수 있다. 여기서는 D.1 체크리스트를 자동 실행하고 실패 0건을 요구한다.

수동 항목(실모델 1회·렌더 확인)은 통과로 위장하지 않는다 — 목록에 이름이 남고, 그 목록이
늘었는지도 함께 본다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests import helpers, qa_rehearsal

#: 자동화가 덮을 수 없다고 선언한 항목. 늘어나면 그 자체가 리뷰 대상이다.
EXPECTED_MANUAL = {"D1-5b", "D1-5c"}

#: 부록 D.1의 여섯 줄. 각 줄이 최소 1항목으로 나타나야 한다.
CHECKLIST_ROWS = {
    "D1-1": "checkpoint 수정 0회 / 일반 segment 1회 / trouble_cue 수정(경보·notify)",
    "D1-2": "User2 reply 1회 · end 6유형 각 1회",
    "D1-3": "대안 3종 순서·pair 3종 좌우가 배정표와 일치",
    "D1-4": "새로고침·재접속·코드 재발급·중복 제출·flag·abort 각 1회",
    "D1-5": "DEV_MODE·실모델 각 1회, R1–R4, notify 6종",
    "D1-6": "[정본] 7건 초안 대조 (윤문 0건)",
}


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
    """부록 D.1의 여섯 줄이 각각 최소 1항목으로 나타나는지.

    항목 id는 `D1-<줄><변형>[:<세부>]` 꼴이다(예: `D1-4e`, `D1-5:R3+`). 줄 번호만 뽑는다.
    """
    import re

    covered = {
        match.group(0)
        for check in report.checks
        if (match := re.match(r"D1-\d+", check.id))
    }
    missing = {row: title for row, title in CHECKLIST_ROWS.items() if row not in covered}
    assert not missing, f"부록 D.1에서 덮이지 않은 줄: {missing}"


async def test_notify_six_triggers_fire(report: qa_rehearsal.RehearsalReport) -> None:
    """§2.8 표 6종 — 하나라도 빠지면 운영 중 그 사건이 조용히 지나간다."""
    check = next(item for item in report.checks if item.id == "D1-5:notify")
    assert check.status == qa_rehearsal.PASS, check.detail


async def test_checkpoint_edit_alert_is_rehearsed(
    report: qa_rehearsal.RehearsalReport,
) -> None:
    """부록 D.1 1행 — trouble_cue 수정 시 경보·notify가 실제로 나는지 리허설이 확인한다."""
    check = next(item for item in report.checks if item.id == "D1-1:edit2")
    assert check.status == qa_rehearsal.PASS, check.detail


async def test_all_six_end_types_are_rehearsed(
    report: qa_rehearsal.RehearsalReport,
) -> None:
    """부록 D.1 2행 — 이탈 유형 6종 각 1회(§4.7 · NT-41)."""
    check = next(item for item in report.checks if item.id == "D1-2b")
    assert check.status == qa_rehearsal.PASS, check.detail


async def test_markdown_report_lists_every_check(report: qa_rehearsal.RehearsalReport) -> None:
    rendered = report.render_markdown()
    for check in report.checks:
        assert check.id in rendered
    assert "수동 확인이 남은 항목" in rendered
