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


def test_nt19_desktop_guard_threshold_is_768x600() -> None:
    """§2.10·§4.0 — 뷰포트 768×600 미만 진입 차단 (D-38 — 종전 1024 폭 단독).

    768은 임의의 값이 아니다. `.screen`의 max-width가 760px이라 그 위로는 단일 컬럼
    화면이 큰 모니터와 동일하게 렌더된다 — 아래 `test_nt19_threshold_saturates_the_screen_column`이
    두 값이 같이 움직이도록 묶는다.
    """
    source = COPY_TS.read_text(encoding="utf-8")
    assert re.search(r"MIN_VIEWPORT_WIDTH\s*=\s*768", source)
    assert re.search(r"MIN_VIEWPORT_HEIGHT\s*=\s*600", source)
    assert screen_copy.MIN_VIEWPORT_WIDTH == 768, "서버·클라이언트 폭 임계값이 어긋난다"
    assert screen_copy.MIN_VIEWPORT_HEIGHT == 600, "서버·클라이언트 높이 임계값이 어긋난다"


def test_nt19_threshold_saturates_the_screen_column() -> None:
    """가드 임계값 ≥ `.screen` max-width — 통과한 뷰포트는 본문 폭이 균일해야 한다(D-38).

    이 관계가 깨지면 가드를 통과한 참가자끼리 본문 폭이 달라진다. 명세 §2.10이 데스크톱
    가드를 두는 이유가 그것이라, 둘 중 하나만 바뀌면 실패해야 한다.
    """
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    match = re.search(r"\.screen\s*\{[^}]*?max-width:\s*(\d+)px", css, flags=re.DOTALL)
    assert match, ".screen의 max-width를 찾지 못했다"
    assert screen_copy.MIN_VIEWPORT_WIDTH >= int(match.group(1))


def test_nt19_guard_blocks_landscape_phones() -> None:
    """D-12 — 폭만 보면 가로 모드 휴대폰이 통과한다. 높이 임계가 그것을 막는다.

    폭 768만 쓰면 iPhone 16 Pro Max 가로(956×440)가 데스크톱으로 통과한다. 반대로 흔한
    데스크톱 창(1280×720)은 계속 통과해야 한다 — 가드가 다시 정상 사용을 막으면 안 된다.
    """
    width_min, height_min = screen_copy.MIN_VIEWPORT_WIDTH, screen_copy.MIN_VIEWPORT_HEIGHT

    def blocked(width: int, height: int) -> bool:
        return width < width_min or height < height_min

    assert blocked(430, 932), "세로 모드 휴대폰"
    assert blocked(956, 440), "가로 모드 휴대폰 — 높이로 걸러야 한다"
    assert blocked(844, 390), "가로 모드 휴대폰"
    assert not blocked(1280, 720), "흔한 데스크톱 창"
    assert not blocked(960, 1040), "1920 모니터 좌우 분할 — 종전 1024 임계가 막던 구성"


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
    """D-12 — 모바일 대응 CSS를 작성하지 않는다. (주석은 그 규칙을 **설명**하므로 제외한다.)

    `@media`를 통째로 막던 것을 **폭 기반 질의 금지**로 좁혔다(D-39). 접근성 질의
    (`prefers-reduced-motion`)는 반응형 레이아웃이 아니라서 D-12와 무관한데, 통짜 금지가
    그것까지 막고 있었다. 대신 `min-width`/`max-width` 질의는 여전히 금지다 — 그게 실제로
    모바일 대응이 들어오는 문이다.
    """
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    rules = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for banned in ("safe-area", "visualViewport", "touch-action"):
        assert banned not in rules, f"모바일 대응 규칙: {banned}"

    queries = re.findall(r"@media([^{]*)\{", rules)
    for query in queries:
        assert "width" not in query, f"폭 기반 미디어 질의(모바일 대응): @media{query.strip()}"
        assert "prefers-" in query, f"허용되지 않는 미디어 질의: @media{query.strip()}"


