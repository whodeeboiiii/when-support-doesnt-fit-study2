# CLAUDE.md — study2-enactment

NOT QUITE YES Study 2: 12명 within-participants 2×2 enactment 실험 시스템 (참가자 화면 + 연구자 콘솔).
**유일한 정본은 `docs/구현명세서_v1.0.1.md`다.** 이 파일과 명세서가 충돌하면 명세서가 우선한다.

## 절대 규칙

1. **명세서에 없는 설계 결정을 임의로 내리지 마라.** 결정이 필요하면 구현을 멈추고 질문하거나, 명세서 규약대로 `<TODO: …>` 태그를 남겨라. 특히 `[정본]` 표시 문안(sidecar·평정 12문항·P00 자극)은 **한 글자도 윤문 금지**.
2. **Evidence boundary (명세서 §1.2)는 불변식이다.** AI2 payload = {dossier ai_visible, 해당 branch User1(정규화), normalized referent} 3종뿐. AI1 원문·sidecar·researcher_only·타 branch 산출물·평정·사전설문은 어떤 LLM 호출에도 넣지 않는다. `llm/` 모듈은 `dossier_private`를 import할 수 없다(NT-04).
3. **branch 격리**: AI2 컨텍스트는 branch마다 새로 조립한다. 세션 누적 대화 이력 개념을 만들지 마라(NT-10).
4. **자극·배정 immutability**: condition·자극·문항 순서는 최초 성공 시점에 저장 후 재사용. 새로고침·재접속에서 재추첨·재생성 0건(NT-07·08).
5. **dead-end 금지**: 모든 오류 경로는 §9.1 표의 유효한 다음 상태로 수렴한다. AI2 실패의 종착지는 항상 참가자별 neutral_fallback이다.
6. **판정 코드 금지**: 이 시스템에는 비수용 판정·라우팅·eligible 분류가 존재하지 않는다. 유사 기능을 추가하지 마라.
7. **ID 예약**: C1–C4 = 실험 조건 전용, D-nn = 결정, NT-nn = 테스트, SS##/B# = 상태, P#/R# = 화면.
8. 변수·필드 명명에 `acceptance` 계열 금지(§1.5-10).

## Legacy 참조 규칙 (`../study2_pipeline` — 읽기 전용)

- **이식 대상** (필요 시 열람·복사·개조): `backend/`의 llm_gateway·openrouter_client, notify 모듈, Fernet 암호화·audit 유틸, `scripts/init_db.py`, `tests/fake_llm.py`·`conftest.py`·`helpers.py`, `tests/alpha_runner.py`(fixture 러너로 개조), 자산 로더 + 자산 계약 테스트 패턴, frontend의 채팅·설문·로딩 컴포넌트.
- **참조 금지** (구 설계 오염 방지 — 열지 마라): 상태머신 S00–S20, Stage 0, R1/R2/R3 라우팅, `skeleton_templates/`, bridge 조립, 배정(층화 무작위) 서비스, 모집 자동 종료, blind coding export, S19b, few-shot·알파 fixture 내용물, `prompts/prompt_config_v4.0.json`.
- 처분 근거가 필요하면 명세서 부록 G(상속 매핑표)를 읽어라.

## 자산 원칙

- dossier(P00–P12)·사전설문·normalization 패턴은 **스키마 준수 placeholder**로 개발한다. P00만 실값(부록 A.6). 실값 착지를 기다리며 개발을 막지 마라.
- 자산 착지·변경 커밋은 반드시 자산 계약 테스트(NT-20~23)를 동반한다.
- `dossiers/P01–P12`는 git에 커밋하지 않는다(스키마 더미만 커밋 — §2.9).

## 스택·명령

- backend: FastAPI (Python 3.12+), SQLAlchemy, Supabase Postgres(배포)/SQLite(`DEV_MODE=true`)
- frontend: React 18 + Vite + TypeScript + Tailwind — **데스크톱 전용**(모바일 CSS 작성 금지)
- LLM: OpenRouter — MAIN(AI2)/VALIDATOR(checker) 이원화. `DEV_MODE=true`면 fake_llm 사용, 실키 불필요
- 테스트: `pytest` (NT-01~30 — 부록 C). **커밋마다 전체 green, 기준선 불감소.**
- 로컬 실행: `uvicorn app.main:app` + `npm run build` (정적 서빙) — 시연은 DEV_MODE=true

## 작업 규율

- 스프린트 순서는 명세서 §11.1 (NS1 이식·골격 → NS2 상태머신·화면 → NS3 AI2 파이프라인 → NS4 콘솔·마감). 각 스프린트의 완료 기준 행을 그대로 체크리스트로 써라.
- 스프린트 종료 시 `PROGRESS.md`에 완료 기준 대비 결과·미해결 항목·다음 단계를 기록하라.
- free session, 모바일, 보상 코드 발급, 안전 자동 종료는 **범위 밖**이다(§0.3·E.3). 구현하지 마라.
