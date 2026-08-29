"""실값 배포 반입 (PH-04 · 구현명세서 §2.4 `DOSSIER_DIR`·`ASSIGNMENT_PATH` · §2.9).

dossier 24건과 배정표 1건은 **커밋 대상이 아니다**(§2.9). 배포에는 볼륨으로 들어오고,
그 자리를 가리키는 것이 §2.4의 환경변수 둘이다. 이 파일이 거는 것은 **반입이 어긋났을 때
조용히 넘어가지 않는가**다 — 이 계열의 사고는 전부 "틀렸는데 떠 있는" 모양으로 온다.

세 가지를 본다.

1. **볼륨은 오버레이다.** 볼륨에 실값 몇 건만 있어도 나머지는 이미지의 P00·더미로 내려간다.
   24명이 한 명씩 lock되므로(§5.3) 부분 착지가 정상 상태이고, 그때도 기동·시연이 돌아야 한다.
2. **오설정은 기동을 끊는다.** 경로 오타가 "dossier 0건" 또는 "더미 배정표"로 조용히
   수렴하면 그건 빈 연구가 뜬 것이다.
3. **출처를 말할 수 있다.** `asset_sources()`가 지금 읽고 있는 파일을 그대로 보고한다.
"""

from __future__ import annotations

import json

import pytest

from app.assets import dossier_loader, files
from app.assets.files import AssetLocationError, DossierNotFound, dossier_path
from app.core import assignment, freeze


def _real_dossier(target_dir, participant_no: str) -> None:
    """리포의 P00(유효한 실값)을 번호만 바꿔 볼륨 자리에 놓는다."""
    source, _ = dossier_path("P00")
    document = json.loads(source.read_text(encoding="utf-8"))
    document["participant_no"] = participant_no
    document["version"] = f"{participant_no.lower()}_v1"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{participant_no}.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _still_dummy(volume=None) -> str:
    """아직 실값이 착지하지 않은 번호. **고정 번호를 박지 않는다** — PH-03은 한 명씩
    lock되므로(§5.3), 박아 둔 번호에 실값이 도착하는 날 이 파일이 깨진다. 실값은
    커밋되지 않으니(§2.9) CI는 멀쩡하고 자산을 만드는 연구팀 로컬만 깨진다 — 그쪽이
    이 테스트를 가장 필요로 하는 자리다."""
    for participant_no in files.DUMMY_PARTICIPANT_NUMBERS:
        if (files.REPO_DOSSIER_DIR / f"{participant_no}.json").is_file():
            continue
        if volume is not None and (volume / f"{participant_no}.json").is_file():
            continue
        return participant_no
    pytest.skip("실값 24건이 전부 착지했다 — 더미로 내려가는 번호가 없다")


@pytest.fixture
def volume(tmp_path, monkeypatch):
    """`DOSSIER_DIR`가 걸린 빈 볼륨. 캐시는 앞뒤로 비운다."""
    target = tmp_path / "volume-dossiers"
    target.mkdir()
    monkeypatch.setenv("DOSSIER_DIR", str(target))
    dossier_loader.reset_cache()
    yield target
    monkeypatch.delenv("DOSSIER_DIR", raising=False)
    dossier_loader.reset_cache()


# --------------------------------------------------------------------------- #
# 1. 볼륨은 오버레이다
# --------------------------------------------------------------------------- #


def test_partial_landing_falls_back_to_image_dummies(volume) -> None:
    """§5.3 — 24명이 한 명씩 lock된다. 실값 1건만 반입된 상태도 정상 상태다."""
    _real_dossier(volume, "P05")

    path, is_dummy = dossier_path("P05")
    assert path.parent == volume and is_dummy is False, "반입한 실값이 이겨야 한다"

    not_landed = _still_dummy(volume)
    path, is_dummy = dossier_path(not_landed)
    assert is_dummy is True, "반입 전 참가자는 이미지의 스키마 더미로 내려간다"
    assert path.parent == files.REPO_DOSSIER_DIR / "schema_dummy"


def test_qa_dossier_survives_the_volume_override(volume) -> None:
    """P00은 이미지에 커밋돼 있다(§5.5). 볼륨을 걸었다고 QA 워크스루(§10.2)가 죽으면 안 된다."""
    path, is_dummy = dossier_path("P00")
    assert is_dummy is False
    assert path == files.REPO_DOSSIER_DIR / "P00.json"


def test_volume_may_carry_its_own_dummies(volume) -> None:
    """오버라이드 여지는 남긴다 — 볼륨이 자기 더미를 가지면 그쪽이 이긴다."""
    dummy_dir = volume / "schema_dummy"
    _real_dossier(dummy_dir, "P01")
    assert files.schema_dummy_dir() == dummy_dir
    path, is_dummy = dossier_path("P01")
    assert path.parent == dummy_dir and is_dummy is True