def test_no_dark_mode() -> None:
    """§0.4 — 다크모드를 도입하지 않는다. 자극 표시 조건이 기기 설정에 따라 갈리면 안 된다."""
    css = _strip_comments((FRONTEND_SRC / "index.css").read_text(encoding="utf-8"))
    assert "prefers-color-scheme" not in css
    for path in _source_files():
        code = _strip_comments(path.read_text(encoding="utf-8"))
        assert "dark:" not in code, f"{path.name}: 다크모드 클래스"


def test_body_text_is_at_least_16px() -> None:
    """Zoom 화면공유는 한 번 더 축소되어 상대에게 도달한다 — 본문 16px 밑으로 내리지 않는다."""
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    match = re.search(r"body\s*\{[^}]*?font-size:\s*(\d+)px", css, flags=re.DOTALL)
    assert match, "body font-size를 찾지 못했다"
    assert int(match.group(1)) >= 16


def test_ai_bubbles_have_no_color_tint() -> None:
    """AI 버블에 색조를 넣지 않는다 — 따뜻함 지각이 recognition·uptake 평정과 교락한다.

    `.bubble-ai`는 흰 배경 + 무채색 테두리 고정이다. accent(파랑)·guide(노랑)가 여기 들어오면
    조건 간 자극 동일성 이전에 **자극 자체의 성질**이 바뀐다.
    """
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    match = re.search(r"\.bubble-ai\s*\{(.*?)\}", css, flags=re.DOTALL)
    assert match, ".bubble-ai 정의를 찾지 못했다"
    rule = match.group(1)
    for tint in ("accent", "guide", "amber", "yellow", "blue", "sky"):
        assert tint not in rule, f".bubble-ai에 색조: {tint}"


def test_ai_bubble_fill_is_achromatic() -> None:
    """AI 말풍선 색은 **R=G=B**여야 한다 — 제약은 색조(hue)이지 명도가 아니다.

    흰색일 필요는 없다(흰 카드 위에서 말풍선이 묻힌다). 회색은 hue가 0이라 따뜻함/차가움
    지각을 건드리지 않으므로 recognition·uptake 평정과 교락하지 않는다. 이 테스트는 그
    경계를 숫자로 잡는다 — `#F2F2F2`는 통과하고 `#F2F0EE`(살짝 따뜻함)는 실패한다.
    """
    config = (REPO_ROOT / "frontend" / "tailwind.config.js").read_text(encoding="utf-8")
    block = re.search(r"stim:\s*\{(.*?)\}", config, flags=re.DOTALL)
    assert block, "stim 토큰을 찾지 못했다"

    hexes = re.findall(r"#([0-9A-Fa-f]{6})", block.group(1))
    assert hexes, "stim에 색값이 없다"
    for value in hexes:
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
        assert red == green == blue, f"#{value}는 무채색이 아니다 (R={red} G={green} B={blue})"


def test_new_response_highlight_is_defined_in_exactly_one_place() -> None:
    """focal AI1 · 대안 AI1 3종 · AI2의 하이라이트는 **같은 스타일·같은 타이밍**이어야 한다.

    조건마다 표시가 달라지면 그 자체가 조작이 된다. 그래서 ① 스타일 정의는 `index.css`의
    `.bubble-new` 한 곳뿐이고 ② 화면은 boolean `isNew`만 넘긴다 — className을 넘길 수 있으면
    호출부마다 갈린다.
    """
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    assert css.count(".bubble-new") >= 1

    for path in _source_files():
        code = _strip_comments(path.read_text(encoding="utf-8"))
        if path.name == "Chat.tsx":
            continue
        assert "bubble-new" not in code, f"{path.name}: 하이라이트를 직접 그린다"

    screens = FRONTEND_SRC / "screens"
    sites = {
        path.name: len(re.findall(r"isNew(?:\s*/>|\s+|\}|=)", path.read_text(encoding="utf-8")))
        for path in screens.glob("*.tsx")
    }
    # P4 focal AI1 · P9 대안 AI1 · P6/P7 AI2(FocalTranscript 1곳) — 세 파일에만 있다.
    assert sites.get("Focal.tsx", 0) >= 2, "focal AI1·AI2 하이라이트가 빠졌다"
    assert sites.get("Exposure.tsx", 0) >= 1, "대안 AI1 하이라이트가 빠졌다"
    assert sites.get("Intro.tsx", 0) == 0, "checkpoint 재구성은 새 응답이 아니다"


