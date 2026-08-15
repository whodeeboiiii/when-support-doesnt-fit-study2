"""앱 레벨 Fernet 암호화 (구현명세서 §2.9 — v5.0 §2.9 ADOPT).

DB에는 ciphertext만 저장한다. pgcrypto는 채택하지 않는다(SQL 로그에 키 노출 경로 발생).

암호화 대상(§2.9): User1 원문·정규화본, AI2 출력, sidecar free_text·reason_text, flag 사유.
복호화 지점은 **정확히 2곳**이다 — ① 연구자 콘솔 표시 ② 분석 export. 두 곳 모두 복호화
조회를 `audit_logs`에 남길 의무가 있다(`security/audit.py`).

파이프라인 무영향: LLM 경로에는 어차피 §6.2 allowlist가 만든 payload만 들어가므로
암호화가 AI2 생성 경로를 건드리지 않는다.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import get_settings


class MissingFernetKey(RuntimeError):
    """FERNET_KEY 미설정 — 암호화 대상 필드를 쓰는 경로는 여기서 멈춘다(§2.4)."""


def _cipher() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise MissingFernetKey("FERNET_KEY 환경변수가 없다 (§2.4)")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> bytes:
    return _cipher().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """§2.9의 2개 복호화 지점에서만 호출한다. 호출부는 audit 기록 의무가 있다."""
    return _cipher().decrypt(ciphertext).decode("utf-8")


def generate_key() -> str:
    """운영 준비용 — `.env`의 FERNET_KEY 값 생성."""
    return Fernet.generate_key().decode()
