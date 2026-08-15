"""dossier 층 분리의 런타임 검증 (§1.2 · §5.2).

NT-04가 "LLM 경로가 researcher_only 로더를 import할 수 없다"를 정적으로 막는다면, 여기서는
**로더가 실제로 무엇을 돌려주는가**를 막는다. 두 검사가 함께 있어야 "import는 안 했는데
ai_visible dict에 회고 문자열이 섞여 있었다" 같은 경로가 남지 않는다.
"""

from __future__ import annotations

import json

import pytest

from app.assets import dossier_loader, dossier_private
from app.assets.files import PARTICIPANT_NUMBERS, dossier_path

ALL_PARTICIPANTS = list(PARTICIPANT_NUMBERS)


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _walk_strings(item)]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _walk_strings(item)]
    if hasattr(value, "__dataclass_fields__"):
        return [
            s
            for field in value.__dataclass_fields__  # type: ignore[attr-defined]
            for s in _walk_strings(getattr(value, field))
        ]
    return []


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_loader_output_carries_no_researcher_only_string(participant_no: str) -> None:
    """로더가 돌려준 어떤 문자열도 researcher_only 층의 값이 아니다."""
    dossier = dossier_loader.load(participant_no)
    path, _ = dossier_path(participant_no)
    private_values = {
        value.strip()
        for value in json.loads(path.read_text(encoding="utf-8"))["researcher_only"].values()
        if isinstance(value, str) and value.strip()
    }

    loaded_strings = _walk_strings(dossier.sampling) + _walk_strings(dossier.ai_visible)
    loaded_strings += _walk_strings(
        {
            "warranted_uptake": dossier.derivation.warranted_uptake,
            "prohibited_inference": list(dossier.derivation.prohibited_inference),
            "residual_uncertainty": [
                dossier.derivation.residual_uncertainty.text,
                dossier.derivation.residual_uncertainty.question_stem,
            ],
            "focal": dossier.derivation.focal_repair_relevant_content,
            "stimuli": dict(dossier.derivation.stimuli),
            "fallback": dossier.derivation.neutral_fallback,
            "referents": [
                [*entry.patterns, entry.proposition] for entry in dossier.derivation.referent_map
            ],
        }
    )

    for private_value in private_values:
        assert not any(private_value in loaded for loaded in loaded_strings), (
            f"{participant_no}: researcher_only 값이 로더 출력에 섞였다 (§1.2)"
        )


def test_loader_has_no_researcher_only_attribute() -> None:
    """`Dossier` 값 객체에 researcher_only 슬롯 자체가 없다 — 실수로 채울 자리가 없다."""
    dossier = dossier_loader.load("P00")
    assert not hasattr(dossier, "researcher_only")
    assert "researcher_only" not in dossier.ai_visible.as_dict()


@pytest.mark.parametrize("participant_no", ALL_PARTICIPANTS)
def test_private_loader_returns_only_the_researcher_layer(participant_no: str) -> None:
    """콘솔 전용 로더는 researcher_only만 준다 — 세 층을 함께 주는 함수는 두지 않는다."""
    layer = dossier_private.load_researcher_only(participant_no)
    assert set(layer) == set(dossier_private.RESEARCHER_ONLY_FIELDS)
    assert "ai_visible" not in layer
    assert "derivation" not in layer


def test_p00_private_layer_has_qa_synthetic_values() -> None:
    """P00은 QA 전용 합성 dossier다(§10.2) — 콘솔 R3·R4 리허설이 빈 화면을 보지 않게 한다."""
    layer = dossier_private.load_researcher_only("P00")
    assert all(value.strip() for value in layer.values())


def test_unknown_participant_is_rejected() -> None:
    with pytest.raises(KeyError):
        dossier_loader.load("P99")