def test_new_response_highlight_is_not_overridden_by_an_animation_utility() -> None:
    """`.bubble-new`의 링이 등장 애니메이션에 먹히지 않아야 한다.

    실제로 한 번 났던 버그다. 말풍선에 `animate-bubble-in`(utilities 레이어)을 붙이고
    `.bubble-new`(components 레이어)에 링을 두었더니, 같은 `animation` shorthand·같은
    명시도라 **뒤에 오는 utilities가 이겼다**. 빌드는 통과하고 CSS도 존재하는데 링만
    영영 실행되지 않는다 — 눈으로 보기 전에는 안 잡힌다.

    그래서 두 가지를 못박는다. ① `.bubble-new`가 두 애니메이션을 **한 선언에서** 합성한다.
    ② 말풍선 컴포넌트에 `animate-` 유틸리티를 붙이지 않는다.
    """
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    match = re.search(r"\.bubble-new\s*\{(.*?)\}", css, flags=re.DOTALL)
    assert match, ".bubble-new 정의를 찾지 못했다"
    rule = match.group(1)
    assert "ring-settle" in rule, "링 애니메이션이 없다"
    assert "bubble-in" in rule, "등장 애니메이션을 합성하지 않았다 — 유틸리티가 링을 덮어쓴다"

    # `bubble-new`가 붙는 **그 element**의 className만 본다 — 타이핑 점의 `animate-pulse`는
    # 다른 element라 무관하다.
    chat = _strip_comments((FRONTEND_SRC / "components" / "Chat.tsx").read_text(encoding="utf-8"))
    holder = re.search(r"className=\{`([^`]*bubble-new[^`]*)`\}", chat)
    assert holder, "bubble-new를 붙이는 className을 찾지 못했다"
    assert "animate-" not in holder.group(1), (
        "말풍선에 animate 유틸리티 — utilities 레이어가 `.bubble-new`를 덮어쓴다"
    )


@pytest.mark.skipif(not FRONTEND_DIST.is_dir(), reason="빌드 산출물 없음 (npm run build)")
def test_every_animation_reference_has_a_keyframes_definition() -> None:
    """참조한 애니메이션은 빌드 CSS에 **정의**가 있어야 한다.

    두 번째로 난 조용한 실패다. tailwind.config의 `keyframes`는 대응하는 `animate-*`
    유틸리티가 소스에서 발견될 때만 빌드에 실린다. 컴포넌트 클래스에서 raw `animation:`으로만
    참조하면 JIT가 그 사용을 못 보고 `@keyframes`를 통째로 지운다 — CSS에는
    `animation: ring-settle ...`이 남지만 정의가 없어 브라우저는 **조용히 아무것도 안 한다**.

    클래스 존재 확인으로는 못 잡는다(클래스도 선언도 다 있었다). 참조와 정의를 **연결해서**
    본다.
    """
    sheets = list(FRONTEND_DIST.rglob("*.css"))
    assert sheets, "빌드된 CSS가 없다"
    css = "\n".join(path.read_text(encoding="utf-8") for path in sheets)

    defined = set(re.findall(r"@keyframes\s+([A-Za-z0-9_-]+)", css))
    referenced: set[str] = set()
    for declaration in re.findall(r"[^-]animation:([^;}]+)", css):
        for part in declaration.split(","):
            tokens = [token for token in part.strip().split() if token]
            for token in tokens:
                # 이름은 시간·easing·fill-mode가 아닌 첫 식별자다.
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", token) and token not in {
                    "ease", "ease-in", "ease-out", "ease-in-out", "linear", "both",
                    "forwards", "backwards", "none", "infinite", "normal", "alternate",
                    "reverse", "running", "paused",
                }:
                    referenced.add(token)
                    break

    missing = sorted(name for name in referenced if name not in defined)
    assert not missing, f"@keyframes 정의가 없는 애니메이션: {missing}"


