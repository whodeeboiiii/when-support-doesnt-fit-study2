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


def test_checker_v3_fixes_the_referent_and_the_assertion_form() -> None:
    """부록 A.2 v3 (D-43) — 오탐의 세 원인을 프롬프트가 문자로 막는다.

    ① 판정 대상을 초안으로 한정하고 AI1 오귀속을 금지한다 — P23에서 checker가 **AI1의
       `u` segment 원문**을 AI2 초안의 위반으로 잡았다. D-40으로 AI1에 무대지시가 붙은
       뒤로 AI2가 uptake를 이어받을 유인이 더 커져서 이 조항의 무게가 커졌다.
    ② unsupported_inference의 성립 조건 (a)(b)(c) — 특히 (a) 대상이 사용자 본인.
    ③ [사용자 메시지]가 금지 목록보다 우선한다 — 목록은 checkpoint 시점 기준이고
       초안은 User1 **이후**의 turn이라, 이 규칙이 없으면 correction_ignored와 충돌한다.
    """
    system = prompts.system_template(prompts.CHECKER_PROMPT_KEY)
    assert "판정 대상은 [AI 응답 초안] 하나뿐입니다" in system
    assert "초안의 위반으로" in system and "귀속하지 마세요" in system
    for condition in ("(a)", "(b)", "(c)"):
        assert condition in system, f"성립 조건 {condition}이 없다"
    assert "사용자 본인이다" in system
    assert "사용자 메시지는 아래" in system and "금지 목록보다 우선합니다" in system
    assert "참고 목록입니다" in system, "금지 목록이 여전히 독립 규칙으로 읽힌다"


def test_checker_v31_gives_the_context_precedence_over_the_list() -> None:
    """A.2 v3.1 — 맥락 우선. 실모델 재검에서 남은 오탐 두 갈래를 프롬프트로 막는다.

    ① 맥락에 이미 있는 감정을 잡던 것(P08) → (c)에 "맥락에 있으면 위반이 아니다" 명시.
    ② 금지 목록이 맥락을 이기던 것 → "목록의 항목이 맥락에 있는 내용을 가리키면 적용하지
       않는다". 목록은 대화 **전에** 적은 것이고 초안은 User1 **이후**의 turn이다.
    """
    system = prompts.system_template(prompts.CHECKER_PROMPT_KEY)
    assert "(c)를 만족하지 않으므로" in system
    assert "그 항목은 이 사건에서 적용하지 않습니다" in system
    assert "대화에 실제로 나온 내용을 이기지 못합니다" in system
    # 설계 근거·되짚기 예시가 각각 하나씩은 있어야 한다.
    assert system.count("비위반:") >= 5


def test_checker_prompt_carries_no_text_from_any_incident() -> None:
    """§1.2 — 프롬프트는 **전 조건·전 참가자 동일**이다. 특정 사건의 문구가 들어가면 안 된다.

    대조 예시를 쓸 때 실제 dossier에서 문면을 끌어오기 쉽다. 그건 기능적 위반은 아니지만
    (R-1은 AI2 **출력**만 본다) 전 참가자 공통 lock 프롬프트에 한 참가자의 문구가 박히는
    것이라, 방화벽의 외관을 해친다. 공백을 지운 8자 연속 일치를 본다(§5.4 LEAK_MATCH_CHARS).

    실값 dossier가 없는 CI에서는 대조 대상이 없어 자동 통과한다 — 실값이 있는 곳에서 잡는다.
    """
    import re

    from app.assets import dossier_loader, dossier_private, files

    def squash(text: str) -> str:
        return re.sub(r"\s+", "", text)

    config_text = squash(prompts.PROMPT_CONFIG_PATH.read_text(encoding="utf-8"))
    window = dossier_loader.LEAK_MATCH_CHARS

    for participant_no in files.available_participant_numbers():
        dossier = dossier_loader.load(participant_no)
        if dossier.is_dummy:
            continue
        visible = dossier.ai_visible
        sources = [
            *(str(value) for value in dossier_private.load_researcher_only(participant_no).values()),
            visible.situation_summary,
            visible.original_request,
            visible.problematic_ai_response,
            visible.trouble_cue,
            *visible.prior_evidence,
            dossier.stimulus.r,
            dossier.stimulus.u,
            dossier.stimulus.q,
            dossier.stimulus.neutral_fallback,
        ]
        for source in sources:
            text = squash(str(source))
            for index in range(len(text) - window + 1):
                chunk = text[index : index + window]
                assert chunk not in config_text, (
                    f"{participant_no}의 문구가 프롬프트에 있다: {chunk!r} — "
                    "대조 예시는 중립 도메인에서 만든다"
                )


def test_prompt_role_mapping_is_dual_provider() -> None:
    """§2.2.1 D-18 이원화 — 생성은 MAIN, 검증은 VALIDATOR."""
    assert prompts.PROMPT_KEY_ROLE[prompts.AI2_PROMPT_KEY] == "main"
    assert prompts.PROMPT_KEY_ROLE[prompts.CHECKER_PROMPT_KEY] == "validator"


def test_system_part_carries_the_whole_policy_not_just_the_first_line() -> None:
    """§6.2 — role 분리는 **정책부/자료부** 경계다.

    A.1 v2의 첫 문단이 본문 안에서 "아래 [대화 맥락]은 …"으로 블록 머리말을 언급하기 때문에,
    경계를 단순 `find`로 잡으면 그 언급에서 잘려 원칙 1–5가 통째로 user 메시지로 넘어간다.
    경계는 줄 첫머리에 홀로 선 머리말이어야 한다.
    """
    from app.llm import context

    payload = context._split_at_context(prompts.system_template(prompts.AI2_PROMPT_KEY))
    for principle in ("1.", "2.", "3.", "4.", "5."):
        assert f"\n{principle} " in f"\n{payload.system}", f"원칙 {principle}이 system에 없다"
    assert payload.system.endswith("확장하지 않습니다.")
    assert payload.user.startswith(context.CONTEXT_BLOCK)
    for slot in ("{ai_visible_context}", "{focal_ai1}", "{user1}"):
        assert slot in payload.user and slot not in payload.system
