"""NT-04 — `llm/` 모듈이 `dossier_private`를 import하면 정적 검사 실패 (§1.2 구현 규율).

evidence boundary(§1.2)의 마지막 방어선은 런타임 검사가 아니라 **모듈 경계**다.

    researcher_only는 서버에서 별도 모듈(`dossier_private.py`)로만 로드하고,
    LLM payload 조립기(`llm/context.py`)는 해당 모듈을 import할 수 없다(정적 검사 NT-04).

런타임 allowlist(§6.2)는 "이번 호출에 무엇이 들어갔는가"를 막고, 이 검사는 "그 값이 애초에
LLM 경로에 **도달할 수 있는가**"를 막는다. 후자가 없으면 새 코드 한 줄이 조용히 경로를 연다.

검사는 두 겹이다.
1. `backend/app/llm/**` 의 모든 모듈이 `app.assets.dossier_private`를 직접 import하지 않는다.
2. 그 모듈들이 **전이적으로도** 닿지 않는다 — 중간 모듈을 하나 끼우면 통과하는 검사는
   검사가 아니다.
추가로 `importlib.import_module("…dossier_private")` 같은 우회도 AST 수준에서 잡는다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2] / "backend"
APP_ROOT = BACKEND / "app"
LLM_ROOT = APP_ROOT / "llm"

FORBIDDEN_MODULE = "app.assets.dossier_private"
FORBIDDEN_TOKEN = "dossier_private"

#: 같은 규율을 받는 두 번째 자산 — 사전설문(D-44). §1.2는 사전설문 응답을 어떤 LLM 호출에도
#: 넣지 않는다(v1.0.1 NT-01). 런타임 검사(`tests/integration/test_evidence_boundary.py`)는
#: "이번 호출에 안 들어갔다"를 보고, 여기는 **닿을 수 있는 경로 자체**를 막는다.
PRESURVEY_TOKEN = "assets.presurvey"


def module_name(path: Path) -> str:
    relative = path.relative_to(BACKEND).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(name: str | None, level: int, current: str) -> str:
    """`from . import x` / `from ..y import z`를 절대 모듈명으로 편다."""
    if level == 0:
        return name or ""
    base = current.split(".")
    # 패키지 기준: `app.llm.gateway.calls`에서 level=1이면 `app.llm.gateway`
    anchor = base[: len(base) - level] if len(base) >= level else []
    tail = [name] if name else []
    return ".".join([*anchor, *tail])


def imported_modules(source: str, current_module: str) -> set[str]:
    """모듈이 import하는 이름 집합 (import·from-import·importlib 문자열 인자 포함)."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(node.module, node.level, current_module)
            if base:
                found.add(base)
            found.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            # importlib.import_module("app.assets.dossier_private") 류 우회
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name in {"import_module", "__import__"}:
                found.update(
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                )
    return found


def python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def app_import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in python_files(APP_ROOT):
        name = module_name(path)
        graph[name] = {
            imported
            for imported in imported_modules(path.read_text(encoding="utf-8"), name)
            if imported.startswith("app")
        }
    return graph


LLM_MODULES = [module_name(path) for path in python_files(LLM_ROOT)]


def test_llm_package_is_not_empty() -> None:
    """검사 대상이 사라지면 이 테스트는 조용히 통과한다 — 그러지 않도록 존재를 먼저 고정한다."""
    assert LLM_MODULES, "backend/app/llm 아래 모듈이 없다"


@pytest.mark.parametrize("path", python_files(LLM_ROOT), ids=lambda p: p.name)
def test_nt04_llm_modules_do_not_import_dossier_private(path: Path) -> None:
    imports = imported_modules(path.read_text(encoding="utf-8"), module_name(path))
    offenders = sorted(name for name in imports if FORBIDDEN_TOKEN in name)
    assert offenders == [], (
        f"{path.relative_to(BACKEND)}: LLM 경로가 researcher_only 로더를 import했다 — {offenders} "
        "(§1.2 evidence boundary · NT-04)"
    )


@pytest.mark.parametrize("path", python_files(LLM_ROOT), ids=lambda p: p.name)
def test_llm_modules_do_not_import_the_presurvey_asset(path: Path) -> None:
    """§1.2 · D-44 — 사전설문 로더는 LLM 경로에서 import되지 않는다."""
    imports = imported_modules(path.read_text(encoding="utf-8"), module_name(path))
    offenders = sorted(name for name in imports if PRESURVEY_TOKEN in name)
    assert offenders == [], (
        f"{path.relative_to(BACKEND)}: LLM 경로가 사전설문 자산을 import했다 — {offenders} "
        "(§1.2 evidence boundary)"
    )


def test_llm_modules_do_not_reach_the_presurvey_asset_transitively() -> None:
    """중간 모듈을 하나 끼우면 통과하는 검사는 검사가 아니다 — NT-04와 같은 폭으로 본다."""
    graph = app_import_graph()
    seen: set[str] = set()
    stack = list(LLM_MODULES)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for target in graph.get(current, set()):
            assert PRESURVEY_TOKEN not in target, (
                f"LLM 경로가 전이적으로 사전설문 자산에 닿는다: {current} → {target}"
            )
            if target in graph and target not in seen:
                stack.append(target)


def test_nt04_llm_modules_do_not_reach_dossier_private_transitively() -> None:
    graph = app_import_graph()
    seen: set[str] = set()
    stack = list(LLM_MODULES)
    trail: dict[str, str] = {}
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for target in graph.get(current, set()):
            if FORBIDDEN_TOKEN in target:
                chain = [target]
                node = current
                while node in trail:
                    chain.append(node)
                    node = trail[node]
                chain.append(node)
                pytest.fail(
                    "LLM 경로가 전이적으로 researcher_only 로더에 닿는다: "
                    + " → ".join(reversed(chain))
                )
            if target in graph and target not in seen:
                trail[target] = current
                stack.append(target)


def test_nt04_detector_catches_a_planted_violation() -> None:
    """검사기 자체의 정직성 — 위반을 심으면 반드시 잡혀야 한다(위양성 통과 방지)."""
    planted = "from app.assets.dossier_private import load_researcher_only\n"
    assert FORBIDDEN_MODULE in imported_modules(planted, "app.llm.context")

    planted_dynamic = "import importlib\nm = importlib.import_module('app.assets.dossier_private')\n"
    assert FORBIDDEN_MODULE in imported_modules(planted_dynamic, "app.llm.context")


def test_dossier_private_is_importable_on_its_own() -> None:
    """경계는 'LLM 경로에서 금지'이지 '존재 금지'가 아니다 — 콘솔(R3·R4)은 이 모듈을 쓴다."""
    from app.assets.dossier_private import load_researcher_only

    assert callable(load_researcher_only)