@pytest.mark.skipif(not FRONTEND_DIST.is_dir(), reason="빌드 산출물 없음 (npm run build)")
def test_built_css_keeps_the_ring_after_the_entrance_animation() -> None:
    """빌드 산출물에서도 링이 살아 있어야 한다 — 레이어 순서는 컴파일 후에야 확정된다."""
    sheets = [path for path in FRONTEND_DIST.rglob("*.css")]
    assert sheets, "빌드된 CSS가 없다"
    css = "\n".join(path.read_text(encoding="utf-8") for path in sheets)

    rules = re.findall(r"\.bubble-new\{([^}]*)\}", css)
    assert rules, "빌드 CSS에 .bubble-new가 없다"
    animated = [rule for rule in rules if "animation:" in rule]
    assert animated, ".bubble-new에 animation 선언이 없다"
    for rule in animated:
        assert "ring-settle" in rule, f"링이 빠졌다: {rule}"

    # 유틸리티가 나중에 나와 덮어쓸 여지 자체를 없앤다.
    assert "animate-bubble-in" not in css, "등장 애니메이션 유틸리티가 번들에 남아 있다"


def test_yellow_is_never_used_on_buttons() -> None:
    """노랑은 지시문 블록 전용이다 — 노랑 위 흰 글자는 대비가 안 나온다(D-39)."""
    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    for name in ("btn-primary", "btn-secondary", "is-selected"):
        match = re.search(rf"\.{name}\s*\{{(.*?)\}}", css, flags=re.DOTALL)
        assert match, f".{name} 정의를 찾지 못했다"
        assert "guide" not in match.group(1), f".{name}에 노랑"


def test_edited_badge_is_confined_to_the_checkpoint_edit_screen() -> None:
    """"수정됨" 배지는 P2에서만 뜬다(D-39).

    이후 화면에서 "당신이 고친 문장"이라고 계속 상기시키면 그 자체가 자극의 일부가 된다.
    배지는 `edit` prop이 있을 때만 그려지고, 그 prop은 P2만 넘긴다 — 구조로 막는다.
    """
    intro = (FRONTEND_SRC / "screens" / "Intro.tsx").read_text(encoding="utf-8")
    assert "수정됨" in intro

    for path in (FRONTEND_SRC / "screens").glob("*.tsx"):
        if path.name == "Intro.tsx":
            continue
        assert "수정됨" not in path.read_text(encoding="utf-8"), f"{path.name}: 배지 노출"

    # `edit`를 넘기는 곳은 P2 하나뿐이다.
    assert len(re.findall(r"<CheckpointCard[^>]*\sedit=", intro, flags=re.DOTALL)) == 1
    for path in (FRONTEND_SRC / "screens").glob("*.tsx"):
        if path.name == "Intro.tsx":
            continue
        code = path.read_text(encoding="utf-8")
        assert not re.search(r"<CheckpointCard[^>]*\sedit=", code, flags=re.DOTALL), path.name


def test_no_progress_indicator_component() -> None:
    """스텝 인디케이터를 두지 않는다 — 남은 분량 수치는 조건·대안 수의 실마리가 된다."""
    for path in _source_files():
        code = _strip_comments(path.read_text(encoding="utf-8"))
        assert "ProgressBar" not in code, f"{path.name}: 진행 표시"


def _strip_comments(source: str) -> str:
    """`/* */`·`//` 주석 제거 — 규칙을 설명하는 주석이 규칙 위반으로 잡히지 않게 한다."""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.MULTILINE)


def test_dev_labels_are_gated_by_the_server_not_a_build_flag() -> None:
    """DEV 설명 레이블은 `/api/dev/status`가 정한다 — 빌드 플래그로 켜면 안 된다.

    §4.10은 조건·construct 라벨을 참가자에게 비공개로 둔다. 레이블 문안은 초안 용어
    ("mismatch locus" 등) 그대로라 참가자 화면에 뜨면 그 규칙이 깨진다. `import.meta.env`로
    켜면 빌드 설정 하나가 그 경로가 되므로, DevBar와 같은 규율(서버 404 = 미표시)에 묶는다.
    """
    for path in _source_files():
        # 주석은 이 규칙을 **설명**하므로 제외한다(`test_no_mobile_css_rules`와 같은 처리).
        code = _strip_comments(path.read_text(encoding="utf-8"))
        assert "import.meta.env" not in code, f"{path.name}: 클라이언트 DEV 플래그"

    source = (FRONTEND_SRC / "components" / "DevNote.tsx").read_text(encoding="utf-8")
    assert "dev.status()" in source, "DevNote가 서버에 묻지 않는다"


