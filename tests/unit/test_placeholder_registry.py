"""PLACEHOLDER 레지스트리 대조 (`PLACEHOLDERS.md` · 구현명세서 부록 E.4).

구 리포(`../study2_pipeline`)의 `tests/unit/test_placeholder_registry.py`를 이식했다. 규칙은 같다:

    "이 표에 없는 placeholder가 코드에 남아 있으면 미완으로 간주한다."

문서가 코드보다 늦게 늙는 것을 막는 장치다. 코드·자산에 `PH-01`·`PH-IRB-1` 같은 태그를 새로
심으면 `PLACEHOLDERS.md`에 행이 없어서 여기서 걸린다 — 미확정 항목이 주석에만 남고 레지스트리에는
없는 상태를 만들 수 없다.

반대 방향(표에는 있는데 코드에 없는 행)은 **검사하지 않는다**. IRB 문안처럼 코드에 닿지 않는
항목이 정상적으로 존재하기 때문이다(PH-IRB-3~7 — 연구자 문서·IRB 서류).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "PLACEHOLDERS.md"

#: 코드·자산에 심는 태그 형식 — `PH-03` · `PH-IRB-1`.
PH_REFERENCE = re.compile(r"PH-(?:IRB-)?\d{1,2}")
#: 레지스트리 표의 행 머리 — `| PH-03 | 자산 | …`
PH_ROW = re.compile(r"^\|\s*(PH-(?:IRB-)?\d{1,2})\s*\|", re.MULTILINE)

_SCANNED = (
    REPO_ROOT / "backend" / "app",
    REPO_ROOT / "frontend" / "src",
    REPO_ROOT / "fixtures",
    REPO_ROOT / "dossiers",
    REPO_ROOT / "analysis",
    REPO_ROOT / "scripts",
)
_SUFFIXES = {".py", ".json", ".ts", ".tsx"}


def _registered() -> set[str]:
    return set(PH_ROW.findall(REGISTRY.read_text(encoding="utf-8")))


def _referenced() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for root in _SCANNED:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in _SUFFIXES:
                continue
            for tag in PH_REFERENCE.findall(path.read_text(encoding="utf-8")):
                found.setdefault(tag, set()).add(str(path.relative_to(REPO_ROOT)))
    return found


def test_every_placeholder_in_code_is_registered() -> None:
    registered = _registered()
    unregistered = {
        tag: sorted(paths) for tag, paths in _referenced().items() if tag not in registered
    }
    assert unregistered == {}, f"PLACEHOLDERS.md에 없는 placeholder: {unregistered}"


def test_registry_records_a_code_location_for_referenced_placeholders() -> None:
    """코드에서 쓰이는 행은 '코드 위치' 열이 비어 있으면 안 된다.

    위치가 없으면 착지할 때 어디를 고쳐야 하는지 문서가 답하지 못한다.
    """
    referenced = set(_referenced())
    missing: list[str] = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        match = PH_ROW.match(line)
        if match is None or match.group(1) not in referenced:
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        # | ID | 유형 | 무엇이 비어 있나 | 코드 위치 | 구 리포 | 해소 주체 | 상태 |
        if len(columns) < 4 or not columns[3]:
            missing.append(match.group(1))
    assert missing == [], f"'코드 위치'가 빈 행: {missing}"


def test_registry_covers_the_spec_todo_index() -> None:
    """부록 E.4의 `<TODO>` 태그 중 **코드에 닿는 것**이 전부 등록돼 있는지.

    명세서가 정본이므로 색인이 늘면 이 테스트가 먼저 깨진다(반대 순서 금지 — 레지스트리 §11).
    """
    spec = (REPO_ROOT / "docs" / "구현명세서_v1.0.1.md").read_text(encoding="utf-8")
    index_section = spec.split("## E.4")[1].split("## E.5")[0]
    spec_tags = {tag for tag in PH_REFERENCE.findall(index_section)}
    # PH-P-n(논문 역반영)은 형식이 다르므로 위 정규식에 잡히지 않는다 — 레지스트리 §9가 담당한다.
    assert spec_tags <= _registered(), f"레지스트리 누락: {sorted(spec_tags - _registered())}"
