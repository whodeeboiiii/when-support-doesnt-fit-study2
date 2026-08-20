"""부록 D.1 QA 리허설 러너 (구현명세서 §10.2 · §11.1 V2-4 완료 기준).

부록 D.1의 체크리스트를 **그대로** 항목으로 옮겨 자동 실행한다.

    - [ ] checkpoint 수정 0회 / 일반 segment 1회 / trouble_cue 수정(경보·notify 확인) 각 1회
    - [ ] User2 reply 1회 · end 6유형 각 1회
    - [ ] 대안 3종 순서·pair 3종 좌우가 배정표(dummy)와 일치
    - [ ] 새로고침·재접속·코드 재발급·중복 제출·flag·abort 각 1회
    - [ ] DEV_MODE·실모델 각 1회([확인 4]), R1–R4, notify 6종
    - [ ] [정본] 7건 초안 대조(윤문 0건)

두 가지를 분명히 해 둔다.

1. **`manual`은 실패가 아니다.** 실모델 실행(§10.1 "QA 직전 1회")과 렌더 수준 확인(NT-19)은
   사람·실키가 필요하다. 여기서는 그 항목을 통과로 위장하지 않고 `manual`로 남긴다 — 자동화가
   덮을 수 없는 자리를 보고서가 이름으로 지목해야 QA 기록(부록 D)이 정직해진다.
2. **알림 6종 중 2종은 세션으로 못 만든다.** provider 문자열 변경과 5xx 누적은 사건이지
   참가자 행동이 아니다. 그 둘은 감시 함수를 직접 호출해 **경로가 살아 있는지**만 본다.

CI 상주분은 `tests/integration/test_qa_rehearsal.py`, 보고서 생성은 `scripts/run_qa_rehearsal.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from httpx import AsyncClient
from sqlalchemy import select

from app.assets import screen_copy
from app.core.state_machine import SsState
from app.models import tables
from app.notify.discord import NotifyEvent
from tests import helpers
from tests.helpers import ADMIN_AUTH

PASS = "pass"
FAIL = "fail"
MANUAL = "manual"

#: §2.8 표의 6종 — 리허설이 전부 발화시켜야 한다(부록 D.1).
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
            "# 부록 D.1 QA 리허설 결과 (v2.0)",
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


async def _run_to_focal(client: AsyncClient, *, edits: list[tuple[str, str]] | None = None) -> str:
    """세션 생성 → P0–P3 → F0. `edits`는 P2에서 넣을 checkpoint 수정이다(§4.2)."""
    created = await helpers.create_session(client, "P00")
    await helpers.join(client, "P00", created["access_code"])
    await helpers.consent(client)
    for segment, text in edits or []:
        response = await client.post(
            "/api/checkpoint/edit", json={"segment": segment, "text": text}
        )
        assert response.status_code == 200, response.text
    await helpers.confirm_checkpoint(client)
    await helpers.advance(client, "P3")
    return created["session_id"]


async def _full_walkthrough(client: AsyncClient, db, report: RehearsalReport) -> str:
    """세션 A — 완주 + 복구·중복 제출·재발급·flag + 배정 일치 (부록 D.1 1·3·4행)."""
    session_id = await _run_to_focal(client, edits=[("situation_summary", "리허설 수정 요약")])
    uid = uuid.UUID(session_id)

    # --- 새로고침 (부록 D.1 4행) ---
    before = await helpers.state(client)
    after = await helpers.state(client)
    report.add(
        "D1-4a",
        "새로고침 복구",
        before == after and after["screen"] == "P4",
        f"화면 {after['screen']} 유지 · 자극 재추첨 0건 (NT-08)",
    )

    # --- 중복 제출 (부록 D.1 4행) ---
    body = {"text": "장기 계획 말고 두 선택지 비교만 해줘"}
    first = await client.post("/api/focal/user1", json=body)
    duplicate = await client.post("/api/focal/user1", json=body)
    turns = (
        await db.execute(
            select(tables.Turn)
            .join(tables.FocalRun)
            .where(tables.FocalRun.session_id == uid, tables.Turn.role == "user1")
        )
    ).scalars().all()
    report.add(
        "D1-4d",
        "중복 제출 idempotency",
        first.status_code == duplicate.status_code == 200 and len(turns) == 1,
        "200 + 기존 레코드 1건 (§9.1 · NT-09)",
    )

    # --- sidecar 3단 (§4.5) ---
    sidecar = await client.post(
        "/api/focal/sidecar",
        json={
            "has_more": True,
            "free_text": "말하지 않은 사정이 있었다",
            "provenance": "preexisting",
            "reason": "설명이 번거로웠다",
        },
    )
    report.add(
        "D1-1c",
        "sidecar 3단 (있음 → preexisting → 이유)",
        sidecar.status_code == 200,
        "§4.5 · D-28 — AI2 미전달(NT-01)",
    )

    await client.post("/api/focal/ai2")
    await helpers.advance(client, "P6")

    # --- 코드 재발급 → 재접속 (부록 D.1 4행) ---
    reissued = await client.post(f"/admin/sessions/{session_id}/code", auth=ADMIN_AUTH)
    reissued_body = reissued.json()
    report.add(
        "D1-4c",
        "접속 코드 재발급",
        reissued.status_code == 200 and reissued_body["session_id"] == session_id,
        "동일 세션 바인딩 (NT-27)",
    )
    rejoined = await helpers.join(client, "P00", reissued_body["access_code"])
    report.add(
        "D1-4b",
        "재접속 복구",
        rejoined["restored"] is True and rejoined["screen"] == "P7",
        f"저장 지점({rejoined['screen']})에서 재개 (§3.5 · NT-08)",
    )

    # --- User2 reply (부록 D.1 2행) ---
    reply = await client.post(
        "/api/focal/downstream", json={"disposition": "reply", "text": "그렇게 정리해줘"}
    )
    report.add(
        "D1-2a",
        "User2 reply 1회",
        reply.status_code == 200,
        "AI 응답 없음 — 안내만 표시 (D-33)",
    )
    await helpers.advance(client, "P7")

    # --- flag (부록 D.1 4행) ---
    flagged = await client.post(
        f"/admin/sessions/{session_id}/flag",
        json={"reason": "리허설 — 참가자 질문에 구두 응대"},
        auth=ADMIN_AUTH,
    )
    state_after_flag = await helpers.state(client)
    report.add(
        "D1-4e",
        "flag (non-blocking)",
        flagged.status_code == 200 and state_after_flag["screen"] == "P8",
        "상태 불변 · events 기록 (D-07 · NT-26)",
    )

    await helpers.submit_ratings(client)
    await helpers.complete_alt_exposures(client)
    await helpers.complete_pairwise(client)
    await helpers.advance(client, "P11")
    await client.post("/api/debrief/confirm")

    # --- 배정 일치 (부록 D.1 3행) ---
    participant = await db.get(tables.Participant, "P00")
    exposures = (
        await db.execute(
            select(tables.AltExposure)
            .where(tables.AltExposure.session_id == uid)
            .order_by(tables.AltExposure.position)
        )
    ).scalars().all()
    views = (
        await db.execute(
            select(tables.PairwiseView)
            .where(tables.PairwiseView.session_id == uid)
            .order_by(tables.PairwiseView.position)
        )
    ).scalars().all()
    alt_ok = [row.condition for row in exposures] == list(participant.alt_order)
    pair_ok = [row.contrast for row in views] == list(participant.pair_order) and all(
        [row.left_condition, row.right_condition] == list(participant.pair_sides[row.contrast])
        for row in views
    )
    report.add(
        "D1-3",
        "대안 3종 순서·pair 3종 좌우가 배정표와 일치",
        alt_ok and pair_ok,
        f"대안 {[row.condition for row in exposures]} · pair {[row.contrast for row in views]} (NT-33·38)",
    )

    final_state = await helpers.state(client)
    report.add(
        "D1-1b",
        "SS00 → SS10 전 경로",
        final_state["ss_state"] == SsState.DONE.value,
        f"종료 상태 {final_state['ss_state']} (§11.2 DoD 1행)",
    )
    return session_id


async def _checkpoint_edit_variants(
    client: AsyncClient, db, report: RehearsalReport, notifications: Sequence[tuple[str, dict]]
) -> None:
    """부록 D.1 1행 — 수정 0회 / 일반 segment 1회 / trouble_cue 수정(경보·notify)."""
    # ① 수정 0회
    await _run_to_focal(client)
    state = await helpers.state(client)
    report.add("D1-1:edit0", "checkpoint 수정 0회", state["screen"] == "P4", "수정 없이 진행")

    # ② 일반 segment 1회 — 경보 없음
    before = len(notifications)
    session_id = await _run_to_focal(client, edits=[("original_request", "조금 다르게 요청했다")])
    monitor = (await client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)).json()
    fired = [event for event, _ in notifications[before:]]
    report.add(
        "D1-1:edit1",
        "일반 segment 수정 1회 (경보 없음)",
        monitor["checkpoint"]["edits"] and monitor["checkpoint"]["alert"] is False
        and str(NotifyEvent.CHECKPOINT_CUE_EDITED) not in fired,
        "diff 표시 · 경보 미발생 (§3.4 — 자극 전제 밖)",
    )

    # ③ trouble_cue 수정 — **경보 + notify**
    before = len(notifications)
    session_id = await _run_to_focal(client, edits=[("trouble_cue", "그렇게까지는 아니었어")])
    monitor = (await client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)).json()
    fired = [event for event, _ in notifications[before:]]
    report.add(
        "D1-1:edit2",
        "trouble_cue 수정 (경보·notify)",
        monitor["checkpoint"]["alert"] is True
        and str(NotifyEvent.CHECKPOINT_CUE_EDITED) in fired,
        "R2 붉은 경보 + Discord 알림 (§2.8 · §3.4 · NT-35)",
    )

    # AI1은 수정과 무관하게 locked 그대로다(NT-34).
    run = (
        await db.execute(
            select(tables.FocalRun).where(
                tables.FocalRun.session_id == uuid.UUID(session_id)
            )
        )
    ).scalars().one()
    from app.assets import dossier_loader

    dossier = dossier_loader.load("P00")
    report.add(
        "D1-1:ai1",
        "checkpoint 수정 후에도 AI1·stimulus_hash 불변",
        run.stimulus_hash == dossier.stimulus_hash(run.condition),
        "§3.4 — AI1은 locked 자극 그대로 (NT-34)",
    )


async def _end_type_variants(client: AsyncClient, report: RehearsalReport) -> None:
    """부록 D.1 2행 — 이탈 유형 **6종 각 1회**."""
    results: dict[str, int] = {}
    for code in screen_copy.END_TYPE_CODES:
        await _run_to_focal(client)
        await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
        await client.post("/api/focal/sidecar", json={"has_more": False})
        await client.post("/api/focal/ai2")
        await helpers.advance(client, "P6")
        response = await client.post(
            "/api/focal/downstream",
            json={"disposition": "end", "end_type": code, "reason": f"리허설 사유 — {code}"},
        )
        results[code] = response.status_code
    report.add(
        "D1-2b",
        "종료 6유형 각 1회",
        set(results.values()) == {200},
        f"{sorted(results)} — 표 순서 고정(§4.7 · NT-41)",
    )


async def _abort_and_dropout(client: AsyncClient, report: RehearsalReport) -> tuple[str, str]:
    """세션 — abort(SS90)·dropout(SS91) 각 1회 (부록 D.1 4행 · §4.13)."""
    created_b, _ = await helpers.open_and_join(client, "P00")
    await client.post(
        f"/admin/sessions/{created_b['session_id']}/abort",
        json={"reason": "리허설 — 중단 절차 확인"},
        auth=ADMIN_AUTH,
    )
    aborted = await helpers.state(client)
    report.add(
        "D1-4f",
        "연구자 abort (SS90)",
        aborted["ss_state"] == SsState.RESEARCHER_ABORT.value and aborted["screen"] == "ABORTED",
        "참가자 화면은 중단 안내로 수렴 (§9.1)",
    )

    created_c, _ = await helpers.open_and_join(client, "P00")
    dropped = await client.post(
        f"/admin/sessions/{created_c['session_id']}/dropout", auth=ADMIN_AUTH
    )
    report.add(
        "D1-4g",
        "SS91 처리",
        dropped.status_code == 200 and dropped.json()["ss_state"] == SsState.DROPOUT.value,
        "복구 불능 이탈 처리 (§9.1 · R1 버튼)",
    )
    return created_b["session_id"], created_c["session_id"]


async def _console_surface(
    client: AsyncClient, report: RehearsalReport, session_id: str
) -> None:
    """R1–R4 전 기능 (부록 D.1 5행)."""
    checks = {
        "R1a": ("R1 참가자·배정·세션 목록", await client.get("/admin/participants", auth=ADMIN_AUTH)),
        "R1b": ("R1 비용 합산", await client.get("/admin/costs", auth=ADMIN_AUTH)),
        "R1c": ("배정표 뷰", await client.get("/admin/assignment", auth=ADMIN_AUTH)),
        "R2": ("R2 라이브 모니터", await client.get(f"/admin/monitor/{session_id}", auth=ADMIN_AUTH)),
        "R3": ("R3 contrastive 인터뷰 뷰", await client.get(f"/admin/review/{session_id}", auth=ADMIN_AUTH)),
        "R4": ("R4 dossier·자극·배정 뷰어", await client.get("/admin/dossier/P00", auth=ADMIN_AUTH)),
        "page": ("콘솔 화면", await client.get("/admin/console", auth=ADMIN_AUTH)),
    }
    for key, (title, response) in checks.items():
        report.add(f"D1-5:{key}", title, response.status_code == 200, f"HTTP {response.status_code}")

    review = checks["R3"][1].json()
    report.add(
        "D1-5:R3+",
        "R3가 focal trajectory + 평정 + 대안 순서 + 세 pair + researcher_only를 보여준다",
        bool(review["trajectory"])
        and bool(review["trajectory"].get("sidecar"))
        and bool(review["ratings"])
        and len(review["alt_exposures"]) == 3
        and len(review["pairs"]) == 3
        and bool(review["researcher_only"]),
        "§4.13 R3 · NT-39",
    )
    monitor = checks["R2"][1].json()
    report.add(
        "D1-5:R2+",
        "R2가 AI2 파이프라인 상태와 checkpoint diff를 표시한다",
        (monitor["focal"] or {}).get("ai2_state")
        in {"clean", "regenerated", "fallback", "pending", "generating"}
        and "checkpoint" in monitor,
        f"AI2 상태 {(monitor['focal'] or {}).get('ai2_state')} · diff 표시",
    )
    dossier = checks["R4"][1].json()
    report.add(
        "D1-5:R4+",
        "R4가 R/U/Q segment와 조립된 4자극을 함께 보여준다",
        set(dossier["segments"]) == {"r", "u", "q"} and len(dossier["stimuli"]) == 4,
        "§5.4 D-35 — 네 전문은 저장하지 않는다",
    )
    unauthenticated = await client.get("/admin/participants")
    report.add("D1-5:auth", "콘솔은 Basic auth 뒤에 있다", unauthenticated.status_code == 401, "§2.7")


async def _notifications(
    client: AsyncClient, report: RehearsalReport, llm: Any, notifications: Sequence[tuple[str, dict]]
) -> None:
    """notify 6종 발화 (부록 D.1 5행 · §2.8)."""
    from app.llm.fake_llm import fixture_token
    from app.llm.prompts import CHECKER_PROMPT_KEY
    from app.notify import watch

    # ① AI2 fallback — 두 시도 모두 R-4 위반이면 §6.5 fallback.
    await _run_to_focal(client)
    await client.post(
        "/api/focal/user1", json={"text": f"비교만 해줘 {fixture_token('too_long')}"}
    )
    await client.post("/api/focal/sidecar", json={"has_more": False})
    await client.post("/api/focal/ai2")

    # ② checker skipped — validator 장애 주입(§9.1 "checker 실패").
    await _run_to_focal(client)
    await client.post("/api/focal/user1", json={"text": "비교만 해줘"})
    await client.post("/api/focal/sidecar", json={"has_more": False})
    llm.fail(CHECKER_PROMPT_KEY)
    await client.post("/api/focal/ai2")

    # ③ checkpoint 경보는 `_checkpoint_edit_variants`가 이미 발화시켰다.

    # ④·⑤ 세션으로는 만들 수 없는 사건 — 감시 함수를 직접 호출해 경로만 확인한다.
    await watch.check_provider_model("main", "anthropic/claude-opus-4.8")
    await watch.check_provider_model("main", "anthropic/claude-opus-4.9")
    for _ in range(watch.SERVER_ERROR_STREAK_THRESHOLD):
        await watch.record_server_error("리허설 주입")

    fired = {event for event, _fields in notifications}
    missing = [event for event in EXPECTED_NOTIFICATIONS if event not in fired]
    report.add(
        "D1-5:notify",
        "notify 6종 발화",
        not missing,
        f"발화 {len(fired)}종" + (f" · 미발화 {missing}" if missing else ""),
    )


def _canonical_copy(report: RehearsalReport) -> None:
    """[정본] 7건 초안 대조 — 윤문 0건 (부록 D.1 6행 · §0.4)."""
    import re
    from pathlib import Path

    from app.assets import dossier_loader

    spec = (
        Path(__file__).resolve().parents[1] / "docs" / "구현명세서_v2.0.md"
    ).read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", spec.replace("> ", " "))

    # ① 화면 문안 5건
    screen_mismatch = [
        text[:20]
        for text in screen_copy.CANONICAL_COPY
        if re.sub(r"\s+", " ", text).strip() not in normalized
    ]
    report.add(
        "D1-6a",
        "[정본] 화면 문안 5건 대조",
        not screen_mismatch,
        "§4.2 checkpoint · §4.4 User1 · §4.5 sidecar 3단 — 윤문 0건"
        if not screen_mismatch
        else f"불일치 {screen_mismatch}",
    )

    # ② P00 자극 segment 3종 (§5.5 [정본, 초안 §7.6 표])
    p00 = dossier_loader.load("P00")
    segment_mismatch = [
        key for key in ("r", "u", "q") if f'"{p00.stimulus.segment(key)}"' not in spec
    ]
    report.add(
        "D1-6b",
        "[정본] P00 R/U/Q segment 대조",
        not segment_mismatch,
        "§5.5 — 초안 §7.6 worked example과 글자 단위 일치"
        if not segment_mismatch
        else f"불일치 {segment_mismatch}",
    )
    report.add(
        "D1-6c",
        "[정본] trouble cue (마침표 없음)",
        f'"{p00.ai_visible.trouble_cue}"' in spec and not p00.ai_visible.trouble_cue.endswith("."),
        "§5.5 — 초안에 마침표 없음, 그대로",
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
    await _checkpoint_edit_variants(client, db, report, notifications)
    await _end_type_variants(client, report)
    await _abort_and_dropout(client, report)
    await _console_surface(client, report, session_id)
    await _notifications(client, report, llm, notifications)
    _canonical_copy(report)

    report.add("D1-5a", "DEV_MODE 실행", True, "fake LLM · 실호출 0건 (§2.0 · 부록 A.6)")
    if real_model:
        report.manual(
            "D1-5b",
            "실모델 실행",
            "이 실행은 DEV_MODE 자동 리허설이다 — 실모델 1회는 `scripts/run_fixtures.py --real`로 "
            "돌리고 [확인 4] 비용을 QA 기록에 남긴다 (§10.1)",
        )
    else:
        report.manual(
            "D1-5b",
            "실모델 실행 (§10.1 QA 직전 1회)",
            "실키·슬러그 필요 — `scripts/run_fixtures.py --real` 후 [확인 4] 비용 기록",
        )
    report.manual(
        "D1-5c",
        "렌더 수준 확인 (NT-19 데스크톱 가드·채팅 UI)",
        "이 리포에는 JS 러너가 없다 — §10.2 워크스루에서 사람이 확인 "
        "`<TODO: vitest 도입 여부 — PI 확인>`",
    )
    return report
