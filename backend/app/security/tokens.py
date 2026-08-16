"""세션 토큰 (구현명세서 §2.5 — "서버 세션 토큰(httpOnly cookie)").

명세는 토큰의 **형태**를 정하지 않는다. 여기서는 세션 id에 HMAC 서명을 붙인 값을 쓴다.

    <session_id>.<hmac_sha256(secret, session_id)[:32]>

이유는 §8.1이다 — `sessions` 표에 토큰 열이 없다. 열을 늘리지 않고 위조를 막으려면 서명이
가장 짧은 길이고, 이 방식은 상태를 하나도 더 만들지 않는다. 서명이 없으면 쿠키에 남의 UUID를
써넣는 것으로 세션이 바뀐다.

비밀은 `FERNET_KEY`에서 파생시킨다(§2.4의 환경변수 목록을 늘리지 않기 위해서다). 키를 바꾸면
발급된 쿠키가 전부 무효가 되는데, 그건 재접속(번호+코드)으로 복구되는 상태다(§3.5).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from app.core.config import get_settings

_SIGNATURE_CHARS = 32


class InvalidToken(ValueError):
    """서명 불일치·형식 오류 — 세션 없음으로 취급한다(401)."""


def _secret() -> bytes:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY가 없어 세션 토큰을 서명할 수 없다 (§2.4)")
    # 암호화 키를 그대로 쓰지 않고 용도 분리 파생을 한 번 거친다.
    return hashlib.sha256(f"session-token:{key}".encode()).digest()


def _signature(session_id: str) -> str:
    return hmac.new(_secret(), session_id.encode(), hashlib.sha256).hexdigest()[:_SIGNATURE_CHARS]


def issue(session_id: uuid.UUID) -> str:
    value = str(session_id)
    return f"{value}.{_signature(value)}"


def read(token: str | None) -> uuid.UUID:
    if not token or "." not in token:
        raise InvalidToken("세션 토큰이 없다")
    value, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _signature(value)):
        raise InvalidToken("세션 토큰 서명이 맞지 않는다")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise InvalidToken("세션 토큰이 UUID 형식이 아니다") from exc
