"""제시 순서 무작위화 (구현명세서 §3.5 · §4.9 · D-13 · NT-08).

요구가 둘인데 서로 당긴다.

- **무작위**: P8 평정 문항은 블록 내 무작위 순서로 제시한다(D-13·D-22). **pairwise 문항은
  이 모듈을 쓰지 않는다** — 자산 파일 순서 고정이다(D-42).
- **불변**: 새로고침·재접속에서 "자극·순서 재추첨 없음"(§3.5·NT-08).

둘을 동시에 만족시키는 방법은 두 가지다 — ① 뽑아서 저장하거나 ② 세션 고유값으로 시드를 만들어
매번 같은 순서를 재현하거나. 여기서는 ②를 쓴다. §8.1 표에 "제시 순서" 저장 테이블이 없고
(`ratings.display_order`는 **제출 시점**에 기록되는 열이다), 표에 없는 테이블을 만드는 것보다
결정론 시드가 명세에 덜 개입한다.

시드는 세션 id(서버가 만든 UUID)를 포함하므로 참가자·세션마다 순서가 다르고, 같은 세션·같은
블록에서는 몇 번을 새로고침해도 같다. 참가자가 예측할 수 있는 값이 아니다.
"""

from __future__ import annotations

import hashlib
import random
from typing import Sequence, TypeVar

T = TypeVar("T")


def seed_from(*parts: object) -> int:
    """시드 문자열 → 정수. sha256을 쓰는 이유는 `hash()`가 프로세스마다 달라지기 때문이다."""
    material = "|".join(str(part) for part in parts)
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest(), "big")


def seeded_order(items: Sequence[T], *seed_parts: object) -> list[T]:
    """같은 시드에는 항상 같은 순서 (NT-08).

    `random.Random`은 CPython 구현이 고정된 Mersenne Twister라 버전 간 재현성이 있다. 그래도
    이 함수의 계약은 "같은 프로세스 수명 안에서 같은 순서"가 아니라 **저장된 결과와 화면의
    일치**이므로, 제출 시점에 순서를 `ratings.display_order`로 남겨 사후 재구성에도 대비한다.
    """
    shuffled = list(items)
    random.Random(seed_from(*seed_parts)).shuffle(shuffled)
    return shuffled
