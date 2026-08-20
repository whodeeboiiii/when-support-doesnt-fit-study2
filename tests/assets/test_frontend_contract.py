"""프런트엔드 계약 — NT-19(데스크톱 가드)·NT-13(번들 비밀·자극 사전 로드) 정적 층.

⚠ **한계**: 이 리포에는 JS 테스트 러너가 없다(테스트는 pytest — CLAUDE.md). 그래서 여기서
보는 것은 **소스와 빌드 산출물의 성질**이지 렌더 동작이 아니다. 렌더 수준의 NT-19는 QA
워크스루(§10.2 · 부록 D.1)에서 사람이 확인한다 `<TODO: vitest 도입 여부 — PI 확인>`.

그래도 이 정적 검사에는 값이 있다. NT-13이 막으려는 것("클라이언트 번들 비밀 0건·자극 사전
로드 0건")은 렌더가 아니라 **번들에 무엇이 들어갔는가**의 문제이고, 그건 파일에서 보인다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.assets import dossier_loader, pairwise_items, rating_items, screen_copy

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
COPY_TS = FRONTEND_SRC / "copy.ts"
APP_TSX = FRONTEND_SRC / "App.tsx"


def _source_files() -> list[Path]:
    return sorted(path for path in FRONTEND_SRC.rglob("*") if path.suffix in {".ts", ".tsx"})


def test_nt19_desktop_guard_threshold_is_1024() -> None:
    """§2.10·§4.0 — 뷰포트 폭 < 1024px 진입 차단."""
    source = COPY_TS.read_text(encoding="utf-8")
    assert re.search(r"MIN_VIEWPORT_WIDTH\s*=\s*1024", source)
    assert screen_copy.MIN_VIEWPORT_WIDTH == 1024, "서버·클라이언트 임계값이 어긋난다"


def test_nt19_guard_text_matches_the_server_copy() -> None:
    """가드 문안은 서버 §4.0 [제안]과 같은 문장이어야 한다."""
    source = COPY_TS.read_text(encoding="utf-8")
    assert screen_copy.DESKTOP_ONLY in source


def test_nt19_app_shell_gates_before_rendering_any_screen() -> None:
    """가드가 화면 선택보다 **앞**에 있어야 한다 — 뒤에 있으면 한 화면은 그려진다."""
    source = APP_TSX.read_text(encoding="utf-8")
    guard_index = source.index("if (tooNarrow) return <DesktopGuard />")
    switch_index = source.index("switch (state.screen)")
    assert guard_index < switch_index


def test_no_mobile_css_rules() -> None:
    """D-12 — 모바일 대응 CSS를 작성하지 않는다. (주석은 그 규칙을 **설명**하므로 제외한다.)"""
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    rules = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for banned in ("@media", "safe-area", "visualViewport", "touch-action"):
        assert banned not in rules, f"모바일 대응 규칙: {banned}"


def test_nt13_no_secrets_in_frontend_sources() -> None:
    """§2.9 — API 키·Basic auth 자격은 환경변수 전용. 번들에 비밀 0건."""
    banned = ("OPENROUTER_API_KEY", "FERNET_KEY", "ADMIN_PASS", "DATABASE_URL", "sk-or-")
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name}: 비밀 문자열 {token}"


def _asset_texts() -> list[str]:
    """번들에 있으면 안 되는 자산 원문 전부 (§1.2 · NT-13).

    v2에서 목록이 늘었다: 조립된 자극 4종은 물론 **R/U/Q segment**도 포함한다 — segment가
    번들에 있으면 클라이언트가 대안 자극을 스스로 조립할 수 있고, 그건 NT-31을 우회한다.
    """
    dossier = dossier_loader.load("P00")
    return [
        *dossier.all_stimuli().values(),
        *(dossier.stimulus.segment(key) for key in dossier_loader.SEGMENT_KEYS),
        dossier.stimulus.neutral_fallback,
        *(item.text for item in rating_items.load().items),
        *(
            item.text
            for entry in pairwise_items.load().sets.values()
            for item in entry.items
        ),
        screen_copy.SIDECAR_Q1,
        screen_copy.SIDECAR_Q2,
        screen_copy.SIDECAR_Q3,
        screen_copy.CHECKPOINT_VERIFY_INTRO,
        screen_copy.USER1_INSTRUCTION,
    ]


def test_nt13_no_stimulus_or_item_text_in_frontend_sources() -> None:
    """자극·문항은 **서버가 화면마다** 내려준다 — 번들에 사전 로드하지 않는다."""
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for asset_text in _asset_texts():
            assert asset_text not in text, f"{path.name}: 자산 원문이 클라이언트에 있다"


def test_nt31_no_condition_label_in_frontend_sources() -> None:
    """§1.2 · NT-31 — 조건 라벨·구성 원리가 참가자 코드에 없다.

    "C1"–"C4"·"uptake"·"elicitation"·`focal_condition` 같은 문자열이 번들에 있으면, 화면이
    조건을 알고 있다는 뜻이거나 언젠가 알게 되는 경로가 열린 것이다.
    """
    banned = ('"C1"', '"C2"', '"C3"', '"C4"', "focal_condition", "alt_order", "pair_sides")
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name}: 조건 라벨 {token}"


@pytest.mark.skipif(not FRONTEND_DIST.is_dir(), reason="빌드 산출물 없음 (npm run build)")
def test_nt13_built_bundle_carries_no_asset_text() -> None:
    """빌드 산출물에도 없어야 한다 — 소스에 없어도 import 경로로 들어올 수 있다."""
    needles = _asset_texts()
    for path in sorted(FRONTEND_DIST.rglob("*")):
        if path.suffix not in {".js", ".css", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            assert needle not in text, f"{path.name}: 자산 원문이 번들에 있다 (NT-13)"


def test_frontend_never_derives_the_next_screen_itself() -> None:
    """§1.3 — 화면 선택은 서버 상태로만 한다. 클라이언트에 상태 전이표가 없어야 한다."""
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        # SS·B 상태 문자열을 클라이언트가 나열하기 시작하면 전이 규칙이 두 곳에 생긴다.
        states = re.findall(r"['\"](SS\d{2}|B[0-7])['\"]", text)
        assert len(set(states)) <= 1, f"{path.name}: 클라이언트가 상태를 나열한다 — {set(states)}"


def test_console_page_is_not_part_of_the_participant_bundle() -> None:
    """§2.1·NT-13 — 연구자 콘솔은 별도 정적 파일이다(빌드 대상 아님).

    콘솔이 참가자 SPA 안으로 들어오면 조건 라벨·researcher_only·sidecar를 다루는 코드가
    참가자 번들에 실린다. 경계를 파일 위치로 지킨다.
    """
    console = REPO_ROOT / "frontend" / "console" / "index.html"
    assert console.is_file(), "콘솔 페이지가 없다 (§4.13 R1–R4)"
    assert not (FRONTEND_SRC / "console").exists(), "콘솔이 참가자 빌드 트리에 있다"
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        assert "/admin/" not in text, f"{path.name}: 참가자 코드가 연구자 API를 부른다"


def test_console_page_carries_no_secrets_or_asset_text() -> None:
    """콘솔도 값은 전부 `/admin/*` JSON에서 받는다 — 파일 자체에는 자산·비밀이 없다."""
    text = (REPO_ROOT / "frontend" / "console" / "index.html").read_text(encoding="utf-8")
    for banned in ("OPENROUTER_API_KEY", "FERNET_KEY", "ADMIN_PASS", "sk-or-"):
        assert banned not in text
    for asset_text in _asset_texts():
        assert asset_text not in text


def test_package_json_has_no_network_analytics() -> None:
    """§9.3 — 참가자 화면에서 제3자로 나가는 경로를 만들지 않는다."""
    package = json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    for banned in ("analytics", "sentry", "gtag", "mixpanel", "hotjar"):
        assert not any(banned in name.lower() for name in dependencies), banned
