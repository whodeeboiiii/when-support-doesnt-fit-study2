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

#: §0.5의 DEV_MODE 정의는 "fake LLM + **로컬 DB**"다. 로컬 DB = SQLite.
LOCAL_DB_SCHEME = "sqlite"


def is_local_db(url: str) -> bool:
    return url.startswith(LOCAL_DB_SCHEME)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- DB (§2.4) ---
    # schema는 연결 수준(search_path)에서만 결정한다 — 코드에 schema-qualified 이름 금지.
    # `proto_v2`(시연·QA) → `main_v2`(본실험). Alembic 미도입 — 전환은 schema 단위로 한다.
    database_url: str = ""
    db_schema: str = "proto_v2"
    study_version: str = "proto_v2"

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

    # --- 자산 경로 (§2.4 신설) ---
    #: PH-04 볼륨 마운트 오버라이드. 기본 = 리포 `dossiers/`.
    #: ⚠ 실제로 읽는 곳은 `assets/files.py`다 — 자산 로더가 pydantic settings에 묶이지
    #: 않도록 거기서 환경변수를 직접 본다. 여기 두는 이유는 §2.4 목록의 완결성이다.
    dossier_dir: str | None = None
    #: 기본 `assignments/assignment_v1.json`, 없으면 `assignment_dummy.json`(is_dummy 표시).
    assignment_path: str | None = None

    # --- 팀 시연·CI 구성 (§0.5·§2.0) ---
    dev_mode: bool = False

    @property
    def resolved_database_url(self) -> str:
        """DB URL 분기 지점 (§2.0). 두 방향 모두 **조용한 흘러내림**을 막는다.

        - 운영(DEV_MODE=false)에서 미설정 → 기동 실패. 로컬 파일 DB로 흘러내리면 수집
          데이터가 배포 DB 밖에 쌓인다.
        - 시연(DEV_MODE=true)에서 원격 DB 지정 → **기동 실패**. §0.5는 DEV_MODE를
          "fake LLM + 로컬 DB — 팀 시연 구성"으로 정의한다. 시연·QA 데이터가 배포 DB에
          섞이면 §2.4의 schema 전환 규율(`proto_v2` → `main_v2`)이 무의미해지고,
          fake AI2 산출물이 실참가자 데이터와 같은 테이블에 남는다.
        """
        if self.database_url:
            if self.dev_mode and not is_local_db(self.database_url):
                raise RuntimeError(
                    "DEV_MODE=true인데 DATABASE_URL이 로컬 DB가 아니다 (§0.5 — DEV_MODE는 "
                    "'fake LLM + 로컬 DB' 구성이다). 시연 데이터가 배포 DB로 들어가는 것을 막는다. "
                    "DATABASE_URL을 비우거나(로컬 SQLite로 수렴) DEV_MODE=false로 두어라."
                )
            return self.database_url
        if self.dev_mode:
            return DEV_DATABASE_URL
        raise RuntimeError("DATABASE_URL이 설정되지 않았다 (§2.4). DEV_MODE=true가 아니면 필수다.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
