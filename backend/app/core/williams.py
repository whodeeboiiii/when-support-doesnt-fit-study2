"""Williams balanced Latin square + 번호 순환 매핑 (구현명세서 §3.3 · D-09).

**이 파일이 배정의 전부다.** §3.3이 못박은 규율 — "코드·자산 어디에도 별도 배정 로직을 두지
않는다" — 을 지키려면 조건 결정이 한 곳에만 있어야 한다. 층화 무작위·추첨·저장된 난수 같은
것은 존재하지 않는다: 참가자 번호가 sequence를, sequence와 branch_index가 조건을 결정한다.

    sequence_index = (참가자 번호 − 1) mod 4 + 1

이 매핑은 결정론이므로 재진입·새로고침에서 "다시 뽑는" 경로가 원천적으로 없다(NT-07·08).
`branches.condition`을 저장하는 이유는 재추첨 방지가 아니라 **감사**다 — 저장값과 이 함수의
산출이 다르면 그건 자산·코드가 중간에 바뀌었다는 뜻이고, 그때는 저장값이 이긴다(§1.3).

P00(QA 합성 참가자)은 번호가 0이라 `(0−1) mod 4 + 1 = 4` → S4를 받는다. 분석 제외 자산이므로
균형 설계에는 영향이 없다(§5.1).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

#: §3.3 표. 네 조건이 각 serial position에 1회씩, 12개 directed adjacent pair가 각 1회씩(NT-06).
SEQUENCES: Mapping[int, tuple[str, str, str, str]] = MappingProxyType(
    {
        1: ("C1", "C2", "C4", "C3"),
        2: ("C2", "C3", "C1", "C4"),
        3: ("C3", "C4", "C2", "C1"),
        4: ("C4", "C1", "C3", "C2"),
    }
)

#: §3.2 branch_index b ∈ {1,2,3,4}
BRANCH_INDICES: tuple[int, int, int, int] = (1, 2, 3, 4)


def participant_ordinal(participant_no: str) -> int:
    """`"P03"` → 3. 형식이 어긋나면 배정을 추측하지 않고 멈춘다."""
    if len(participant_no) != 3 or participant_no[0] != "P" or not participant_no[1:].isdigit():
        raise ValueError(f"참가자 번호 형식이 아니다: {participant_no!r} (P00–P12)")
    return int(participant_no[1:])


def sequence_index(participant_no: str) -> int:
    """§3.3 `(참가자 번호 − 1) mod 4 + 1`."""
    return (participant_ordinal(participant_no) - 1) % 4 + 1


def sequence(participant_no: str) -> tuple[str, str, str, str]:
    return SEQUENCES[sequence_index(participant_no)]


def condition(participant_no: str, branch_index: int) -> str:
    """§5.4 `condition = williams[sequence][branch_index]`."""
    if branch_index not in BRANCH_INDICES:
        raise ValueError(f"branch_index는 1–4여야 한다 (받은 값: {branch_index!r})")
    return sequence(participant_no)[branch_index - 1]
