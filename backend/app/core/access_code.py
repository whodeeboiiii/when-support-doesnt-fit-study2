"""일회용 접속 코드 (구현명세서 §2.5 · §0.5 · §4.0 · NT-27).

    연구자가 R1에서 세션 생성 → 6자리 일회용 접속 코드 발급(세션당 1개, TTL 24h).
    … 코드 만료 시 연구자가 재발급(**동일 세션에 바인딩** — 새 세션 생성 아님).

세 가지가 이 모듈의 계약이다.

1. **평문 코드는 저장하지 않는다.** `sessions.access_code_hash`만 남는다(§8.1). 연구자에게는
   발급 응답에서 **한 번만** 보여주고, 잃어버리면 재발급이다(그래서 재발급이 있다).
2. **재발급은 같은 세션의 hash·만료를 갈아끼운다.** 새 행을 만들면 참가자당 완료 세션 1개
   불변식(NT-12)과 저장 지점 복원(§3.5)이 동시에 깨진다.
3. **무차별 대입 지연**(§4.0): 실패 5회 → 30초. 12명 규모라 프로세스 메모리로 충분하다.
   영속 카운터를 만들면 그것 자체가 참가자 식별 로그가 된다.

코드는 참가자 번호와 **함께** 해시한다. 12세션 규모에서 6자리 코드의 엔트로피는 크지 않은데,
번호를 섞으면 "아무 번호에나 아무 코드"를 넣어 맞히는 경로가 사라진다(번호+코드 쌍이 맞아야
한다). 어차피 §8.2의 검증도 {participant_no, access_code} 쌍이다.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

#: 혼동 문자(0·O, 1·I·L)를 뺀 영숫자. 코드는 Zoom 화면공유 중 구두로도 전달된다.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

#: §0.5 [파일럿 확정]
CODE_TTL = timedelta(hours=24)

#: §4.0 "실패 5회 시 30초 지연 — 무차별 대입 방어"
MAX_FAILURES = 5
FAILURE_DELAY_S = 30


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize(code: str) -> str:
    """대소문자·공백·하이픈은 참가자 입력 실수이지 다른 코드가 아니다."""
    return "".join(character for character in code.upper() if character.isalnum())


def hash_code(participant_no: str, code: str) -> str:
    material = f"{participant_no.upper()}:{normalize(code)}".encode()
    return hashlib.sha256(material).hexdigest()


def verify(participant_no: str, code: str, stored_hash: str) -> bool:
    """타이밍 비교로 맞춘다 — 6자리라 side channel이 상대적으로 값싸다."""
    return hmac.compare_digest(hash_code(participant_no, code), stored_hash)


def expires_at(issued_at: datetime | None = None) -> datetime:
    return (issued_at or datetime.now(UTC)) + CODE_TTL


def is_expired(code_expires_at: datetime | None, now: datetime | None = None) -> bool:
    """만료 시각이 없으면 만료로 본다 — 미상은 통과가 아니다(§9.1 → 연구자 재발급)."""
    if code_expires_at is None:
        return True
    reference = now or datetime.now(UTC)
    if code_expires_at.tzinfo is None:
        # SQLite는 tz를 잃는다(DEV_MODE). 저장은 항상 UTC이므로 그렇게 읽는다.
        code_expires_at = code_expires_at.replace(tzinfo=UTC)
    return code_expires_at <= reference


# --------------------------------------------------------------------------- #
# 실패 지연 (§4.0)
# --------------------------------------------------------------------------- #


@dataclass
class _Failures:
    count: int = 0
    blocked_until: float = 0.0


_failures: dict[str, _Failures] = {}


def reset_throttle() -> None:
    """테스트·재시작 경계용."""
    _failures.clear()


def retry_after(participant_no: str, now: float) -> int:
    """지금 이 번호로 시도할 수 있는가 — 남은 지연(초). 0이면 시도 가능."""
    entry = _failures.get(participant_no.upper())
    if entry is None or entry.blocked_until <= now:
        return 0
    # 올림 — Retry-After가 실제 해제 시각보다 이르면 참가자가 한 번 더 튕긴다.
    return max(1, math.ceil(entry.blocked_until - now))


def record_failure(participant_no: str, now: float) -> int:
    """실패 1건. 임계에 닿으면 지연을 걸고 카운터를 되돌린다."""
    entry = _failures.setdefault(participant_no.upper(), _Failures())
    entry.count += 1
    if entry.count >= MAX_FAILURES:
        entry.count = 0
        entry.blocked_until = now + FAILURE_DELAY_S
    return retry_after(participant_no, now)


def record_success(participant_no: str) -> None:
    _failures.pop(participant_no.upper(), None)
