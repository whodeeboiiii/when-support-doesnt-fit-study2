"""prompt_config 로더 (구현명세서 §6.6 · 부록 A.1·A.2 (v2)).

`prompts/prompt_config_v2.json`이 **단일 정본**이다: AI2 시스템 프롬프트(A.1)·R3 최대 제약
프롬프트(A.1b — D-48)·checker 프롬프트(A.2)·
파라미터(temperature·max_tokens)·`prompt_hash`. (`normalization_patterns_version` 키는 v2에서
삭제됐다 — D-34.) 코드에 프롬프트 문자열을
복사해 두지 않는다 — 두 곳에 있으면 어느 쪽이 실제로 호출된 문안인지 audit이 답하지 못한다.

⚠ 프롬프트 문안 자체는 PI 승인 후 lock 대상이다(부록 A 머리말). 본실험 중 변경은 장애 외
금지이며, 변경 시 cohort를 분리한다(§1.4).

⚠ checker 프롬프트(A.2)에는 출력 예시의 중괄호가 들어 있다. 조립할 때 `str.format`을 그대로
쓰면 깨진다 — NS3의 payload 조립기는 명시 치환(`replace`)을 쓴다.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.llm.gateway.client import ModelRole

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_CONFIG_PATH = REPO_ROOT / "prompts" / "prompt_config_v2.json"

#: 프롬프트 키 (§8.4 audit·fake LLM 분기). 부록 A.1 / A.1b / A.2에 대응한다.
AI2_PROMPT_KEY = "ai2_generation"
CHECKER_PROMPT_KEY = "integrity_checker"

#: §6.1 R3 — **최대 제약 모드**(부록 A.1b, D-48). R1·R2가 모두 기각된 뒤 `neutral_fallback`
#: 직전에 1회 돌린다. 질문 0개·사용자에 대한 서술 금지·맥락 내 내용만으로 출력 공간을 좁혀
#: 세 위반 유형(R-3 / unsupported_inference / expansion)이 **구조적으로 성립할 수 없게** 한다.
#: A.1(`ai2_generation`)은 이것과 무관하게 lock 상태 그대로다.
AI2_CONSTRAINED_PROMPT_KEY = "ai2_constrained"

PROMPT_KEY_ROLE: dict[str, ModelRole] = {
    AI2_PROMPT_KEY: ModelRole.MAIN,
    AI2_CONSTRAINED_PROMPT_KEY: ModelRole.MAIN,
    CHECKER_PROMPT_KEY: ModelRole.VALIDATOR,
}


@lru_cache
def config() -> dict[str, Any]:
    document = json.loads(PROMPT_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{PROMPT_CONFIG_PATH}: prompt_config는 JSON 객체여야 한다")
    return document


def compute_config_hash(document: dict[str, Any]) -> str:
    """`prompt_hash` 자신을 제외한 전체 config의 sha256 (§6.6 재현성)."""
    payload = {key: value for key, value in document.items() if key != "prompt_hash"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def config_hash() -> str:
    """자산에 기재된 `prompt_hash`. 실제 내용과 다르면 기동 게이트가 잡는다(`verify()`)."""
    return str(config()["prompt_hash"])


def verify() -> None:
    """기재 hash와 실제 내용의 일치 확인 — 프롬프트를 고치고 hash를 안 고친 커밋을 잡는다."""
    document = config()
    expected = compute_config_hash(document)
    if document.get("prompt_hash") != expected:
        raise ValueError(
            f"{PROMPT_CONFIG_PATH}: prompt_hash 불일치 — 기재 {document.get('prompt_hash')!r} "
            f"vs 실제 {expected!r} (§6.6)"
        )


def block(prompt_key: str) -> dict[str, Any]:
    document = config()
    try:
        return document[prompt_key]
    except KeyError as exc:  # pragma: no cover - 오타 방지용
        raise KeyError(f"prompt_config에 없는 프롬프트 키: {prompt_key!r}") from exc


def system_template(prompt_key: str) -> str:
    return str(block(prompt_key)["system"])


def parameters(prompt_key: str) -> dict[str, Any]:
    """§0.5·§6.6 생성 파라미터 (AI2 temperature 0.4 / checker 0.0 [파일럿 확정])."""
    return dict(block(prompt_key)["parameters"])


def version_lock() -> dict[str, str]:
    """§8.4 audit에 실리는 자산 버전 묶음."""
    document = config()
    return {
        "prompt_config_version": str(document["version"]),
        "prompt_hash": str(document["prompt_hash"]),
    }


def call_hash(system: str, user: str) -> str:
    """호출 1건의 프롬프트 해시 (§8.4) — 실제 전송된 문자열 기준."""
    return hashlib.sha256(f"{system}\n\x1e\n{user}".encode("utf-8")).hexdigest()


def reset_cache() -> None:
    config.cache_clear()
