"""배포 환경변수 주입 (docs/배포_실행_v1.md §2.3).

    railway login && railway link                  # 먼저 (브라우저 인증)
    python scripts/push_env_to_railway.py "<Supabase URL>"          # 미리보기(기본)
    python scripts/push_env_to_railway.py "<Supabase URL>" --apply  # 실제 주입
    python scripts/push_env_to_railway.py --volume-vars --apply     # 반입 후 2단계

변수를 손으로 14개 옮기면 하나쯤 빠지거나 오타가 난다. 그런데 이 구성에서 변수 하나가
틀리면 증상이 **기동 실패**가 아니라 조용한 오작동일 수 있다 — 예컨대 `FERNET_KEY`가 다르면
서버는 멀쩡히 뜨고 세션도 돌지만 **기존 🔒 데이터만 못 읽는다.** 그래서 목록을 코드에 둔다.

**두 단계로 나눈다.** `DOSSIER_DIR`·`ASSIGNMENT_PATH`는 자산을 볼륨에 올린 **뒤에만** 걸어야
한다 — 먼저 걸면 파일이 없어서 기동이 끊긴다(반입 문서 §2 규칙 3). 그 둘만 `--volume-vars`로
분리했다.

**비밀값은 argv에 싣지 않는다.** `railway variables set KEY --stdin`으로 파이프에 태운다 —
argv는 같은 머신의 다른 프로세스에서 보이고 셸 히스토리에도 남는다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

#: 로컬 `.env`에서 그대로 가져갈 변수. 값이 비면 건너뛴다.
#: `DATABASE_URL`은 여기 없다 — 로컬은 SQLite라 그대로 가져가면 안 된다(인자로 받는다).
FROM_ENV = (
    ("DB_SCHEMA", False),
    ("STUDY_VERSION", False),
    ("MAIN_MODEL_ID", False),
    ("VALIDATOR_MODEL_ID", False),
    ("LLM_CONCURRENCY", False),
    ("AI2_TIMEOUT_MS", False),
    ("CHECKER_TIMEOUT_MS", False),
    ("ADMIN_USER", False),
    ("ADMIN_PASS", True),
    ("OPENROUTER_API_KEY", True),
    ("FERNET_KEY", True),
    ("DISCORD_WEBHOOK_URL", True),
)

#: 반입 이후 2단계에서만 건다.
VOLUME_VARS = (
    ("DOSSIER_DIR", "/data/dossiers"),
    ("ASSIGNMENT_PATH", "/data/assignments/assignment_v1.json"),
)


def read_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        raise SystemExit(f".env가 없다: {ENV_FILE}")
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def mask(value: str) -> str:
    """길이만 보인다. 끝자리 몇 글자라도 터미널 출력·스크린샷에 남기지 않는다 —
    주입 결과 대조는 `railway variables list --kv`로 한다."""
    return f"[설정됨 · {len(value)}자]"


def set_variable(key: str, value: str, *, secret: bool, apply: bool) -> None:
    shown = mask(value) if secret else value
    if secret:
        printed = f"  <값> | railway variables set {key} --stdin --skip-deploys"
    else:
        printed = f"  railway variables set {key}={value} --skip-deploys"
    print(f"{printed}\n      → {key} = {shown}")
    if not apply:
        return
    if secret:
        command = ["railway", "variables", "set", key, "--stdin", "--skip-deploys"]
        result = subprocess.run(command, input=value, text=True, capture_output=True)
    else:
        command = ["railway", "variables", "set", f"{key}={value}", "--skip-deploys"]
        result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        # 오류 메시지에 값이 실릴 수 있으므로 그대로 뿌리지 않는다.
        detail = (result.stderr or result.stdout).strip().replace(value, "<값>")
        raise SystemExit(f"❌ {key} 주입 실패 — {detail[:300]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Railway 환경변수 주입 (§2.3)")
    parser.add_argument("database_url", nargs="?", help="Supabase 연결 URL (1단계에 필수)")
    parser.add_argument("--volume-vars", action="store_true",
                        help="2단계 — 자산 반입 후 DOSSIER_DIR·ASSIGNMENT_PATH만 건다")
    parser.add_argument("--apply", action="store_true", help="실제 주입 (기본은 미리보기)")
    args = parser.parse_args(argv)

    if args.volume_vars:
        print("2단계 — 볼륨 변수 (자산을 이미 올렸어야 한다)\n")
        for key, value in VOLUME_VARS:
            set_variable(key, value, secret=False, apply=args.apply)
        print("\n반입 전이라면 여기서 멈춰라 — 파일이 없으면 기동이 끊긴다(반입 문서 §2 규칙 3).")
    else:
        if not args.database_url:
            raise SystemExit(
                "Supabase 연결 URL이 필요하다 (§2.2 — Session pooler 쪽을 복사한다).\n"
                '  사용: python scripts/push_env_to_railway.py "postgresql://…" [--apply]'
            )
        if args.database_url.startswith("sqlite"):
            raise SystemExit("로컬 SQLite URL이다 — 배포 DB URL을 줘라(§0.5).")
        env = read_env()

        print("1단계 — 로컬 .env에서 가져갈 값 + DB + DEV_MODE\n")
        set_variable("DATABASE_URL", args.database_url, secret=True, apply=args.apply)
        set_variable("DEV_MODE", "false", secret=False, apply=args.apply)
        skipped = []
        for key, secret in FROM_ENV:
            value = env.get(key, "")
            if not value:
                skipped.append(key)
                continue
            set_variable(key, value, secret=secret, apply=args.apply)
        if skipped:
            print(f"\n  건너뜀(.env에 값 없음): {', '.join(skipped)}")
        print("\n  ⚠ FERNET_KEY는 로컬과 같은 값이어야 한다 — 다르면 서버는 정상으로 뜨고")
        print("     기존 🔒 데이터만 못 읽는다(§2.9).")

    if not args.apply:
        print("\n미리보기다 — 아무것도 주입하지 않았다. 실제 주입은 `--apply`.")
    else:
        print("\n✅ 주입 완료. `--skip-deploys`라 배포는 아직 안 걸렸다 — 마지막에 한 번 재배포한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
