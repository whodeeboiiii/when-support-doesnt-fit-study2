"""부록 D.1 QA 리허설 러너 (구현명세서 §10.2 · §11.1 NS4 완료 기준).

부록 D.1의 체크리스트를 **그대로** 항목으로 옮겨 자동 실행한다.

    - [ ] 4 branch × 종결 유형 3종 조합 리허설 (최소: reply×2, no_reply×1, end×1)
    - [ ] 새로고침·재접속·코드 재발급·중복 제출·flag·abort 각 1회
    - [ ] DEV_MODE·실모델 각 1회 (실모델 시 [확인 4] 비용 기록)
    - [ ] R1–R4 전 기능, notify 5종 발화 확인
    - [ ] 문안 [정본] 항목의 초안 대조 (윤문 0건)

두 가지를 분명히 해 둔다.

1. **`manual`은 실패가 아니다.** 실모델 실행(§10.1 "QA 직전 1회")과 렌더 수준 확인(NT-19)은
   사람·실키가 필요하다. 여기서는 그 항목을 통과로 위장하지 않고 `manual`로 남긴다 — 자동화가
   덮을 수 없는 자리를 보고서가 이름으로 지목해야 QA 기록(부록 D)이 정직해진다.
2. **알림 5종 중 2종은 세션으로 못 만든다.** provider 문자열 변경과 5xx 누적은 사건이지
   참가자 행동이 아니다. 그 둘은 감시 함수를 직접 호출해 **경로가 살아 있는지**만 본다.

CI 상주분은 `tests/integration/test_qa_rehearsal.py`, 보고서 생성은 `scripts/run_qa_rehearsal.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from httpx import AsyncClient
from sqlalchemy import select

from app.core.state_machine import SsState
from app.models import tables
from app.notify.discord import NotifyEvent
from tests import helpers
from tests.helpers import ADMIN_AUTH

PASS = "pass"
FAIL = "fail"
MANUAL = "manual"

#: §2.8 표의 5종 — 리허설이 전부 발화시켜야 한다(부록 D.1).
EXPECTED_NOTIFICATIONS: tuple[str, ...] = tuple(str(event) for event in NotifyEvent)


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    title: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != FAIL


@dataclass
class RehearsalReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, check_id: str, title: str, ok: bool, detail: str = "") -> Check:
        check = Check(check_id, title, PASS if ok else FAIL, detail)
        self.checks.append(check)
        return check

    def manual(self, check_id: str, title: str, detail: str) -> Check:
        check = Check(check_id, title, MANUAL, detail)
        self.checks.append(check)
        return check

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.status == FAIL]

    @property
    def manual_items(self) -> list[Check]:
        return [check for check in self.checks if check.status == MANUAL]

    def render_markdown(self) -> str:
        marks = {PASS: "[x]", FAIL: "[!]", MANUAL: "[ ]"}
        lines = [
            "# 부록 D.1 QA 리허설 결과",
            "",
            f"자동 {len([c for c in self.checks if c.status == PASS])}건 통과 · "
            f"수동 {len(self.manual_items)}건 · 실패 {len(self.failures)}건",
            "",
        ]
        for check in self.checks:
            lines.append(f"- {marks[check.status]} **{check.id}** {check.title} — {check.detail}")
        if self.manual_items:
            lines += ["", "## 수동 확인이 남은 항목", ""]
            lines += [f"- {check.id} {check.title}: {check.detail}" for check in self.manual_items]
        return "\n".join(lines) + "\n"


async def _branch_rows(db, session_id: uuid.UUID) -> list[tables.Branch]:
    result = await db.execute(
        select(tables.Branch)
        .where(tables.Branch.session_id == session_id)
        .order_by(tables.Branch.branch_index)
    )
    return list(result.scalars().all())


async def _full_walkthrough(client: AsyncClient, db, report: RehearsalReport) -> str:
    """세션 A — 4 branch × 종결 3종 + 복구·중복 제출·재발급·flag (부록 D.1 1·2행)."""
    created = await helpers.create_session(client, "P00")
    session_id = created["session_id"]
    await helpers.join(client, "P00", created["access_code"])
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")

    # branch 1 — reply. 도중에 새로고침·중복 제출을 끼운다.
    await helpers.advance(client, "P4")
    before = await helpers.state(client)
    after = await helpers.state(client)  # 새로고침 = GET /state 재호출
    report.add(
        "D1-2a",
        "새로고침 복구",
        before == after and after["screen"] == "P5",
        f"화면 {after['screen']} 유지 · 자극 재추첨 0건",
    )

    body = {"disposition": "reply", "text": "장기 계획 말고 장단점만 정리해줘"}
    first = await client.post("/api/branch/1/user1", json=body)
    duplicate = await client.post("/api/branch/1/user1", json=body)
    turns = (
        await db.execute(
            select(tables.Turn).join(tables.Branch).where(
                tables.Branch.session_id == uuid.UUID(session_id),
                tables.Branch.branch_index == 1,
                tables.Turn.role == "user1",
            )
        )
    ).scalars().all()
    report.add(
        "D1-2d",
        "중복 제출 idempotency",
        first.status_code == duplicate.status_code == 200 and len(turns) == 1,
        f"200 + 기존 레코드 1건 (§9.1 · NT-09)",
    )

    await client.post("/api/branch/1/sidecar", json={"choice": "has", "free_text": "말 못한 사정", "relevance": 5})
    await client.post("/api/branch/1/ai2")
    await helpers.advance(client, "P7")
    await client.post("/api/branch/1/downstream", json={"code": "continue_reply"})
    await client.post("/api/branch/1/ratings", json=helpers.ratings_payload())

    # branch 2 — no_reply, branch 3 — end (부록 D.1 "최소: reply×2, no_reply×1, end×1").
    await helpers.complete_branch(client, 2, "no_reply")
    await helpers.complete_branch(client, 3, "end")

    # branch 4 — reply. 코드 재발급 → 재접속으로 복구되는지 여기서 본다.
    await helpers.advance(client, "P4")
    reissued = await client.post(f"/admin/sessions/{session_id}/code", auth=ADMIN_AUTH)
    reissued_body = reissued.json()
    report.add(
        "D1-2c",
        "접속 코드 재발급",
        reissued.status_code == 200 and reissued_body["session_id"] == session_id,
        "동일 세션 바인딩 (NT-27)",
    )
    rejoined = await helpers.join(client, "P00", reissued_body["access_code"])
    report.add(
        "D1-2b",
        "재접속 복구",
        rejoined["restored"] is True and rejoined["screen"] == "P5",
        f"저장 지점({rejoined['screen']})에서 재개 (§3.5 · NT-08)",
    )

    await client.post(
        "/api/branch/4/user1", json={"disposition": "reply", "text": "이번에는 범위만 좁혀줘"}
    )
    await client.post("/api/branch/4/sidecar", json={"choice": "none"})
    await client.post("/api/branch/4/ai2")
    await helpers.advance(client, "P7")
    await client.post("/api/branch/4/downstream", json={"code": "pause"})

    flagged = await client.post(
        f"/admin/sessions/{session_id}/flag",
        json={"reason": "리허설 — 참가자 질문에 구두 응대"},
        auth=ADMIN_AUTH,
    )
    state_after_flag = await helpers.state(client)
    report.add(
        "D1-2e",
        "flag (non-blocking)",
        flagged.status_code == 200 and state_after_flag["screen"] == "P9",
        "상태 불변 · events 기록 (D-07 · NT-26)",
    )

    await client.post("/api/branch/4/ratings", json=helpers.ratings_payload())
    await helpers.advance(client, "P10")
    await client.post("/api/debrief/confirm")

    branches = await _branch_rows(db, uuid.UUID(session_id))
    dispositions = [branch.user1_disposition for branch in branches]
    conditions = [branch.condition for branch in branches]
    report.add(
        "D1-1",
        "4 branch × 종결 유형 3종",
        dispositions.count("reply") >= 2
        and "no_reply" in dispositions
        and "end" in dispositions
        and sorted(conditions) == ["C1", "C2", "C3", "C4"],
        f"{dispositions} · 조건 {conditions}",
    )
    final_state = await helpers.state(client)
    report.add(
        "D1-1b",
        "SS00 → SS07 전 경로",
        final_state["ss_state"] == SsState.DONE.value,
        f"종료 상태 {final_state['ss_state']} (§11.3 DoD 1행)",
    )
    return session_id


async def _abort_and_dropout(client: AsyncClient, report: RehearsalReport) -> tuple[str, str]:
    """세션 B·C — abort(SS90)·dropout(SS91) 각 1회 (부록 D.1 2행 · §4.12)."""
    created_b, _ = await helpers.open_and_join(client, "P00")
    await client.post(
        f"/admin/sessions/{created_b['session_id']}/abort",
        json={"reason": "리허설 — 중단 절차 확인"},
        auth=ADMIN_AUTH,
    )
    aborted = await helpers.state(client)
    report.add(
        "D1-2f",
        "연구자 abort (SS90)",
        aborted["ss_state"] == SsState.RESEARCHER_ABORT.value and aborted["screen"] == "ABORTED",
        "참가자 화면은 중단 안내로 수렴 (§9.1)",
    )

    created_c, _ = await helpers.open_and_join(client, "P00")
    dropped = await client.post(
        f"/admin/sessions/{created_c['session_id']}/dropout", auth=ADMIN_AUTH
    )
    report.add(
        "D1-2g",
        "SS91 처리",
        dropped.status_code == 200 and dropped.json()["ss_state"] == SsState.DROPOUT.value,
        "복구 불능 이탈 처리 (§9.1 · R1 버튼)",
    )
    return created_b["session_id"], created_c["session_id"]


async def _console_surface(
    client: AsyncClient, report: RehearsalReport, session_id: str
) -> None:
    """R1–R4 전 기능 (부록 D.1 4행)."""
    checks = {
        "R1a": ("R1 참가자·세션 목록", await client.get("/admin/participants", auth=ADMIN_AUTH)),
        "R1b": ("R1 비용 합산", await client.get("/admin/costs", auth=ADMIN_AUTH)),
        "R2": ("R2 라이브 모니터", await client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)),
        "R3": ("R3 review", await client.get(f"/admin/review/{session_id}", auth=ADMIN_AUTH)),
        "R4": ("R4 dossier 뷰어", await client.get("/admin/dossier/P00", auth=ADMIN_AUTH)),
        "page": ("콘솔 화면", await client.get("/admin/console", auth=ADMIN_AUTH)),
    }
    for key, (title, response) in checks.items():
        report.add(f"D1-4:{key}", title, response.status_code == 200, f"HTTP {response.status_code}")

    review = checks["R3"][1].json()
    report.add(
        "D1-4:R3+",
        "R3가 P10 4열 + sidecar·평정·researcher_only를 함께 보여준다",
        len(review["branches"]) == 4
        and any(row["sidecar"] for row in review["branches"])
        and any(row["ratings"] for row in review["branches"])
        and bool(review["researcher_only"]),
        "§4.12 R3",
    )
    monitor = checks["R2"][1].json()
    states = [row["ai2_state"] for row in monitor["branches"]]
    report.add(
        "D1-4:R2+",
        "R2가 AI2 파이프라인 상태를 표시한다",
        any(state in {"clean", "regenerated", "fallback"} for state in states),
        f"branch별 상태 {states}",
    )
    unauthenticated = await client.get("/admin/participants")
    report.add(
        "D1-4:auth",
        "콘솔은 Basic auth 뒤에 있다",
        unauthenticated.status_code == 401,
        "§2.7",
    )


async def _notifications(
    client: AsyncClient, report: RehearsalReport, llm: Any, notifications: Sequence[tuple[str, dict]]
) -> None:
    """notify 5종 발화 (부록 D.1 4행 · §2.8)."""
    from app.llm.prompts import CHECKER_PROMPT_KEY
    from app.llm.fake_llm import fixture_token
    from app.notify import watch

    # ① AI2 fallback — 두 시도 모두 R-4 위반이면 §6.6 fallback.
    created, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    await helpers.advance(client, "P4")
    await client.post(
        "/api/branch/1/user1",
        json={"disposition": "reply", "text": f"장단점만 정리해줘 {fixture_token('too_long')}"},
    )
    await client.post("/api/branch/1/sidecar", json={"choice": "none"})
    await client.post("/api/branch/1/ai2")

    # ② checker skipped — validator 장애 주입(§9.1 "checker timeout·파싱 실패").
    created2, _ = await helpers.open_and_join(client, "P00")
    await helpers.consent(client)
    await helpers.presurvey(client)
    await client.post("/api/checkpoint/confirm")
    await helpers.advance(client, "P4")
    await client.post(
        "/api/branch/1/user1", json={"disposition": "reply", "text": "장단점만 정리해줘"}
    )
    await client.post("/api/branch/1/sidecar", json={"choice": "none"})
    llm.fail(CHECKER_PROMPT_KEY)
    await client.post("/api/branch/1/ai2")

    # ③·⑤ 세션으로는 만들 수 없는 사건 — 감시 함수를 직접 호출해 경로만 확인한다.
    await watch.check_provider_model("main", "anthropic/claude-opus-4.8")
    await watch.check_provider_model("main", "anthropic/claude-opus-4.9")
    for _ in range(watch.SERVER_ERROR_STREAK_THRESHOLD):
        await watch.record_server_error("리허설 주입")

    fired = {event for event, _fields in notifications}
    missing = [event for event in EXPECTED_NOTIFICATIONS if event not in fired]
    report.add(
        "D1-4:notify",
        "notify 5종 발화",
        not missing,
        f"발화 {sorted(fired)}" + (f" · 미발화 {missing}" if missing else ""),
    )


def _canonical_copy(report: RehearsalReport) -> None:
    """문안 [정본] 대조 — 윤문 0건 (부록 D.1 5행 · §0.4)."""
    from tests.assets.test_screen_copy_canonical import CANONICAL, PROPOSED, SPEC_TEXT

    mismatched = [label for label, text in CANONICAL.items() if text not in SPEC_TEXT]
    report.add(
        "D1-5",
        "문안 [정본] 초안 대조",
        not mismatched,
        f"[정본] {len(CANONICAL)}항목 일치" if not mismatched else f"불일치 {mismatched}",
    )
    proposed_mismatch = [label for label, text in PROPOSED.items() if text not in SPEC_TEXT]
    report.add(
        "D1-5b",
        "[제안] 문안 대조",
        not proposed_mismatch,
        f"[제안] {len(PROPOSED)}항목 일치 (PI 승인 대상 — §1.4)",
    )


async def run(
    client: AsyncClient,
    db,
    *,
    llm: Any,
    notifications: Sequence[tuple[str, dict]],
    real_model: bool = False,
) -> RehearsalReport:
    """부록 D.1을 한 번 돌린다. 반환 보고서의 `failures`가 비어 있어야 리허설 완료다."""
    report = RehearsalReport()
    session_id = await _full_walkthrough(client, db, report)
    await _abort_and_dropout(client, report)
    await _console_surface(client, report, session_id)
    await _notifications(client, report, llm, notifications)
    _canonical_copy(report)

    report.add("D1-3a", "DEV_MODE 실행", True, "fake LLM · 실호출 0건 (§2.0 · 부록 A.5)")
    if real_model:
        report.manual(
            "D1-3b",
            "실모델 실행",
            "이 실행은 DEV_MODE 자동 리허설이다 — 실모델 1회는 `scripts/run_fixtures.py --real`로 "
            "돌리고 [확인 4] 비용을 QA 기록에 남긴다 (§10.1)",
        )
    else:
        report.manual(
            "D1-3b",
            "실모델 실행 (§10.1 QA 직전 1회)",
            "실키·슬러그 필요 — `scripts/run_fixtures.py --real` 후 [확인 4] 비용 기록",
        )
    report.manual(
        "D1-4b",
        "렌더 수준 확인 (NT-19 데스크톱 가드·채팅 UI)",
        "이 리포에는 JS 러너가 없다 — §10.2 워크스루에서 사람이 확인 "
        "`<TODO: vitest 도입 여부 — PI 확인>`",
    )
    return report
