"""오프라인 fixture 러너 (구현명세서 §10.1 — 구 `tests/alpha_runner.py` 개조).

§10의 3층 검증에서 부록 C의 NT 테스트가 "코드가 정해진 대로 도는가"라면, 여기는 **"판정이
기대와 일치하는가"**를 케이스 분포로 본다. 그래서 fixture 텍스트를 실제 런타임 경로 그대로
태운다 — `llm.normalization.normalize`와 `llm.integrity_rules.check_all` · `llm.checker.run`은
참가자 세션이 부르는 바로 그 함수다.

    통과 기준(§10.1): 결정론 케이스 100%. LLM checker는
    [파일럿 확정: 위반 검출 누락 0을 목표로 문항별 분석] — fake LLM(CI)에서는 결정론이므로
    100%를 걸고, 실모델 실행(QA 직전 1회)에서는 게이트 없이 분포를 보고한다.

이 파일은 `test_*.py`가 아니므로 pytest가 수집하지 않는다 — 러너는 라이브러리이고,
CI 상주분은 `tests/integration/test_fixture_runner.py`, 수동 실행은 `scripts/run_fixtures.py`다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import dossier_loader
from app.llm import checker as checker_module
from app.llm import normalization
from app.llm.integrity_rules import ForbiddenText, check_all

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "fixtures"
NORMALIZATION_FIXTURE = FIXTURES_DIR / "normalization_fixture_v1.jsonl"
INTEGRITY_FIXTURE = FIXTURES_DIR / "integrity_fixture_v1.jsonl"

#: §10.1 통과 기준. None = 게이트 없음(분포만 본다).
NORMALIZATION_THRESHOLDS: dict[str, float | None] = {"A": 1.0, "B": 1.0, "C": 1.0}
INTEGRITY_THRESHOLDS: dict[str, float | None] = {"R": 1.0, "C": 1.0}

#: checker fixture가 쓰는 고정 맥락. 판정 대상은 **초안**이므로 맥락은 어느 것이든 같아야 한다.
CHECKER_CONTEXT_PARTICIPANT = "P00"
CHECKER_USER1 = "장기 계획 말고 장단점만 정리해줘"


@dataclass(frozen=True, slots=True)
class CaseResult:
    id: str
    block: str
    passed: bool
    expected: Any
    actual: Any
    note: str = ""


@dataclass(slots=True)
class FixtureReport:
    name: str
    path: Path
    results: list[CaseResult] = field(default_factory=list)

    @property
    def blocks(self) -> list[str]:
        return sorted({result.block for result in self.results})

    def in_block(self, block: str) -> list[CaseResult]:
        return [result for result in self.results if result.block == block]

    def pass_rate(self, block: str | None = None) -> float:
        subset = self.results if block is None else self.in_block(block)
        if not subset:
            return 1.0
        return sum(1 for result in subset if result.passed) / len(subset)

    def failures(self) -> list[CaseResult]:
        return [result for result in self.results if not result.passed]

    def gate_failures(self, thresholds: dict[str, float | None]) -> list[str]:
        """기준 미달 블록. 빈 목록이면 통과다."""
        breaches: list[str] = []
        for block in self.blocks:
            threshold = thresholds.get(block)
            if threshold is None:
                continue
            rate = self.pass_rate(block)
            if rate < threshold:
                breaches.append(f"{self.name} 블록 {block}: {rate:.0%} < 기준 {threshold:.0%}")
        return breaches


def load_cases(path: Path) -> list[dict[str, Any]]:
    """jsonl에서 케이스만 읽는다 — `id` 없는 줄(머리말 주석)은 건너뛴다."""
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        document = json.loads(line)
        if isinstance(document, dict) and document.get("id"):
            cases.append(document)
    if not cases:
        raise ValueError(f"{path}: 케이스가 없다")
    return cases


# --------------------------------------------------------------------------- #
# normalization (§6.4 · NT-24)
# --------------------------------------------------------------------------- #


def _referents(raw: Sequence[dict[str, Any]]) -> tuple[dossier_loader.ReferentEntry, ...]:
    return tuple(
        dossier_loader.ReferentEntry(
            patterns=tuple(entry.get("patterns", ())), proposition=entry.get("proposition", "")
        )
        for entry in raw
    )


def run_normalization_fixture(path: Path = NORMALIZATION_FIXTURE) -> FixtureReport:
    """지시표현 치환 케이스 전수. 실호출·DB 없이 돈다(순수 함수)."""
    report = FixtureReport(name="normalization", path=path)
    for case in load_cases(path):
        expected = case["expect"]
        result = normalization.normalize(case["user1"], _referents(case.get("referent_map", [])))
        actual = {
            "applied": result.applied,
            "pattern": result.matched_pattern_id,
            "referent": result.referent_id,
            "substituted": result.substituted,
        }
        report.results.append(
            CaseResult(
                id=case["id"],
                block=case.get("block", "A"),
                passed=all(actual[key] == value for key, value in expected.items()),
                expected=expected,
                actual=actual,
                note=case.get("note", ""),
            )
        )
    return report


# --------------------------------------------------------------------------- #
# integrity (§6.5 · NT-25)
# --------------------------------------------------------------------------- #


def _forbidden(raw: Sequence[dict[str, Any]]) -> list[ForbiddenText]:
    return [
        ForbiddenText(
            rule=entry["rule"],
            source=entry.get("source", "fixture"),
            text=entry["text"],
            whole_only=bool(entry.get("whole_only", False)),
        )
        for entry in raw
    ]


async def run_integrity_fixture(
    session: AsyncSession, path: Path = INTEGRITY_FIXTURE
) -> FixtureReport:
    """규칙 계층 전수 + checker 블록. checker는 주입된 클라이언트(CI=fake)로 판정한다."""
    report = FixtureReport(name="integrity", path=path)
    ai_visible = dossier_loader.load(CHECKER_CONTEXT_PARTICIPANT).ai_visible

    for case in load_cases(path):
        expected = case["expect"]
        draft = case["draft"]
        violations = check_all(
            draft, _forbidden(case.get("forbidden", [])), allowed=case.get("allowed", "")
        )
        actual: dict[str, Any] = {"rules": sorted({v.rule for v in violations})}
        passed = actual["rules"] == sorted(expected.get("rules", []))

        if "checker_types" in expected:
            verdict = await checker_module.run(
                session,
                ai_visible=ai_visible,
                user1_normalized=CHECKER_USER1,
                draft=draft,
            )
            actual["checker_types"] = sorted(verdict.violation_types)
            actual["checker_skipped"] = verdict.skipped
            passed = passed and actual["checker_types"] == sorted(expected["checker_types"])

        report.results.append(
            CaseResult(
                id=case["id"],
                block=case.get("block", "R"),
                passed=passed,
                expected=expected,
                actual=actual,
                note=case.get("note", ""),
            )
        )
    return report


# --------------------------------------------------------------------------- #
# 보고
# --------------------------------------------------------------------------- #


def render_markdown(reports: Sequence[tuple[FixtureReport, dict[str, float | None]]]) -> str:
    lines = ["# fixture 실행 결과 (구현명세서 §10.1)", ""]
    for report, thresholds in reports:
        lines.append(f"## {report.name} — `{report.path.name}`")
        lines.append("")
        lines.append("| 블록 | 통과 | 전체 | 비율 | 기준 |")
        lines.append("|---|---|---|---|---|")
        for block in report.blocks:
            subset = report.in_block(block)
            passed = sum(1 for result in subset if result.passed)
            threshold = thresholds.get(block)
            lines.append(
                f"| {block} | {passed} | {len(subset)} | {report.pass_rate(block):.0%} | "
                f"{'—' if threshold is None else f'{threshold:.0%}'} |"
            )
        lines.append("")
        failures = report.failures()
        if failures:
            lines.append("### 불일치")
            lines.append("")
            for failure in failures:
                lines.append(f"- **{failure.id}** ({failure.note})")
                lines.append(f"  - 기대: `{failure.expected}`")
                lines.append(f"  - 실제: `{failure.actual}`")
            lines.append("")
        breaches = report.gate_failures(thresholds)
        lines.append("**게이트: " + ("통과**" if not breaches else "미달** — " + "; ".join(breaches)))
        lines.append("")
    return "\n".join(lines)
