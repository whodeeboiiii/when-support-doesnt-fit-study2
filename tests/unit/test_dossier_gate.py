"""§5.4 기동 게이트 — 자산이 계약을 어기면 서버가 뜨지 않는다.

NT-20의 나머지 절반이다. "정상 자산이 통과한다"는 `tests/assets/`가 보고, 여기서는 **깨진
자산이 실제로 기동을 끊는가**를 본다. 게이트가 조용히 통과하면 계약 테스트는 장식이 된다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import main
from app.assets import dossier_loader, files
from app.assets.files import dossier_path


#: 리포의 실제 P00을 **패치 전에** 읽어 둔다 — 검사용 원본이자 "정상 자산"의 기준값이다.
_REAL_P00_PATH, _ = dossier_path("P00")
_REAL_P00_TEXT = _REAL_P00_PATH.read_text(encoding="utf-8")


@pytest.fixture
def fake_dossier_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """dossier 디렉터리를 임시 폴더로 갈아끼운다 — 리포 자산은 건드리지 않는다."""
    monkeypatch.setattr(files, "DOSSIER_DIR", tmp_path)
    monkeypatch.setattr(files, "SCHEMA_DUMMY_DIR", tmp_path / "schema_dummy")
    (tmp_path / "schema_dummy").mkdir()
    dossier_loader.reset_cache()
    yield tmp_path
    dossier_loader.reset_cache()


def _p00_document() -> dict[str, Any]:
    return json.loads(_REAL_P00_TEXT)


def _write(directory: Path, document: dict[str, Any], participant_no: str = "P00") -> None:
    (directory / f"{participant_no}.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )


def test_valid_document_passes(fake_dossier_dir: Path) -> None:
    _write(fake_dossier_dir, _p00_document())
    assert dossier_loader.load("P00").participant_no == "P00"


def test_missing_required_key_fails(fake_dossier_dir: Path) -> None:
    document = _p00_document()
    del document["derivation"]["neutral_fallback"]
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError, match="neutral_fallback"):
        dossier_loader.load("P00")


def test_extra_key_in_ai_visible_fails(fake_dossier_dir: Path) -> None:
    """§1.2 — ai_visible에 스키마 밖 필드가 생기면 회고 자료가 AI-visible로 승격될 수 있다."""
    document = _p00_document()
    document["ai_visible"]["retrospective_note"] = "회고 메모"
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError, match="스키마에 없는 키"):
        dossier_loader.load("P00")


def test_question_in_c1_fails(fake_dossier_dir: Path) -> None:
    """§5.4가 예로 든 그대로 — C1에 질문이 있으면 기동 실패다."""
    document = _p00_document()
    stem = document["derivation"]["residual_uncertainty"]["question_stem"]
    document["derivation"]["stimuli"]["C1"] += f" {stem}"
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError, match="질문 수"):
        dossier_loader.load("P00")


def test_missing_question_in_c4_fails(fake_dossier_dir: Path) -> None:
    document = _p00_document()
    stem = document["derivation"]["residual_uncertainty"]["question_stem"]
    document["derivation"]["stimuli"]["C4"] = document["derivation"]["stimuli"]["C4"].replace(
        stem, ""
    )
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError, match="C4"):
        dossier_loader.load("P00")


def test_stale_stimuli_meta_fails(fake_dossier_dir: Path) -> None:
    document = _p00_document()
    document["derivation"]["stimuli_meta"]["C1"]["chars"] += 1
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError, match="원문 계량과 불일치"):
        dossier_loader.load("P00")


def test_unknown_cue_form_fails(fake_dossier_dir: Path) -> None:
    document = _p00_document()
    document["ai_visible"]["trouble_cue"]["form"] = "annoyed"
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError, match="trouble_cue.form"):
        dossier_loader.load("P00")


def test_missing_file_is_reported(fake_dossier_dir: Path) -> None:
    with pytest.raises(files.DossierNotFound):
        dossier_loader.load("P07")


def test_schema_dummy_is_used_when_real_value_is_absent(fake_dossier_dir: Path) -> None:
    """§2.9 — 실값이 없으면 더미로 내려가되 `is_dummy`로 드러난다(§11.1 더미 자산 원칙)."""
    document = _p00_document()
    document["participant_no"] = "P05"
    _write(fake_dossier_dir / "schema_dummy", document, "P05")
    dossier = dossier_loader.load("P05")
    assert dossier.is_dummy is True
    assert dossier.is_locked is False


def test_startup_gate_refuses_to_boot_on_broken_asset(fake_dossier_dir: Path) -> None:
    document = _p00_document()
    document["derivation"]["stimuli"]["C2"] = "질문이 없는 자극이다."
    _write(fake_dossier_dir, document)
    with pytest.raises(dossier_loader.DossierContractError):
        main.validate_assets()
