"""NT-03 — normalization 엔진 입력 한정 (구현명세서 §6.4 · 부록 A.3 · §1.2).

    NT-03 normalization 엔진 입력이 {user1, referent_map, patterns}로 한정

케이스 판정 자체는 fixture(§10.1 · NT-24)가 전수로 본다. 여기서는 **경계와 자산 계약**을 본다 —
엔진이 그 셋 말고 무엇을 받을 수 있는가, 패턴 자산이 계약을 지키는가.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from app.assets.dossier_loader import ReferentEntry
from app.llm import normalization

BACKEND = Path(__file__).resolve().parents[2] / "backend"
MODULE_PATH = BACKEND / "app" / "llm" / "normalization.py"

REFERENT = ReferentEntry(
    patterns=("그렇게 해줘", "응 그렇게 해줘"), proposition="두 선택지의 장단점을 더 정리해줘"
)


def test_nt03_signature_is_limited_to_user1_and_referent_map() -> None:
    """세 번째 입력(patterns)은 자산이므로 모듈이 스스로 로드한다 — 인자는 둘뿐이다."""
    parameters = list(inspect.signature(normalization.normalize).parameters)
    assert parameters == ["user1", "referent_map"]


def test_nt03_module_cannot_reach_forbidden_sources() -> None:
    """§1.2 — dossier_private·DB 모델·sidecar·평정에 닿는 import가 없어야 한다."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for forbidden in ("dossier_private", "models", "tables", "api", "sidecar"):
        assert not any(forbidden in name for name in imported), f"금지 import: {forbidden}"


def test_nt03_condition_is_not_an_input() -> None:
    """§6.4 — 전 조건 동일 규칙(NT-11). 조건을 받을 자리가 없어야 그 성질이 구조로 보장된다.

    주석·docstring은 규칙을 **설명**하므로 제외하고, 실제 식별자와 문자열 상수만 본다.
    """
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            identifiers.add(node.value)
    for banned in ("condition", "branch_index", "sequence_index", "C1", "C2", "C3", "C4"):
        assert banned not in identifiers, f"조건 의존 흔적: {banned}"


def test_patterns_asset_matches_prompt_config_version() -> None:
    """§6.7 — 패턴 목록 버전은 prompt_config가 기록한 값과 같아야 한다."""
    from app.llm import prompts

    normalization.reset_cache()
    patterns = normalization.load_patterns()
    assert [pattern.id for pattern in patterns] == ["NP-01", "NP-02", "NP-03"]
    document = json.loads(normalization.PATTERNS_PATH.read_text(encoding="utf-8"))
    assert document["version"] == prompts.config()["normalization_patterns_version"]


def test_version_mismatch_fails_loudly(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "patterns.json"
    broken.write_text(
        json.dumps({"version": "other_v9", "patterns": []}, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(normalization, "PATTERNS_PATH", broken)
    normalization.reset_cache()
    try:
        with pytest.raises(normalization.PatternAssetError):
            normalization.load_patterns()
    finally:
        normalization.reset_cache()


def test_np04_is_not_a_pattern(tmp_path, monkeypatch) -> None:
    """부록 A.3 — NP-04는 '치환하지 않음'의 결과 코드다. 패턴으로 등록되면 자산 오류다."""
    from app.llm import prompts

    broken = tmp_path / "patterns.json"
    broken.write_text(
        json.dumps(
            {
                "version": prompts.config()["normalization_patterns_version"],
                "patterns": [{"id": "NP-04", "regex": ".*", "mode": "single"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(normalization, "PATTERNS_PATH", broken)
    normalization.reset_cache()
    try:
        with pytest.raises(normalization.PatternAssetError, match="NP-04"):
            normalization.load_patterns()
    finally:
        normalization.reset_cache()


def test_substitution_keeps_the_original_alongside() -> None:
    """부록 A.3 치환 결과 형식 — 원문 병기로 정보 추가 없이 지시만 복원한다."""
    result = normalization.normalize("응 그렇게 해줘", [REFERENT])
    assert result.applied
    assert result.text == '사용자 메시지(정규화): "두 선택지의 장단점을 더 정리해줘" (원문: "응 그렇게 해줘")'
    assert "원문" in result.text


def test_no_substitution_keeps_the_raw_text_untouched() -> None:
    """§6.4 — 다의·무매칭이면 ambiguity를 유지한다. 임의 보완 금지."""
    result = normalization.normalize("고마워 도움이 됐어", [REFERENT])
    assert not result.applied
    assert result.text == "고마워 도움이 됐어"
    assert result.matched_pattern_id == normalization.NO_SUBSTITUTION_ID
    assert result.referent_id is None


def test_substitution_adds_no_new_meaning() -> None:
    """치환문의 어휘는 원문 + referent proposition 밖으로 나가지 않는다."""
    result = normalization.normalize("응 그렇게 해줘", [REFERENT])
    assert result.substituted is not None
    allowed = set("응 그렇게 해줘".split()) | set(REFERENT.proposition.split())
    assert set(result.substituted.split()) <= allowed


def test_empty_user1_is_not_substituted() -> None:
    assert not normalization.normalize("   ", [REFERENT]).applied


def test_referent_ids_are_stable_and_ordered() -> None:
    """§8.1 `normalizations.referent_id` — 자산 순서에서 파생한다."""
    referents = normalization.referents_from([REFERENT, REFERENT])
    assert [referent.id for referent in referents] == ["R-01", "R-02"]
