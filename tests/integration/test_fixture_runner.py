"""NT-25 — integrity fixture v2 결정론부 100% (구현명세서 §10.1 · §11.1 V2-3 완료 기준).

    integrity fixture v2 … 규칙 계층은 100%, LLM checker는 [파일럿 확정] — fake LLM로 CI 상주.

**NT-24(normalization fixture)는 폐기됐다**(부록 C — D-34). 대신 블록 A(대안 segment
overlap)가 들어왔고, 그건 **위반이 아니라 플래그**라는 것이 이 블록의 요점이다.

러너 자체(`tests/fixture_runner.py`)는 실행 경로를 재구현하지 않고 런타임 함수를 그대로 부른다.
그래서 이 테스트가 green이라는 것은 "fixture가 통과했다"가 아니라 **"참가자 세션이 쓰는 판정
함수가 fixture 기대와 일치한다"**는 뜻이다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from tests import fixture_runner


async def test_nt25_integrity_rule_layer_is_fully_deterministic(session: AsyncSession) -> None:
    report = await fixture_runner.run_integrity_fixture(session)
    assert report.pass_rate("R") == 1.0, [
        (failure.id, failure.expected, failure.actual) for failure in report.failures()
    ]


async def test_checker_block_passes_with_the_fake_client(session: AsyncSession) -> None:
    """fake LLM은 규칙표 기반 결정론이므로(부록 A.5) checker 블록도 100%다.

    실모델 실행(§10.1 — QA 직전 1회)에서는 이 블록에 게이트를 걸지 않는다.
    """
    report = await fixture_runner.run_integrity_fixture(session)
    assert report.gate_failures(fixture_runner.INTEGRITY_THRESHOLDS) == []
    assert report.pass_rate("C") == 1.0, [
        (failure.id, failure.expected, failure.actual) for failure in report.failures()
    ]


async def test_integrity_fixture_covers_every_violation_type(session: AsyncSession) -> None:
    """§10.1 — 위반 유형별 합성 출력이 다 있는가 (질문 2개·길이·누출·추론·확장·미반영·정상)."""
    cases = fixture_runner.load_cases(fixture_runner.INTEGRITY_FIXTURE)
    rules = {rule for case in cases for rule in case["expect"].get("rules", [])}
    # **R-2가 없다** — v2에서 위반이 아니라 플래그가 됐다(§6.4).
    assert rules == {"R-1", "R-3", "R-4"}
    checker_types = {
        violation
        for case in cases
        for violation in case["expect"].get("checker_types", [])
    }
    assert checker_types == {"unsupported_inference", "expansion", "correction_ignored"}
    # 정상 케이스가 없으면 "전부 위반"으로도 100%가 나온다.
    assert any(not case["expect"].get("rules") for case in cases)


async def test_alt_overlap_block_is_separate_from_violations(session: AsyncSession) -> None:
    """§6.4 R-2 — overlap 케이스가 `rules`가 아니라 `alt_overlap`으로 기대된다.

    이 분리가 무너지면 플래그가 위반으로 승격된 것이고, 그게 v2가 막으려는 실수다.
    """
    cases = fixture_runner.load_cases(fixture_runner.INTEGRITY_FIXTURE)
    overlap_cases = [case for case in cases if case.get("block") == "A"]
    assert overlap_cases, "블록 A(alt_overlap) 케이스가 없다"
    assert any(case["expect"]["alt_overlap"] for case in overlap_cases), "overlap 양성 케이스 없음"
    assert any(not case["expect"]["alt_overlap"] for case in overlap_cases), "음성 케이스 없음"
    for case in overlap_cases:
        assert "R-2" not in case["expect"].get("rules", []), "R-2가 위반 목록에 있다"

    report = await fixture_runner.run_integrity_fixture(session)
    assert report.pass_rate("A") == 1.0, [
        (failure.id, failure.expected, failure.actual) for failure in report.failures()
    ]


async def test_report_renders(session: AsyncSession) -> None:
    """QA 기록(부록 D)에 붙일 보고서가 실제로 만들어지는지."""
    integrity_report = await fixture_runner.run_integrity_fixture(session)
    document = fixture_runner.render_markdown(
        [(integrity_report, fixture_runner.INTEGRITY_THRESHOLDS)]
    )
    assert "integrity" in document
    assert "게이트: 통과" in document
    # 블록 셋이 표에 나온다.
    for block in ("R", "A", "C"):
        assert f"| {block} |" in document


def test_normalization_fixture_is_gone() -> None:
    """D-34 — normalization fixture·모듈이 v2에 없다(부록 H.1 삭제 목록)."""
    from pathlib import Path

    fixtures = Path(fixture_runner.FIXTURES_DIR)
    assert not (fixtures / "normalization_fixture_v1.jsonl").exists()
    assert not (fixtures / "normalization_patterns_v1.json").exists()
    assert not hasattr(fixture_runner, "run_normalization_fixture")
