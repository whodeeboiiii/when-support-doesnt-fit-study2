"""접속 코드 규칙 (구현명세서 §2.5 · §0.5 · §4.0 — NT-27의 규칙 층).

세션 바인딩(NT-27의 본체)은 API 층에서 본다. 여기서는 코드 자체의 성질만 본다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core import access_code


def test_code_shape() -> None:
    """§0.5 — 6자리 영숫자."""
    for _ in range(50):
        code = access_code.generate_code()
        assert len(code) == access_code.CODE_LENGTH == 6
        assert code.isalnum()
        assert set(code) <= set(access_code.CODE_ALPHABET)


def test_alphabet_excludes_confusable_characters() -> None:
    """Zoom 화면공유 중 구두로도 전달된다 — 0/O·1/I/L을 섞지 않는다."""
    assert not set("01IOL") & set(access_code.CODE_ALPHABET)


def test_codes_are_not_predictable_in_bulk() -> None:
    codes = {access_code.generate_code() for _ in range(200)}
    assert len(codes) > 190, "코드가 반복된다 — 난수원이 의심스럽다"


def test_hash_binds_participant_and_code() -> None:
    """같은 코드라도 참가자 번호가 다르면 다른 해시다."""
    code = "ABC234"
    assert access_code.hash_code("P01", code) != access_code.hash_code("P02", code)
    assert access_code.verify("P01", code, access_code.hash_code("P01", code))
    assert not access_code.verify("P02", code, access_code.hash_code("P01", code))


@pytest.mark.parametrize("typed", ["abc234", " ABC234 ", "ABC-234", "abc-234"])
def test_input_normalization(typed: str) -> None:
    """대소문자·공백·하이픈은 입력 실수이지 다른 코드가 아니다."""
    stored = access_code.hash_code("P01", "ABC234")
    assert access_code.verify("P01", typed, stored)


def test_ttl_is_24h() -> None:
    """§0.5 [파일럿 확정] — TTL 24h."""
    assert access_code.CODE_TTL == timedelta(hours=24)
    issued = datetime(2026, 1, 1, tzinfo=UTC)
    assert access_code.expires_at(issued) == issued + timedelta(hours=24)


def test_expiry_check() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    assert access_code.is_expired(now - timedelta(seconds=1), now)
    assert not access_code.is_expired(now + timedelta(seconds=1), now)
    # 만료 시각이 없으면 만료로 본다 — 미상은 통과가 아니다.
    assert access_code.is_expired(None, now)


def test_naive_datetime_is_read_as_utc() -> None:
    """DEV_MODE의 SQLite는 tz를 잃는다. 저장은 항상 UTC이므로 그렇게 읽어야 한다."""
    now = datetime(2026, 1, 2, tzinfo=UTC)
    stored = (now + timedelta(hours=1)).replace(tzinfo=None)
    assert not access_code.is_expired(stored, now)


def test_failure_delay_after_five_attempts() -> None:
    """§4.0 — 실패 5회 시 30초 지연."""
    access_code.reset_throttle()
    now = 1_000.0
    for attempt in range(access_code.MAX_FAILURES - 1):
        assert access_code.record_failure("P01", now) == 0, f"{attempt + 1}회에서 이르게 막혔다"
    assert access_code.record_failure("P01", now) == access_code.FAILURE_DELAY_S
    assert access_code.retry_after("P01", now) == access_code.FAILURE_DELAY_S
    # 다른 참가자 번호는 막히지 않는다 — 지연은 번호 단위다.
    assert access_code.retry_after("P02", now) == 0
    # 지연이 지나면 다시 시도할 수 있다(dead-end 금지 — §9.1).
    assert access_code.retry_after("P01", now + access_code.FAILURE_DELAY_S + 1) == 0


def test_success_clears_the_counter() -> None:
    access_code.reset_throttle()
    now = 1_000.0
    access_code.record_failure("P01", now)
    access_code.record_success("P01")
    assert access_code.retry_after("P01", now) == 0
