"""dossier **researcher_only** 층 로더 — 연구자 콘솔 전용 (구현명세서 §1.2 · §5.2).

이 모듈이 존재하는 이유는 하나다: researcher_only(회고 stance·미전송 생각·mismatch 해석·
원 trajectory·ideal response·correction labor)는 §1.2 표에서 **AI2·checker·normalization
전부 금지**이고, 금지를 주석이 아니라 **모듈 경계**로 만들기 위해서다.

    구현 규율(§1.2): researcher_only는 서버에서 별도 모듈(`dossier_private.py`)로만 로드하고,
    LLM payload 조립기(`llm/…`)는 이 모듈을 import할 수 없다 — 정적 검사 NT-04.

허용 호출부는 콘솔 R3(review 뷰 요약)·R4(dossier 뷰어)와 분석 export뿐이다. 여기서 나온
문자열이 프롬프트 문자열 조립에 들어가는 코드 경로는 존재해서는 안 된다.
"""

from __future__ import annotations

from typing import Any

from app.assets.files import read_raw

#: §5.2 스키마의 researcher_only 필드. 없는 키는 빈 문자열로 채워 콘솔 표시를 단순화한다.
RESEARCHER_ONLY_FIELDS: tuple[str, ...] = (
    "retrospective_stance",
    "unsent_at_the_time",
    "mismatch_interpretation",
    "original_trajectory",
    "ideal_response_reported",
    "correction_labor_notes",
)


def load_researcher_only(participant_no: str) -> dict[str, Any]:
    """researcher_only 층만 돌려준다 (콘솔 전용).

    ai_visible·derivation은 여기서 돌려주지 않는다 — 필요하면 호출부가 `dossier_loader`를
    따로 부른다. 한 함수가 세 층을 함께 반환하면 콘솔용 dict가 그대로 다른 곳으로 흘러간다.
    """
    document, _path, _is_dummy = read_raw(participant_no)
    layer = document.get("researcher_only") or {}
    if not isinstance(layer, dict):
        raise ValueError(f"{participant_no}: researcher_only 층이 객체가 아니다 (§5.2)")
    return {field: layer.get(field, "") for field in RESEARCHER_ONLY_FIELDS}
