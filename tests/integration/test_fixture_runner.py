"""NT-24 · NT-25 — fixture 결정론부 100% (구현명세서 §10.1 · §11.1 NS3 완료 기준).

    normalization fixture … 통과 기준: 결정론 케이스 100%.
    integrity fixture … 규칙 계층은 100%, LLM checker는 [파일럿 확정] — fake LLM로 CI 상주.

러너 자체(`tests/fixture_runner.py`)는 실행 경로를 재구현하지 않고 런타임 함수를 그대로 부른다.
그래서 이 테스트가 green이라는 것은 "fixture가 통과했다"가 아니라 **"참가자 세션이 쓰는 판정
함수가 fixture 기대와 일치한다"**는 뜻이다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from tests import fixture_runner


def test_nt24_normalization_fixture_is_fully_deterministic() -> None:
    report = fixture_runner.run_normalization_fixture()
    assert report.gate_failures(fixture_runner.NORMALIZATION_THRESHOLDS) == []
    assert report.pass_rate() == 1.0, [
        (failure.id, failure.expected, failure.actual) for failure in report.failures()
    ]


def test_normalization_fixture_covers_the_spec_case_types() -> None:
    """§10.1이 요구한 케이스 유형 — 치환 대상·다의·무매칭·부분 인용."""
    cases = fixture_runner.load_cases(fixture_runner.NORMALIZATION_FIXTURE)
    notes = " ".join(case.get("note", "") for case in cases)
    for required in ("유일 매칭", "다의", "무매칭", "부분 인용", "최소 치환"):
        assert required in notes, f"fixture에 {required} 케이스가 없다"
    assert {case["expect"]["applied"] for case in cases} == {True, False}


def test_normalization_fixture_is_reproducible() -> None:
    """같은 입력에 같은 판정 — 두 번 돌려 결과가 갈리면 결정론이 아니다."""
    first = fixture_runner.run_normalization_fixture()
    second = fixture_runner.run_normalization_fixture()
    assert [result.actual for result in first.results] == [
        result.actual for result in second.results
    ]


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
    """§10.1 — 위반 유형별 합성 출력이 다 있는가 (질문 2개·누출·추론·확장·미반영·정상)."""
    cases = fixture_runner.load_cases(fixture_runner.INTEGRITY_FIXTURE)
    rules = {rule for case in cases for rule in case["expect"].get("rules", [])}
    assert rules == {"R-1", "R-2", "R-3", "R-4"}
    checker_types = {
        violation
        for case in cases
        for violation in case["expect"].get("checker_types", [])
    }
    assert checker_types == {"unsupported_inference", "expansion", "correction_ignored"}
    # 정상 케이스가 없으면 "전부 위반"으로도 100%가 나온다.
    assert any(not case["expect"].get("rules") for case in cases)


async def test_report_renders(session: AsyncSession) -> None:
    """QA 기록(부록 D)에 붙일 보고서가 실제로 만들어지는지."""
    normalization_report = fixture_runner.run_normalization_fixture()
    integrity_report = await fixture_runner.run_integrity_fixture(session)
    document = fixture_runner.render_markdown(
        [
            (normalization_report, fixture_runner.NORMALIZATION_THRESHOLDS),
            (integrity_report, fixture_runner.INTEGRITY_THRESHOLDS),
        ]
    )
    assert "normalization" in document and "integrity" in document
    assert "게이트: 통과" in document
