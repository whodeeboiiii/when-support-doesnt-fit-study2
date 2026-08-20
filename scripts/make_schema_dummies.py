"""schema_dummy dossier 생성 (구현명세서 §2.3 · §5.3 · §11.1 더미 자산 원칙).

    ./backend/.venv/bin/python scripts/make_schema_dummies.py

`dossiers/schema_dummy/P01–P24.json` 24건을 만든다. 전 필드가 `<TODO: PH-03>` placeholder
이면서 **자산 계약(NT-20~23)을 통과한다** — 실값 착지를 기다리며 CI·시연이 돌아야 하기
때문이다(CLAUDE.md 자산 원칙).

더미가 지켜야 하는 것은 스키마가 아니라 **계약**이다.
- `r`·`u`는 질문 0개, `q`는 정확히 1개 (§5.4 · NT-22)
- `stimuli_meta`가 조립 결과의 계량과 일치 (NT-23)
- `neutral_fallback`이 질문 0·1,200자 이하 (NT-21)
- `provenance`가 ai_visible 텍스트 필드 전부를 덮음 (§5.4)
- segment에 researcher_only 문자열 미포함 (§5.4)

a_level·mismatch_locus는 **실제 판정 결과가 아니다**. 배정표 dummy(§5.2)가 strata 편중
방지 제약을 실제로 시험할 수 있도록 세 A-level과 다섯 locus에 고르게 흩뿌린다 — 그래야
`make_assignment.py --self-test`가 의미 있는 입력을 받는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.assets.dossier_loader import (  # noqa: E402
    STIMULUS_RECIPE,
    A_LEVELS,
    MISMATCH_LOCI,
)
from app.assets.files import DUMMY_PARTICIPANT_NUMBERS, schema_dummy_dir  # noqa: E402
from app.core.text_metrics import measure  # noqa: E402

TODO = "<TODO: PH-03"

#: strata를 고르게 흩뿌리기 위한 고정 순환. 정렬 순서를 쓰는 이유는 결정론이다 —
#: 같은 스크립트를 두 번 돌리면 같은 파일이 나와야 diff가 의미를 갖는다.
A_LEVEL_CYCLE = sorted(A_LEVELS)
LOCUS_CYCLE = sorted(MISMATCH_LOCI)


def _document(participant_no: str, index: int) -> dict:
    a_level = A_LEVEL_CYCLE[index % len(A_LEVEL_CYCLE)]
    locus = LOCUS_CYCLE[index % len(LOCUS_CYCLE)]
    pn = participant_no

    # segment 3종 — 질문 수 계약을 지키는 placeholder 문장.
    r = f"{TODO} — {pn} R(recognition) segment 미착지> 이 자리에는 문제 지점을 알아차렸음을 보이는 최소 문장이 들어간다."
    u = f"{TODO} — {pn} U(minimum substantive uptake) segment 미착지> 이 자리에는 현재 evidence가 정당화하는 최소 조정의 실행문이 들어간다."
    q = f"{TODO} — {pn} Q(minimum elicitation) segment 미착지> 지금은 어느 쪽이 더 필요하세요?"

    segments = {"r": r, "u": u, "q": q}
    meta = {
        condition: measure(" ".join(segments[key] for key in keys)).as_dict()
        for condition, keys in STIMULUS_RECIPE.items()
    }

    return {
        "participant_no": pn,
        "version": f"{pn.lower()}_schema_dummy_v2",
        "locked_at": None,
        "hash": None,
        "evidence_code": {
            "a_level": a_level,
            "mismatch_locus": locus,
            "mismatch_locus_text": f"{TODO} — {pn} 무엇이 problematized되었는지 미착지>",
            "directional_constraint": f"{TODO} — {pn} evidence의 방향 제약 미착지>",
            "permitted_operation": f"{TODO} — {pn} U의 상한 미착지>",
            "residual_uncertainty": f"{TODO} — {pn} minimum U 이후 남는 consequential uncertainty 미착지>",
            "consequential_justification": f"{TODO} — {pn} plausible next move 분기 근거 미착지>",
            "prohibited_inference": [
                f"{TODO} — {pn} 금지 추론 목록 미착지 (checker 판정 참조)>"
            ],
            "coders": "researcher_only_ref",
            "adjudicated_at": None,
        },
        "ai_visible": {
            "situation_summary": f"{TODO} — {pn} 상황 요약 미착지> 사건 이해에 필요한 최소 context가 이 자리에 들어간다.",
            "prior_evidence": [
                f"{TODO} — {pn} checkpoint 이전에 사용자가 이미 제공한 정보 미착지>"
            ],
            "original_request": f"{TODO} — {pn} 원 요청 미착지>",
            "problematic_ai_response": f"{TODO} — {pn} 문제된 AI 응답 발췌 미착지>",
            "trouble_cue": f"{TODO} — {pn} 실제 AI-visible trouble turn 미착지>",
            "provenance": {
                "situation_summary": "researcher_paraphrase",
                "prior_evidence": "participant_quote",
                "original_request": "verbatim_log",
                "problematic_ai_response": "participant_quote",
                "trouble_cue": "verbatim_log",
            },
            "excerpt_note": f"{TODO} — {pn} 발췌 생략 범위·2인 확인 기록 참조 미착지>",
        },
        "researcher_only": {
            "retrospective_stance": f"{TODO} — {pn} 회고 stance 미착지>",
            "unsent_at_the_time": f"{TODO} — {pn} 미전송 생각 미착지>",
            "mismatch_interpretation": f"{TODO} — {pn} mismatch 해석 미착지>",
            "original_trajectory": f"{TODO} — {pn} 원 trajectory 미착지>",
            "ideal_response_reported": f"{TODO} — {pn} ideal response 미착지>",
            "correction_labor_notes": f"{TODO} — {pn} correction labor 기록 미착지>",
            "verification_notes": f"{TODO} — {pn} P2·인터뷰에서 나온 private preference 기록 자리>",
        },
        "stimulus": {
            **segments,
            "stimuli_meta": meta,
            "neutral_fallback": (
                f"{TODO} — {pn} neutral fallback 문안 미착지> 말씀해주신 내용은 잘 받았습니다. "
                "지금 말씀해주신 범위 안에서 이어가겠습니다."
            ),
            "qc": {
                "r_identity": False,
                "u_identity": False,
                "q_identity": False,
                "permitted_boundary": False,
                "leakage": False,
                "minimum_q": False,
                "reviewer": f"{TODO} — {pn} 독립 second researcher QC 미실시>",
                "at": None,
            },
        },
    }


def main() -> int:
    target = schema_dummy_dir()
    target.mkdir(parents=True, exist_ok=True)
    for index, participant_no in enumerate(DUMMY_PARTICIPANT_NUMBERS):
        path = target / f"{participant_no}.json"
        document = _document(participant_no, index)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"schema_dummy {len(DUMMY_PARTICIPANT_NUMBERS)}건 생성: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