def test_dev_label_components_render_nothing_without_dev_mode() -> None:
    """세 컴포넌트 전부 `useDevMode()` 뒤에 그린다 — 하나라도 빠지면 배포에서 샌다."""
    source = (FRONTEND_SRC / "components" / "DevNote.tsx").read_text(encoding="utf-8")
    for component in ("DevNote", "DevAside", "DevScreenNote"):
        body = source.split(f"export function {component}(", 1)
        assert len(body) == 2, f"{component}를 찾지 못했다"
        assert "useDevMode()" in body[1].split("\n}")[0], f"{component}가 게이트 밖이다"


def test_dev_screen_notes_cover_every_screen() -> None:
    """P0–P12 전 화면에 DEV 배너가 있어야 한다.

    배너를 손으로 넣다 보면 한 화면이 빠지거나 **다른 화면 안에** 들어간다(실제로 P7·P11에서
    한 번씩 났다). 여기서는 존재만 본다 — 위치는 배너의 `screen` 값과 화면 제목을 QA
    워크스루에서 눈으로 대조한다(§10.2).
    """
    sources = "".join(
        path.read_text(encoding="utf-8") for path in (FRONTEND_SRC / "screens").glob("*.tsx")
    )
    missing = [f"P{n}" for n in range(13) if f'screen="P{n}"' not in sources]
    assert not missing, f"DEV 배너 없는 화면: {missing}"


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
        # 무대지시도 서버가 `ai1_note`로 내려주는 자산 문면이다 — 번들에 박으면 클라이언트가
        # 조건별 표시를 스스로 정하게 된다(D-40). A-level별 3종 전부를 본다(D-47 — A0은 빈
        # 문자열이라 대조 대상이 아니다: 빈 문자열은 어떤 파일에도 "들어 있다").
        *(note for note in dossier_loader.UPTAKE_NOTE_BY_A_LEVEL.values() if note),
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


def test_uptake_note_is_rendered_from_one_place() -> None:
    """D-40 — 무대지시의 회색 표시는 `StimulusText` 한 곳에서만 정의된다.

    `.bubble-new`와 같은 규율이다(D-39): 자극의 표시가 호출부마다 갈리면 그 자체가 조작이
    된다. 색은 `index.css`의 `.stim-note` 하나뿐이고, 화면은 서버가 준 문면을 넘기기만 한다.
    """
    chat = (FRONTEND_SRC / "components" / "Chat.tsx").read_text(encoding="utf-8")
    assert "export function StimulusText" in chat
    assert chat.count("stim-note") == 1, "무대지시 색이 두 곳에서 정의됐다"

    css = (FRONTEND_SRC / "index.css").read_text(encoding="utf-8")
    assert css.count(".stim-note") == 1

    # 화면은 문면을 만들지 않는다 — 서버 필드를 그대로 넘긴다.
    for name in ("screens/Focal.tsx", "screens/Exposure.tsx", "screens/Wrap.tsx"):
        text = (FRONTEND_SRC / name).read_text(encoding="utf-8")
        assert "ai1_note" in text, f"{name}: 무대지시 필드를 넘기지 않는다"


def test_uptake_note_color_is_achromatic() -> None:
    """무대지시도 자극 안이다 — 색조를 넣지 않는다(`stim` 토큰 규율 그대로)."""
    config = (REPO_ROOT / "frontend" / "tailwind.config.js").read_text(encoding="utf-8")
    block = re.search(r"stim:\s*\{(.*?)\}", config, flags=re.DOTALL)
    assert block and "note:" in block.group(1), "무대지시 색이 stim 토큰 밖에 있다"


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
