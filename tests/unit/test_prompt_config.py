"""prompt_config 자산 계약 (§6.7 · 부록 A.1·A.2).

`prompt_config_v1.json`이 정본이라는 규율은 hash가 지킨다 — 문안을 고치고 hash를 안 고치면
기동 게이트(`app.main.validate_assets`)가 잡는다. 여기서는 그 게이트가 실제로 물리는지와,
프롬프트에 **조건 라벨이 새지 않는지**를 본다(§6.2 — AI2 프롬프트는 전 조건 동일).
"""

from __future__ import annotations

import pytest

from app.llm import prompts


def test_prompt_hash_matches_content() -> None:
    prompts.verify()


def test_hash_change_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    document = dict(prompts.config())
    document["prompt_hash"] = "0" * 64
    monkeypatch.setattr(prompts, "config", lambda: document)
    with pytest.raises(ValueError, match="prompt_hash 불일치"):
        prompts.verify()


def test_parameters_follow_the_frozen_table() -> None:
    """§0.5 — AI2 temperature 0.4 / checker 0.0, checker만 JSON 강제(§2.2.3)."""
    ai2 = prompts.parameters(prompts.AI2_PROMPT_KEY)
    checker = prompts.parameters(prompts.CHECKER_PROMPT_KEY)
    assert ai2["temperature"] == 0.4
    assert ai2["max_tokens"] == 800
    assert ai2["expect_json"] is False
    assert checker["temperature"] == 0.0
    assert checker["expect_json"] is True


def test_ai2_prompt_carries_no_condition_label() -> None:
    """§6.2 — AI2 정책 프롬프트는 전 조건·전 참가자 동일하다. 조건 라벨이 들어갈 자리가 없다."""
    system = prompts.system_template(prompts.AI2_PROMPT_KEY)
    for label in ("C1", "C2", "C3", "C4", "uptake", "elicitation", "condition"):
        assert label not in system, f"AI2 프롬프트에 조건 라벨이 있다: {label}"


def test_ai2_prompt_has_only_the_three_allowed_slots() -> None:
    """§6.2 입력 계약(D-34) — effective checkpoint · **focal AI1** · User1 **원문**.

    v1.0.1과 두 곳이 다르다: `{focal_ai1}`이 생겼고(AI1 원문을 주는 것이 v2 정책),
    `{user1_normalized}`가 `{user1}`로 바뀌었다(normalization 폐기).
    """
    system = prompts.system_template(prompts.AI2_PROMPT_KEY)
    assert "{ai_visible_context}" in system
    assert "{focal_ai1}" in system
    assert "{user1}" in system
    assert "{user1_normalized}" not in system, "normalization은 v2에 없다 (D-34)"
    for forbidden in (
        "{sidecar",
        "{researcher",
        "{ratings",
        "{alt",
        "{condition",
        "{assignment",
        "{pairwise",
        "{user2",
    ):
        assert forbidden not in system


def test_checker_prompt_asks_for_the_three_violation_types() -> None:
    """부록 A.2 — 규칙 계층이 맡는 항목(질문 수·길이·문자열 누출)은 checker에 중복 위임하지 않는다."""
    system = prompts.system_template(prompts.CHECKER_PROMPT_KEY)
    for violation_type in ("unsupported_inference", "expansion", "correction_ignored"):
        assert violation_type in system
    assert "{prohibited_inference}" in system


def test_prompt_role_mapping_is_dual_provider() -> None:
    """§2.2.1 D-18 이원화 — 생성은 MAIN, 검증은 VALIDATOR."""
    assert prompts.PROMPT_KEY_ROLE[prompts.AI2_PROMPT_KEY] == "main"
    assert prompts.PROMPT_KEY_ROLE[prompts.CHECKER_PROMPT_KEY] == "validator"
