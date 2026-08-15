"""환경변수·확정 파라미터 로딩 (구현명세서 v1.0.1 §2.4 · §0.5).

원칙 (v5.0 §2.4.3 규율 승계)
- 비밀정보는 환경변수로만 받는다. 코드에 기본값을 두지 않는다.
- §0.5의 '확정 파라미터'는 코드 기본값으로 둔다 — 변경은 QA·soft launch 튜닝 창에서만
  근거와 함께(§1.4).
- 미확정 항목은 `<TODO: …>` 태그로 남긴다(명세 태그 규약 — 부록 E.4 색인).

`DEV_MODE=true`는 배포 구성과 **동일 코드 경로**를 돌리되 두 지점만 갈아끼운다(§2.0):
① LLM 클라이언트(fake_llm) ② DB URL(SQLite).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

#: DEV_MODE에서 `DATABASE_URL`이 비었을 때 쓰는 로컬 DB (§2.0 "로컬 DB(SQLite, SQLAlchemy URL 교체)").
DEV_DATABASE_URL = "sqlite+aiosqlite:///./dev_local.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- DB (§2.4) ---
    # schema는 연결 수준(search_path)에서만 결정한다 — 코드에 schema-qualified 이름 금지.
    # `proto_v1`(시연·QA) → `main_v1`(본실험). Alembic 미도입 — 전환은 schema 단위로 한다.
    database_url: str = ""
    db_schema: str = "proto_v1"
    study_version: str = "proto_v1"

    # --- LLM (§2.2) ---
    openrouter_api_key: str | None = None
    #: [확인 1] 슬러그 가용성·단가는 개발 착수 시 OpenRouter 현행으로 재확인한다(부록 F).
    main_model_id: str | None = None
    validator_model_id: str | None = None
    #: §0.5 — 동시 세션 상정 1–2
    llm_concurrency: int = 2
    #: §0.5 [파일럿 확정]
    ai2_timeout_ms: int = 90_000
    checker_timeout_ms: int = 45_000

    # --- 연구자 콘솔 (§2.7 HTTP Basic auth) ---
    admin_user: str | None = None
    admin_pass: str | None = None

    # --- 암호화 (§2.9) ---
    fernet_key: str | None = None

    # --- 운영 알림 (§2.8) ---
    discord_webhook_url: str | None = None

    # --- 팀 시연·CI 구성 (§0.5·§2.0) ---
    dev_mode: bool = False

    @property
    def resolved_database_url(self) -> str:
        """DB URL 분기 지점 (§2.0). DEV_MODE에서 미설정이면 로컬 SQLite로 수렴한다.

        운영(DEV_MODE=false)에서는 절대 대체값을 만들지 않는다 — 미설정은 기동 실패가
        맞다. 조용히 로컬 파일 DB로 흘러내리면 수집 데이터가 배포 DB 밖에 쌓인다.
        """
        if self.database_url:
            return self.database_url
        if self.dev_mode:
            return DEV_DATABASE_URL
        raise RuntimeError("DATABASE_URL이 설정되지 않았다 (§2.4). DEV_MODE=true가 아니면 필수다.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