def test_every_assigned_participant_resolves_under_a_volume(volume) -> None:
    """부분 착지 상태에서도 기동 게이트(§5.4)가 통과해야 한다 — 전수 로드가 성립한다."""
    landed = _still_dummy(volume)
    _real_dossier(volume, landed)
    dossiers = dossier_loader.load_all()
    assert len(dossiers) >= 25, "P00 + 배정표 24명이 전부 잡혀야 한다"
    assert dossiers[landed].is_dummy is False
    # 볼륨에 놓지 않은 번호는 더미로 내려간다. **번호를 박지 않는다** — `_still_dummy`가
    # 있는 이유와 같다(§2.9 실값 미커밋 + PH-03 한 명씩 lock). P04에 실값이 착지한 날
    # 이 줄이 깨졌다.
    assert dossiers[_still_dummy(volume)].is_dummy is True


# --------------------------------------------------------------------------- #
# 2. 오설정은 기동을 끊는다
# --------------------------------------------------------------------------- #


def test_missing_dossier_dir_is_not_swallowed(tmp_path, monkeypatch) -> None:
    """마운트 경로 오타 — `DossierNotFound` 계보였다면 참가자 루프가 삼켜서 **0건으로 기동
    성공**했을 자리다. 별도 예외로 끊는다."""
    monkeypatch.setenv("DOSSIER_DIR", str(tmp_path / "없는-경로"))
    dossier_loader.reset_cache()
    try:
        with pytest.raises(AssetLocationError, match="DOSSIER_DIR"):
            files.dossier_dir()
        with pytest.raises(AssetLocationError):
            files.available_participant_numbers()
        assert not issubclass(AssetLocationError, DossierNotFound), (
            "삼켜지는 예외 계보에 들어가면 이 검사의 의미가 사라진다"
        )
    finally:
        monkeypatch.delenv("DOSSIER_DIR", raising=False)
        dossier_loader.reset_cache()


def test_missing_assignment_path_never_falls_back_to_dummy(tmp_path, monkeypatch) -> None:
    """§5.2 — 경로를 명시했으면 그 파일이어야 한다. dummy로 내려가면 **더미 배정표를 실은 채**
    기동이 성공한다(NT-42가 뒤늦게 잡는다)."""
    monkeypatch.setenv("ASSIGNMENT_PATH", str(tmp_path / "assignment_v1.json"))
    assignment.reset_cache()
    try:
        with pytest.raises(assignment.AssignmentContractError, match="ASSIGNMENT_PATH"):
            assignment.assignment_path()
    finally:
        monkeypatch.delenv("ASSIGNMENT_PATH", raising=False)
        assignment.reset_cache()


def test_assignment_path_override_is_used_when_present(tmp_path, monkeypatch) -> None:
    """정상 반입 — 오버라이드가 실값으로 잡히고 `is_dummy`가 내려간다."""
    source, _ = assignment.assignment_path()
    target = tmp_path / "assignment_v1.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("ASSIGNMENT_PATH", str(target))
    assignment.reset_cache()
    try:
        path, is_dummy = assignment.assignment_path()
        assert path == target and is_dummy is False
        assert assignment.load().is_dummy is False
    finally:
        monkeypatch.delenv("ASSIGNMENT_PATH", raising=False)
        assignment.reset_cache()


# --------------------------------------------------------------------------- #
# 3. 출처를 말할 수 있다
# --------------------------------------------------------------------------- #


def test_asset_sources_reports_where_each_file_came_from(volume) -> None:
    """PH-04 — 반입 직후의 첫 확인. 게이트가 PH-03을 보고할 때 "볼륨이 안 붙었다"와
    "아직 lock 전이다"를 구분할 수 있어야 손을 댄다."""
    _real_dossier(volume, "P07")
    not_landed = _still_dummy(volume)  # 볼륨에 놓은 P07을 고르지 않도록 반입 뒤에 고른다
    sources = freeze.asset_sources()

    assert sources["dossier_dir"] == str(volume)
    assert sources["dossier_dir_overridden"] is True
    assert "P07" in sources["dossiers"]["real"]
    assert not_landed in sources["dossiers"]["dummy"]
    assert sources["focal_items"]["is_placeholder"] is False


def test_asset_sources_reports_repo_paths_without_override() -> None:
    dossier_loader.reset_cache()
    sources = freeze.asset_sources()
    assert sources["dossier_dir_overridden"] is False
    assert sources["dossier_dir"] == str(files.REPO_DOSSIER_DIR)
