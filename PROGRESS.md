# PROGRESS — study2-enactment

정본: `docs/구현명세서_v1.0.1.md`. 이 파일과 명세서가 충돌하면 명세서가 우선한다.

---

## NS1 — 이식·골격 (완료, 2026-08-16)

### 완료 기준 대비 결과

| 기준 (§11.1 NS1 행 + 지시사항) | 결과 | 근거 |
|---|---|---|
| §2.3 폴더 구조로 신 리포 스캐폴드 (pyproject·vite·pytest 설정) | ✅ | `pyproject.toml`, `frontend/{package.json,vite.config.ts,tsconfig.json,tailwind.config.js}`, `[tool.pytest.ini_options]` |
| 구 리포 "이식 대상" 모듈만 이식 (llm_gateway·notify·fernet·audit·fake_llm·conftest·init_db·자산 로더 패턴·frontend 컴포넌트) | ✅ (2건 이월) | 아래 [이식 내역](#이식-내역) |
| dossier 3층 스키마 로더 + P00 실값(부록 A.6) + P01–P12 스키마 더미 | ✅ | `backend/app/assets/dossier_loader.py`, `dossiers/P00.json`, `dossiers/schema_dummy/P01–P12.json` |
| dossier_private 분리 + NT-04 정적 검사 | ✅ | `backend/app/assets/dossier_private.py`, `tests/unit/test_evidence_boundary_static.py` |
| 자산 계약 테스트 (NT-20~23) 통과 | ✅ | `tests/assets/test_dossier_contract.py` — 13 dossier × 4계약 |
| leakage 정적 검사(NT-04) 동작 | ✅ | 직접 import·전이 import·`importlib` 우회 3중 검사 + 검사기 자기검증 |
| `DEV_MODE=true`로 서버 기동 + 자산 검증 통과 | ✅ | `uvicorn app.main:app` 기동 확인, `GET /api/health` 200 (dossier 13건 로드) |
| 테스트 전체 green (기준선) | ✅ | **188 passed** (기준선 = 188. 이후 커밋에서 불감소) |

### 검증 명령

```bash
# 백엔드 (venv: backend/.venv, Python 3.12)
./backend/.venv/bin/python -m pytest -q                 # 188 passed
DEV_MODE=true ./backend/.venv/bin/python scripts/init_db.py   # 14 tables (§8.1)

# 프론트엔드
cd frontend && npm install && npm run build             # dist/ 생성

# 시연 기동 (DEV_MODE — fake LLM + 로컬 SQLite, 실키 불요)
DEV_MODE=true ./backend/.venv/bin/python -m uvicorn app.main:app --port 8000
curl -s localhost:8000/api/health
```

### 구현물

```
backend/app/
  main.py              기동 시 자산 게이트(§5.4) + LLM 클라이언트 주입(§2.0) + dist 정적 서빙
  api/health.py        /api/health (자산 '내용'은 싣지 않는다 — §2.9·NT-13)
  core/config.py       §2.4 환경변수 전 항목 + §0.5 확정 파라미터 기본값
  core/text_metrics.py 문자·문장·질문 계량 (§5.2 stimuli_meta · §6.5 R-3 공용)
  assets/files.py      dossier 파일 위치 해석 (실값 → 스키마 더미)
  assets/dossier_loader.py   ai_visible·derivation 층 + 계약 검증 + 기동 게이트
  assets/dossier_private.py  researcher_only 층 (콘솔 전용 — llm/ import 금지)
  llm/prompts.py       prompt_config 정본 로더 + prompt_hash 정합
  llm/integrity_rules.py     R-3·R-4 (R-1·R-2는 NS3)
  llm/fake_llm.py      DEV_MODE·CI 공용 결정론 클라이언트
  llm/gateway/{client,openrouter_client,calls}.py   호출 단일 관문(동시성·타임아웃·1회 재시도·llm_calls)
  models/{base,tables,session}.py    §8.1 14테이블 + Postgres/SQLite 공통 엔진
  notify/{discord,watch}.py          §2.8 트리거 5종
  security/{fernet,audit}.py         §2.9 암호화 · §8.1 audit_logs
dossiers/P00.json + dossiers/schema_dummy/P01–P12.json
prompts/prompt_config_v1.json        부록 A.1·A.2 전문 + 파라미터 + hash
frontend/src/{App.tsx,main.tsx,index.css,components/{Chat,Likert,Inputs,Loading}.tsx}
scripts/init_db.py
tests/{assets,unit,integration}/
```

### 이식 내역

| 구 리포 | 신 위치 | 개조 |
|---|---|---|
| `llm_gateway/{client,openrouter_client,calls}.py` | `app/llm/gateway/` | 프롬프트 캐싱(`cache_control`) 제거(D-21). CALL_SPECS 10종 → prompt_config 2키(AI2·checker). audit 대상 `audit_logs` → **`llm_calls`**(§8.1). 타임아웃을 `AI2_TIMEOUT_MS`/`CHECKER_TIMEOUT_MS`로 분리 |
| `llm_gateway/allowlist.py` | — | **이식 보류**: 신 allowlist는 §6.2의 3종 입력이라 NS3 `llm/context.py`와 함께 새로 쓴다. 구 프롬프트 키·private 테이블 유도 로직은 신 설계에 대응물이 없다 |
| `notify/{discord,watch}.py` | `app/notify/` | 트리거 7종 → §2.8의 5종. 모집 종료·일일 지출 급증(DB 조회) 폐기, 5xx 누적 신설 |
| `db/crypto.py` | `app/security/fernet.py` | 그대로 |
| `db/audit.py` | `app/security/audit.py` | `audit_logs` 스키마가 §8.1(actor/action/target)로 바뀌어 재작성. 행위 6종 enum |
| `db/{base,session}.py` | `app/models/{base,session}.py` | SQLite 분기 추가(DEV_MODE), JSONB→`JSON().with_variant`, UUID PK |
| `tests/fake_llm.py` | `app/llm/fake_llm.py` | 명세 §2.3대로 앱 패키지로 이동(DEV_MODE 공용). 기본 응답을 AI2·checker 2종으로 교체 |
| `tests/conftest.py` | `tests/conftest.py` | DB를 로컬 Postgres → DEV_MODE SQLite로. 사전 생성 잡 recorder 제거(§2.6 잡 소멸) |
| `scripts/init_db.py` | `scripts/init_db.py` | schema 전환 규율 유지, SQLite 대응 |
| `screens/items.py`·`test_battery_firewall.py` | (패턴만) | 자산 로더 + 자산 계약 테스트 **패턴**만 참고. 구 문항 내용은 반입하지 않음 |
| `frontend/components/{Chat,Likert,Inputs}.tsx`, `screens/Loading.tsx` | `frontend/src/components/` | 데스크톱 전용 개조(D-12): visualViewport 키보드 회피·터치 타깃 44px·sticky 제출 막대 제거. 로딩 문구를 §4.7·§9.1 문안으로 |
| `tests/helpers.py` | — | **NS2로 이월** (구 helpers는 S00–S20 흐름 전용. 신 SS·B 헬퍼는 상태머신과 함께 작성) |
| `tests/alpha_runner.py` | — | **NS3으로 이월** (normalization·integrity fixture가 생기는 시점에 러너로 개조 — §10.1) |

참조 금지 목록(상태머신 S00–S20·Stage 0·라우팅·`skeleton_templates/`·bridge·배정 서비스·모집 자동 종료·blind coding export·S19b·few-shot·알파 fixture 내용물·`prompt_config_v4.0.json`)은 **열지 않았다.**

### 자산 현황

- `dossiers/P00.json` — QA 전용 합성 실값. 부록 A.6의 [정본] 항목(trouble cue, residual uncertainty·question stem, 자극 C1–C4, referent_map)과 부록 A.4의 fallback 예시를 **글자 그대로** 반입. `ai_visible`의 서술문·`researcher_only`·`prohibited_inference` 등 A.6이 문장을 주지 않은 필드는 A.6 서술 범위 안에서 QA 합성으로 작성했다(분석 제외, `is_test=true`).
- `dossiers/schema_dummy/P01–P12.json` — 스키마 준수 더미 12종. 전 필드가 `<TODO: PH-03>` placeholder이면서 NT-20~23을 통과한다(질문 수 계약·stem 동일성·meta 일치·fallback 규칙 통과).
- 파일 배치: **실값은 `dossiers/Pnn.json`, 더미는 `dossiers/schema_dummy/Pnn.json`.** 로더는 실값 → 더미 순으로 찾고 더미로 내려가면 `is_dummy=True`로 표시한다. `.gitignore`가 `dossiers/P01–P12.json`(실값 자리)만 제외하므로 §2.9의 "P00·스키마 더미만 커밋"이 성립한다. 반입 절차는 여전히 `<TODO: PH-04>`.
- `prompts/prompt_config_v1.json` — 부록 A.1·A.2 전문 + 파라미터(0.4/800, 0.0/json_object) + `prompt_hash`. 문안을 고치고 hash를 안 고치면 기동이 실패한다.

### 테스트 ↔ 부록 C 매핑 (NS1 착지분)

| NT | 위치 | 비고 |
|---|---|---|
| NT-04 | `tests/unit/test_evidence_boundary_static.py` | 직접·전이·`importlib` 우회 + 검사기 자기검증 |
| NT-20 | `tests/assets/test_dossier_contract.py`, `tests/unit/test_dossier_gate.py` | 스키마 전수·layer 분리·referent_map 형식 + **기동 게이트가 실제로 끊는지** |
| NT-21 | `tests/assets/test_dossier_contract.py` | 전 dossier fallback이 R-3·R-4 통과 |
| NT-22 | 〃 | C1·C3 질문 0 / C2·C4 질문 1 + stem 동일 |
| NT-23 | 〃 | stimuli_meta ↔ 원문 계량 일치 |
| (부록 D.1 문안 대조) | `tests/assets/test_p00_canonical_text.py` | P00 [정본] 문안이 명세서 원문과 글자 단위 일치 (윤문 0건) |
| (NT-28 전제) | `tests/integration/test_models_smoke.py` | 🔒 필드 평문 미저장 확인 |
| (NT-15 전제) | `tests/integration/test_boot_and_gateway.py` | 호출 1건 = `llm_calls` 1행, 재시도 동일 request id |

`tests/unit/test_dossier_layers.py`는 로더 출력에 researcher_only 문자열이 섞이지 않음을 런타임에서 확인한다(NT-04의 짝).

---

## NS2 — 상태머신·화면 (완료, 2026-08-16)

### 완료 기준 대비 결과

| 기준 (§11.1 NS2 행) | 결과 | 근거 |
|---|---|---|
| SS·B 상태머신 | ✅ | `core/state_machine.py` — SS00–SS07·SS90/91 × B0–B7, 전이표에 역방향 간선 0건 |
| Williams 매핑 | ✅ | `core/williams.py` — §3.3 표 + `(P번호−1) mod 4 + 1`. 배정 로직은 이 파일이 유일 |
| P0–P11 화면 + 저장 | ✅ | `frontend/src/screens/` 4파일 12화면 + `api/participant.py`·`api/branch.py` |
| idempotency·복구 | ✅ | `core/idempotency.py` (별도 테이블 없이 상태 순위로 판정) — NT-08·09 |
| 사전설문 로더 | ✅ | `assets/presurvey.py` + `fixtures/presurvey_items_v0.json`(placeholder, PH-01) |
| **NT-06** Williams 표·순환 매핑 | ✅ | `tests/unit/test_williams.py` — 위치별 조건 1회 + adjacent pair 12종 각 1회 |
| **NT-07** condition·stimulus_hash 불변 | ✅ | `tests/integration/test_session_flow.py` — 재진입·새로고침 반복 후 동일, ai1 turn 1건 |
| **NT-08** 새로고침·재접속 복구 | ✅ | 자극 재추첨 0건·AI2 재생성 0건·문항 순서 동일, 쿠키 삭제 후 재접속 복원 |
| **NT-09** 중복 제출 idempotency | ✅ | 세션 4단계·branch 5단계 전부 200 + 기존 레코드(행 증가 0) |
| **NT-12** 참가자당 완료 세션 1개 | ✅ | `POST /admin/sessions` 409 (P00은 무제한) |
| **NT-14** 비합법 전이 거부 | ✅ | 규칙 층 `tests/unit/test_state_machine.py` + API 층 409 8종 |
| 문안 [정본] 초안 대조 | ✅ | `tests/assets/test_screen_copy_canonical.py` — sidecar 2변형·평정 12문항을 §7.3 표 행 단위로 대조 |
| 테스트 전체 green | ✅ | **400 passed** (기준선 188 → 400. 불감소) |

**DEV_MODE DB 가드 (승인 2026-08-16)**: `DEV_MODE=true`인데 `DATABASE_URL`이 로컬 SQLite가 아니면 **기동을 차단**한다(`core/config.py` + `main.validate_runtime_config()`). 근거는 §0.5의 DEV_MODE 정의 자체다 — "fake LLM + 로컬 DB — 팀 시연 구성". 첫 요청까지 미루지 않고 기동 시점에 보는 이유는, 그때 실패해야 서버가 "정상"으로 보이지 않기 때문이다. 검사는 `tests/unit/test_config.py`(오류 문안에 자격증명 미포함 포함).

추가로 착지한 부록 C 항목: **NT-05**(사전설문 메타키 미노출), **NT-17**(no_reply/end에 AI2·downstream 부재), **NT-18**(2블록·블록 내 무작위·block/display_order 저장·합산 부재), **NT-27**(코드 TTL·재발급 동일 세션 바인딩), **NT-29**(렌더 beacon→제출 이벤트 쌍), **NT-19·NT-13 부분**(아래 한계 참조).

### 시연 확인 (DEV_MODE, 실제 서버)

`uvicorn` + `curl`로 P00 세션을 SS00→SS07 완주했다(§11.3 Definition of Done 1행).

- 종결 유형 조합: branch1 `reply` · branch2 `no_reply` · branch3 `reply` · branch4 `end`
- 저장 결과: branches 4(조건 **C4·C1·C3·C2** = P00의 S4 행) · ratings 48 · sidecar 4 · generations 2 · downstream 2 · presurvey 12 · audit 2
- no_reply branch에서 `POST /ai2`·`POST /downstream` → **409** (NT-17)
- P10 payload에 조건 라벨(C1–C4·uptake·elicitation) 0건, sidecar 0건
- SQLite 파일을 바이트로 뒤져 User1·sidecar·AI2 평문 **0건**(§2.9)

```bash
DEV_MODE=true DATABASE_URL="sqlite+aiosqlite:///./dev_local.db" \
  ADMIN_USER=demo ADMIN_PASS=demo-pass FERNET_KEY=<키> \
  ./backend/.venv/bin/python scripts/init_db.py
DEV_MODE=true … ./backend/.venv/bin/python -m uvicorn app.main:app --port 8000 --app-dir backend
curl -u demo:demo-pass -X POST localhost:8000/admin/sessions -H 'Content-Type: application/json' -d '{"participant_no":"P00"}'
```

### 구현물 (NS2 추가분)

```
backend/app/
  core/williams.py           §3.3 결정론 배정 (이 파일이 배정의 전부)
  core/state_machine.py      SS·B 전이표 + 화면 매핑 (§3.1·§3.2)
  core/idempotency.py        제출 단위 재제출 판정 (§3.5 — 별도 테이블 없음)
  core/randomization.py      시드 고정 순서 (§4.9 블록 내 무작위 + NT-08 불변)
  core/access_code.py        6자리 코드·TTL 24h·실패 지연 (§2.5·§4.0)
  security/tokens.py         세션 토큰 서명 (§2.5 httpOnly 쿠키)
  assets/screen_copy.py      §4·§9.1 화면 문안 ([정본]·[제안] 구분 주석)
  assets/rating_items.py     §7.3 평정 12문항 [정본] + 2블록 제시 순서
  assets/presurvey.py        §4.2 자산 로더 + 참가자 payload allowlist (NT-05)
  api/deps.py                세션 쿠키·Basic auth (§2.7)
  api/store.py               저장 상태 조회 헬퍼
  api/state_payload.py       GET /state 화면 payload 조립
  api/participant.py         §8.2 세션 수준 + beacon
  api/branch.py              §8.2 branch 수준 (§3.2 인과 창)
  api/admin.py               세션 생성·코드 재발급 (NS4 콘솔의 최소 선행분)
  llm/ai2_pipeline.py        **NS2 이음매** — §9.1 종착지(neutral_fallback)로 수렴
fixtures/presurvey_items_v0.json   PH-01 placeholder (12문항·4섹션)
frontend/src/{api.ts,copy.ts,App.tsx,screens/{common,Join,Intro,Branch,Wrap}.tsx}
tests/{helpers.py,unit/{test_williams,test_state_machine,test_access_code}.py,
       assets/{test_presurvey_contract,test_screen_copy_canonical,test_frontend_contract}.py,
       integration/{test_session_flow,test_events}.py}
```

### 설계 메모 (읽는 사람이 헷갈릴 지점)

- **AI2는 아직 없다.** `llm/ai2_pipeline.py`는 §6 파이프라인 대신 참가자별 `neutral_fallback`을 돌려준다. 빈 자리를 두지 않은 이유는 §9.1의 dead-end 금지이고, 그 결과 시연 중 P7에 뜨는 문안은 fallback이며 `generations.fallback_used=true`·§2.8 알림으로 **사실 그대로** 기록된다. NS3이 이 함수만 교체한다.
- **화면 문안이 서버에 있다.** [정본] 대조를 기계가 하려면 한 곳에 있어야 한다(`assets/screen_copy.py`). 프런트엔드에는 세션 없이 필요한 문안(P0·데스크톱 가드)과 이동 버튼 라벨만 남겼다(`frontend/src/copy.ts`).
- **문항 ID가 클라이언트로 가지 않는다.** 사전설문(§4.2 규칙)과 평정(변수명 = 구성개념 라벨) 모두 **위치**로만 오간다. 위치 → 문항 ID 매핑은 서버에만 있다.
- **평정 순서는 저장하지 않고 시드로 재현한다.** §8.1에 순서 테이블이 없어서다. 시드는 세션 UUID + branch + block이고, 제출 시점에 `ratings.display_order`로 남는다.

---

## NS3 — AI2 파이프라인 (완료, 2026-08-16)

### 완료 기준 대비 결과

| 기준 (§11.1 NS3 행) | 결과 | 근거 |
|---|---|---|
| normalization | ✅ | `llm/normalization.py` + `fixtures/normalization_patterns_v1.json`(부록 A.3) |
| 규칙 검사 | ✅ | `llm/integrity_rules.py` — R-1·R-2 추가(R-3·R-4는 NS1) |
| checker | ✅ | `llm/checker.py` — 부록 A.2 3유형, 판정 불능은 `checker_skipped` |
| 재생성·fallback | ✅ | `llm/ai2_pipeline.py` — 위반 → 재생성 1회 → `neutral_fallback` |
| audit | ✅ | `generations` 행/시도 + `llm_calls` 1행/호출 (§8.4) |
| DEV_MODE | ✅ | fake LLM에 fixture 트리거 추가(부록 A.5) — 위반 경로를 실호출 없이 재현 |
| fixture 러너 | ✅ | `tests/fixture_runner.py`(구 alpha_runner 개조) + `scripts/run_fixtures.py` |
| **NT-01** AI2 payload 불포함 | ✅ | `tests/integration/test_evidence_boundary.py` — sentinel 주입 후 전 호출 전문 검사 |
| **NT-02** checker payload 허용 입력 외 불포함 | ✅ | 〃 (허용 4종은 **실제로 들어가는지**도 확인) |
| **NT-03** normalization 입력 한정 | ✅ | `tests/unit/test_normalization.py` — 시그니처·import·조건 비의존 |
| **NT-10** branch 격리 | ✅ | 4-branch 연속 fixture — 한 payload에 두 branch 발화 0회, payload 길이 비증가 |
| **NT-11** 전 조건 동일 + 저장 | ✅ | 네 조건에서 동일 판정, raw/normalized/matched_pattern/referent 저장 |
| **NT-15** audit 재구성 | ✅ | `reconstruct_path()`가 generations·llm_calls만으로 {정상\|재생성\|fallback} 복원 |
| fixture 결정론부 100% | ✅ | NT-24 normalization 12건 100%, NT-25 규칙 계층 12건 100% |
| 테스트 전체 green | ✅ | **444 passed** (기준선 188 → 400 → 444. 불감소) |

추가로 착지: **NT-16**(sidecar 제출 전 AI2 호출 0건 — 상태·저장물 양쪽으로 확인), **NT-24·NT-25**, §9.1의 세 오류 경로(AI2 호출 실패 · checker 실패 · 재생성 후 위반) 전부 표시 가능한 텍스트로 수렴.

### 검증 명령

```bash
./backend/.venv/bin/python -m pytest -q                    # 444 passed
DEV_MODE=true ./backend/.venv/bin/python scripts/run_fixtures.py --out reports/fixtures.md
#   normalization A/B/C = 100%, integrity R/C = 100% → 게이트 통과
```

### 실서버 확인 (DEV_MODE)

P00 세션에서 `응 그렇게 해줘` 제출 → 정규화 → AI2 → checker까지 실경로로 확인했다.

- `normalizations`: `applied=1, NP-01, R-01` — 지시 대상이 `두 선택지의 장단점을 더 정리해줘`로 복원
- `generations`: 1행(`attempt=1, final=1, fallback_used=0, rule_violations=[]`, checker 판정 전문 저장)
- `llm_calls`: `main ok` + `validator ok` 2행 (prompt_hash·파라미터·자산 버전 포함)
- SQLite 파일 바이트 검사 — User1·sidecar·AI2 평문 **0건**

### 구현물 (NS3 추가분)

```
backend/app/llm/
  normalization.py     §6.4 지시 복원 — 입력 {user1, referent_map, patterns}뿐 (NT-03)
  context.py           §6.2 allowlist 강제 지점 — AiVisible + 문자열만 받는다 (NT-01·NT-02)
  checker.py           §6.5 LLM checker — 판정 불능은 checker_skipped로 흡수 (§9.1)
  integrity_rules.py   R-1·R-2 추가 (대조 문자열은 호출부가 넘긴다 — NT-04)
  ai2_pipeline.py      §6.1 사다리 — 생성 → 규칙 → checker → 재생성 1회 → fallback
  fake_llm.py          부록 A.5 fixture 트리거 + 규칙표 기반 결정론 checker
backend/app/api/leakage_sources.py   R-1·R-2 대조 문자열 수집 (llm/ 밖에 두는 이유는 NT-04)
fixtures/normalization_patterns_v1.json   부록 A.3 패턴 목록 (PH-05)
fixtures/normalization_fixture_v1.jsonl   §10.1 케이스 12건 (치환·다의·무매칭·부분 인용)
fixtures/integrity_fixture_v1.jsonl       §10.1 케이스 16건 (R-1–R-4 + checker 3유형 + 정상)
tests/fixture_runner.py · scripts/run_fixtures.py
tests/{unit/test_normalization.py, integration/{test_evidence_boundary,test_ai2_pipeline,test_fixture_runner}.py}
```

### 설계 메모 (읽는 사람이 헷갈릴 지점)

- **R-2를 문자 그대로 적용하면 정상 세션이 깨진다.** 참가자가 두 branch에서 같은 말을 하면 이번 branch의 정상 응답이 "타 branch User1 문자열"로 걸리고, 재생성해도 같은 이유로 걸려 fallback으로 떨어진다. 그래서 두 가지를 좁혔다: ① 이번 호출의 payload에 이미 있는 문자열은 대조에서 뺀다 ② 타 branch **AI2**는 전문 일치로만 보고(같은 정책·같은 dossier에서 나온 문구 겹침은 격리 실패가 아니다), 그 branch의 User1이 이번과 같으면 대조에서 제외한다. 이 조정이 없으면 fallback이 예외 경로가 아니라 상시 경로가 된다.
- **규칙 위반이 이미 있으면 checker를 부르지 않는다.** 판정 결과(재생성)가 같고 §6.1의 시간 예산을 아낀다. 기록에서는 `rule_violations`가 비어 있지 않고 `checker_result=null`인 상태로 구분된다.
- **fallback은 별도 `generations` 행**이다(마지막 시도 번호 + `fallback_used=true`). 기각된 초안 원문을 fallback 문안으로 덮어쓰지 않기 위해서다 — 초안이 남아야 "무엇이 왜 기각됐는지"를 보고할 수 있다.
- **프롬프트는 정책(system)과 자료(user)로 나눠 보낸다.** 이어 붙이면 부록 A.1 전문 그대로다 — 문안은 그대로 두고 채팅 API의 role 구분만 따른다.
- **재생성 피드백에는 위반 유형만 싣는다.** span에는 sidecar·researcher_only 문자열이 들어 있을 수 있어서, 그대로 돌려보내면 그 자체가 §1.2 위반이다.

---

## NS4 — 콘솔·마감 (완료, 2026-08-16)

### 완료 기준 대비 결과

| 기준 (§11.1 NS4 행) | 결과 | 근거 |
|---|---|---|
| R1 세션 관리 | ✅ | `GET /admin/participants`(참가자·sequence·dossier lock·세션 일람·모집 게이트) + 세션 생성·코드 재발급·SS91 버튼 + `GET /admin/costs`(§2.8 usage 합산) |
| R2 라이브 모니터 | ✅ | `GET /admin/monitor/{id}` — SS·B·화면, transcript(복호화), 이벤트 스트림, **AI2 파이프라인 상태**(generating/clean/regenerated/fallback), 3s 폴링 |
| R3 review 뷰 | ✅ | `GET /admin/review/{id}` — P10과 같은 4열 + sidecar·평정·flag·researcher_only |
| R4 dossier·자극 뷰어 | ✅ | `GET /admin/dossier/{pno}` — 3층·AI1 4종·fallback·referent_map·hash·lock (읽기 전용, 쓰기 경로 0건) |
| notify | ✅ | §2.8 5종 전부 발화 경로 확보 — abort 트리거 신설 + 5xx 누적 미들웨어(`main.py`) 배선 |
| export 스크립트 | ✅ | `analysis/export_trajectory.py`(participant × condition trajectory) + `analysis/tagging_flags.py`(first-opportunity·carryover) |
| QA 워크스루 (부록 D.1 리허설) | ✅ | `tests/qa_rehearsal.py` + `scripts/run_qa_rehearsal.py` — 자동 22건 통과·수동 2건·실패 0건 |
| soft launch 준비 | ✅ | `backend/app/core/freeze.py` + `scripts/freeze_study_version.py` — §11.3 모집 게이트 점검 + §10.5 `study_version` 1회 동결 |
| **NT-26** flag non-blocking·abort만 SS90·전 콘솔 행위 audit | ✅ | `tests/integration/test_console.py` — flag 전후 상태 동일, abort→SS90+참가자 안내, 엔드포인트 9종 호출마다 audit 증가 |
| **NT-28** 🔒 평문 저장 0건·복호화 audit | ✅ | `tests/integration/test_encryption_audit.py` — 전 테이블 덤프 훑기 + Fernet 토큰 검사 + 복호화 지점 **정적 열거**(4곳) |
| **NT-30** export 비식별·자유 텍스트 opt-in 분리·태깅 플래그 열 | ✅ | `tests/integration/test_export.py` — 기본 실행 전 파일에 문장 0건, `--include-text`만 `free_text.csv` 생성 |
| **NT-13** 번들 비밀 0건 실측 | ✅ | 빌드 산출물 대상 검사 + 콘솔 페이지 분리 검사 (`tests/assets/test_frontend_contract.py`) |
| 부록 D.1 리허설 완료 | ✅ | 아래 [리허설 결과](#부록-d1-리허설-결과) |
| Definition of Done 전 항목 (§11.3) | ✅ 10/11 | 마지막 줄(PH-IRB·PH-03 착지 전 모집 금지)은 **자산·IRB 착지 대기** — 게이트 점검은 구현됨 |
| 테스트 전체 green | ✅ | **508 passed** (기준선 188 → 400 → 444 → 508. 불감소) |

### 검증 명령

```bash
./backend/.venv/bin/python -m pytest -q                          # 508 passed
DEV_MODE=true ./backend/.venv/bin/python scripts/run_qa_rehearsal.py --out reports/qa_rehearsal.md
DEV_MODE=true ./backend/.venv/bin/python scripts/freeze_study_version.py --check   # 모집 게이트
DEV_MODE=true ./backend/.venv/bin/python analysis/export_trajectory.py --actor <이름> --out exports/
#   자유 텍스트가 필요하면 --include-text (free_text.csv 분리 생성) · --coding <csv>로 carryover 플래그
```

콘솔은 `http://localhost:8000/admin/console` (Basic auth — `ADMIN_USER`/`ADMIN_PASS`).

### 부록 D.1 리허설 결과

자동 22건 통과 · 수동 2건 · 실패 0건.

| D.1 체크리스트 행 | 확인 방식 |
|---|---|
| 4 branch × 종결 3종 | reply×2 · no_reply×1 · end×1, 조건 C1–C4 전수, SS00→SS07 완주 |
| 새로고침·재접속·코드 재발급·중복 제출·flag·abort 각 1회 | 항목 D1-2a~2g (SS91 처리 포함) |
| DEV_MODE·실모델 각 1회 | DEV_MODE ✅ / **실모델은 수동** — `scripts/run_fixtures.py --real` + [확인 4] 비용 기록 |
| R1–R4 전 기능, notify 5종 발화 | 엔드포인트 6종 200 + 5종 발화 확인(2종은 감시 함수 직접 호출) |
| 문안 [정본] 초안 대조 | [정본] 4항목·[제안] 20항목 명세서 원문 일치 (윤문 0건) |

수동으로 남은 2건: **실모델 1회**(실키·비용), **렌더 수준 확인**(NT-19 — JS 러너 미도입).

### 실서버 확인 (DEV_MODE)

P00 세션을 실서버(`localhost:8000`)에서 끝까지 돌려 콘솔 경로를 확인했다.

- R2: `SS04/P7`, branch 1 = `C4 · clean`, transcript 3턴(ai1·user1·ai2) 복호화 표시
- flag 후 참가자 화면 `P7` 그대로 — 상태 불변(D-07)
- R3: sidecar·flag 사유 표시, abort 후 참가자 화면 = 중단 안내 문안
- `GET /costs`: main 2건 / validator 2건 usage 합산
- SQLite 파일 바이트 검사 — User1·sidecar·flag 사유·중단 사유 평문 **0건**, `audit_logs` view 9 · decrypt 4 · flag 1 · abort 1 · code_issue 4

### 구현물 (NS4 추가분)

```
backend/app/api/
  admin.py             R1 목록·비용 + flag(non-blocking)·abort(SS90)·dropout(SS91) + 모집 게이트 표시
  admin_views.py       R2 모니터 · R3 review · R4 dossier (복호화 지점 ① — 요청 단위 audit)
  console.py           `/admin/console` 정적 콘솔 서빙 (Basic auth)
backend/app/core/freeze.py     §11.3 모집 게이트 점검 + §10.5 study_version 1회 동결
backend/app/main.py            5xx 누적 알림 미들웨어(§2.8) + NS4 라우터 배선
frontend/console/index.html    R1–R4 콘솔 1장 (빌드 없음 — 참가자 번들과 분리)
analysis/export_trajectory.py  participant × condition trajectory + 4개 부속 표
analysis/tagging_flags.py      first_opportunity(기계) · carryover_sensitive(코딩 입력)
scripts/{run_qa_rehearsal,freeze_study_version}.py
tests/qa_rehearsal.py
tests/{integration/{test_console,test_export,test_encryption_audit,test_freeze,test_qa_rehearsal}.py,
       unit/test_tagging_flags.py}
```

### 설계 메모 (읽는 사람이 헷갈릴 지점)

- **콘솔은 참가자 SPA에 넣지 않았다.** 빌드 없는 정적 HTML 1장을 Basic auth 뒤에서 서빙한다. 한 번들이면 조건 라벨·researcher_only·sidecar를 다루는 코드가 참가자 번들에 실릴 수 있는 경로가 생기고(NT-13), 세션 중 콘솔 수정이 참가자 번들 재빌드를 요구한다.
- **R3는 P10 조립기를 재사용하지 않는다.** 참가자 화면은 sidecar를 **빼야** 하고(PH-02) 연구자 화면은 **넣어야** 한다. 같은 함수에 플래그를 달면 언젠가 참가자 쪽에서 그 플래그가 켜진다.
- **복호화 audit은 값 단위가 아니라 요청 단위**다. 한 화면이 40개 필드를 복호화한다고 40행을 남기면 접근 이력이 잡음이 된다. 남기는 것은 "누가 언제 무엇을 열었는가"뿐이고 값은 audit에 옮겨 적지 않는다.
- **AI2 파이프라인 상태는 저장하지 않고 `generations`에서 읽는다.** 표시용 상태 컬럼을 만들면 그 값이 §8.4 audit과 어긋날 수 있다. 재구성의 정본은 언제나 generations다(NT-15).
- **`carryover_sensitive`는 코딩 없이는 빈 칸이다.** "실질 동일 내용이 이전 branch에서 표현됐는가"는 사람의 판정이고(§7.6), 문자열 유사도로 대신하면 그 오차가 결과 변수(disposition·downstream)와 상관된다. 빈 칸은 "아니오"가 아니다.
- **기본 export는 복호화하되 텍스트를 쓰지 않는다.** §7.4가 요구하는 텍스트 **길이**를 내려면 복호화가 필요하다. 그래서 `--include-text`는 "복호화 여부"가 아니라 "문장을 파일에 쓰는지"의 스위치이고, audit `decrypt`는 두 경우 모두 남는다.
- **모집 게이트는 표시만 한다.** PH-03·PH-IRB 미착지 상태에서도 세션 생성은 된다(P00 리허설이 막히면 안 된다). 시작 여부는 연구자가 정한다 — 시스템이 판정하지 않는다는 D-10과 같은 태도다.

---

## 확인 필요 (NS4) — 명세서에 없어 내가 정한 사항

| # | 정한 것 | 명세서 상태 | 반려 시 비용 |
|---|---|---|---|
| ① | **연구자 콘솔을 빌드 없는 정적 HTML 1장으로** 분리(`frontend/console/index.html`) | §2.1은 Participant UI만 React로 지정, §2.0 다이어그램은 콘솔을 FastAPI 쪽에 그린다 | 낮음 (React로 옮기려면 두 번째 진입점 필요) |
| ② | `GET /admin/participants`·`GET /admin/console` 신설 | §8.2 표에 없음. §4.12 R1 화면이 요구 | 낮음 |
| ③ | 복호화 audit을 **요청 단위 1행**으로 | §2.9는 "복호화 조회는 audit 기록"만 | 낮음 (값 단위로 바꾸면 audit 폭증) |
| ④ | R2 모니터가 매 폴링(3s)마다 audit 2행을 남긴다 | §2.7은 "모든 콘솔 조회" 기록만 | 중간 — 3s 폴링이면 세션 1건에 수백 행. 화면 열람 세션 단위로 묶는 대안 있음 |
| ⑤ | AI2 상태 라벨 5종(`generating`/`pending`/`clean`/`regenerated`/`fallback`) | §4.12는 "생성 중/재생성/fallback" 3종 | 낮음 |
| ⑥ | `events.type` 3종 신설(`researcher_flag`·`researcher_abort`·`researcher_dropout`) | §8.1은 "beacon·flag(사유🔒)·abort"라고만 | 낮음 |
| ⑦ | dropout은 **알림 없음** | §2.8 표에 트리거가 없다(abort만 있음) | 낮음 |
| ⑧ | dropout에는 사유를 받지 않는다 | §8.2 `POST /dropout`에 body 미지정 | 낮음 |
| ⑨ | export 파일 5종 분할(trajectory·ratings·presurvey·generation_integrity·events) + opt-in `free_text` | §7.6은 "플래그 열로 제공"만 | 낮음 |
| ⑩ | 기본 export도 복호화한다(텍스트 길이 — §7.4). opt-in은 **파일 기록** 스위치 | §2.9·NT-30은 열 분리만 요구 | 낮음 |
| ⑪ | `first_opportunity = (branch_index == 1)` | §7.6은 "각 branch가 첫 표현 기회였는지 기록" | 낮음 — 같은 사건 4회 반복이므로 기계적으로 결정된다 |
| ⑫ | `carryover_sensitive`는 코딩 CSV가 있을 때만 산출, 없으면 빈 칸 | §7.6은 산출 방법을 지정하지 않음 | 중간 — 자동 추정을 원하면 유사도 판정 규칙을 명세해야 한다 |
| ⑬ | export에서 `events.payload.user_agent` 제거 | §4.0은 저장을 지시, §7.6은 비식별 요구 | 낮음 |
| ⑭ | `study_version` 동결은 **스크립트 전용**(콘솔 버튼 없음) | §10.5는 주체·수단 미지정 | 낮음 |
| ⑮ | 모집 게이트 판정 항목 4종(PH-03·PH-IRB-1·2·PH-01) | §11.3은 "PH-IRB 계열·PH-03"만 명시 (PH-01은 내가 추가) | 낮음 |
| ⑯ | notify 5종 중 2종(provider 문자열 변경·5xx 누적)은 리허설에서 **감시 함수 직접 호출**로 확인 | 부록 D.1은 "notify 5종 발화 확인" | 낮음 — 세션 조작으로는 만들 수 없는 사건이다 |
| ⑰ | 서버 5xx 알림을 **미들웨어**에서 센다 | §2.8은 트리거만 지정 | 낮음 |

**NS3 ⑬의 후속**: 복호화 지점이 실제로는 4곳이다(콘솔·export·R-1/R-2 대조·AI2 payload용 정규화본 읽기). `tests/integration/test_encryption_audit.py`가 이 넷을 **정적으로 열거**하므로, 다섯 번째가 생기면 테스트가 먼저 깨진다. §2.9 문면("복호화 지점 2곳")과의 정합은 PI 확인 사항으로 남긴다.

---

## 확인 필요 (NS3) — 명세서에 없어 내가 정한 사항

| # | 정한 것 | 명세서 상태 | 반려 시 비용 |
|---|---|---|---|
| ① | **R-2 대조 정밀화 2건**(위 설계 메모) | §6.5는 "타 branch User1/AI2 문자열의 등장"만 | 중간 — 되돌리면 정상 세션이 fallback으로 떨어진다 |
| ② | 규칙 위반 시 checker 생략 | §6.1은 [4]→[5] 순서만 | 낮음 (항상 호출로 바꾸면 최악 경로 +45s) |
| ③ | fallback을 별도 `generations` 행으로 | §8.1은 `attempt(1/2)`만 | 낮음 |
| ④ | 누출 대조 최소 길이 8자 | §6.5는 "필드 값 문자열 대조" | 낮음 [파일럿 확정 태그] |
| ⑤ | `{ai_visible_context}` 렌더 형식(항목별 라벨 5줄) | 부록 A.1은 자리만 지정 | 낮음 |
| ⑥ | `trouble_cue.form`(explicit/mitigated/…)을 payload에서 제외 | §6.2는 "ai_visible layer(checkpoint 정보)" | 낮음 — 연구자 코딩 라벨이라 제외했다 |
| ⑦ | 프롬프트를 system/user로 분할 | 부록 A.1은 한 덩어리 | 낮음 (이어 붙이면 원문 동일) |
| ⑧ | `referent_id` 형식 `R-01` / `R-01+R-02`, 병기 연결자 `, ` | §5.2에 id 필드 없음, §8.1은 값을 요구 | 낮음 |
| ⑨ | 재생성 안내 문안 [제안] | §6.5는 "위반 유형 피드백 포함"만 | 낮음 |
| ⑩ | A.3 패턴의 정규식화(공백 유연) + 패턴 자산 버전 교차 검증 | 부록 A.3은 "정규식 취지" | 낮음 `<TODO: PH-05>` |
| ⑪ | checker 판정에서 `violations`를 `pass`보다 권위로 | 부록 A.2는 둘 다 출력 | 낮음 |
| ⑫ | checker 판정 불능을 **통과**로 취급 | §9.1은 "규칙 계층만으로 판정"이라고만 | 낮음 |
| ⑬ | `leakage_sources`의 복호화 | §2.9는 복호화 지점 2곳(콘솔·export) | 중간 — R-1·R-2가 평문 대조를 요구하므로 규칙 자체가 세 번째 지점을 만든다 |
| ⑭ | fake LLM fixture 트리거 토큰 `[[fixture:…]]` | 부록 A.5는 "트리거 문자열"만 | 낮음 |

---

## 확인 필요 (NS2) — 명세서에 없어 내가 정한 사항

NS2에서 명세서가 값을 고정하지 않은 지점이다. **①–③이 연구 의미와 닿아 있고 나머지는 구현 관례**다. 전부 되돌리기 쉬운 상태다.

| # | 정한 것 | 명세서 상태 | 반려 시 비용 |
|---|---|---|---|
| ① | **참가자 화면에 문항 ID 대신 위치를 내린다** — 평정 12문항에도 적용 | §4.2는 사전설문에만 명시(NT-05). 평정은 무언급 | 낮음 (payload 형태만 변경) |
| ② | **평정 제시 순서를 저장하지 않고 시드로 재현** | §8.1에 순서 테이블 없음, §3.5는 "순서 재추첨 없음"만 요구 | 중간 (저장 방식으로 바꾸면 테이블 1개 추가) |
| ③ | **NS2의 P7은 neutral_fallback을 표시**한다 | §11.1이 AI2를 NS3으로 배치 | 없음 (NS3에서 교체 예정) |
| ④ | 세션 토큰 = HMAC 서명한 세션 id (비밀은 `FERNET_KEY` 파생) | §2.5는 "서버 세션 토큰(httpOnly cookie)"만 지정 | 낮음 |
| ⑤ | `POST /api/events` beacon 엔드포인트 신설 | §8.2 표에 없음. §2.11·§7.5·NT-29가 요구 | 낮음 |
| ⑥ | `POST /advance` body = `{from_screen}` | §8.2는 body 미지정 | 낮음 |
| ⑦ | `checkpoint_viewed_at`·`debrief_confirmed_at`·`user_agent`·`viewport`를 `events` 행으로 저장 | §4.0·§4.3·§4.11이 저장을 지시하지만 §8.1 표에 열이 없음 | 낮음 (열 추가 시 마이그레이션) |
| ⑧ | 동의 항목 키 5종(`participation`·`study1_data_use`·`recording`·`overseas_transfer`·`withdrawal_and_compensation`) | §4.1 필수 포함 항목 ①–⑤의 구조만 확정, 문안은 `<TODO: PH-IRB-1>` | 낮음 |
| ⑨ | 사전설문 스키마 초판 — 12문항·4섹션·유형 3종(single/multi/likert_1_7) | §4.2 구성 ①–④만 서술, 원문은 `<TODO: PH-01>` | 낮음 |
| ⑩ | 세션 생성 차단 조건 = 해당 참가자에 `active`·`done` 세션 존재 (P00 예외) | §2.5·NT-12는 "완료 세션 1개"만 | 낮음 (재시작하려면 NS4의 abort/dropout 필요) |
| ⑪ | sidecar "있음"에서 free_text·relevance **필수**, reason 선택 | §4.6은 세 입력을 나열만 | 낮음 |
| ⑫ | downstream 7선택은 **명세서 표 순서 고정**(무작위 아님) | §4.8은 "표시 순서" 저장만 지시. 무작위는 §7.3 평정의 규칙(D-13) | 낮음 |
| ⑬ | 접속 코드 해시에 참가자 번호 결합, 실패 지연은 번호 단위 프로세스 메모리 | §2.5·§4.0은 해시 방식·카운터 위치 미지정 | 낮음 |
| ⑭ | P10에서 **참가자 본인** 텍스트를 복호화해 표시 | §2.9는 "복호화 지점 2곳(콘솔·export)", §4.10은 4 trajectory 재표시 요구 — 문면상 긴장 | 중간 (금지하면 §4.10 재표시 불가) |
| ⑮ | UI 이동 라벨(`계속하기`·`시작`·`제출하기`·`시작하기`·종료 안내) | §4에 라벨 없음 | 낮음 |

**한계로 남긴 것**

- **NT-19(데스크톱 가드)는 정적 검사만** 걸었다 — 임계값 1024·문안 일치·가드가 화면 선택보다 앞이라는 것까지 본다. 렌더 동작 검증에는 JS 테스트 러너가 필요한데 이 리포의 테스트는 pytest다(CLAUDE.md). **vitest 도입 여부는 결정 사항**이다. 현재는 §10.2 QA 워크스루에서 사람이 확인한다.
- **NT-13도 정적 층**이다: 소스·빌드 산출물에 비밀·자산 원문이 없다는 것까지 확인한다(`tests/assets/test_frontend_contract.py`).

---

## 확인 필요 (NS1) — 명세서에 없어 내가 정한 사항

NS1을 진행하기 위해 필요했지만 명세서가 값을 고정하지 않은 항목이다. **연구 의미가 걸린 것은 ①뿐이고 나머지는 구현 관례**다. 되돌리기 쉬운 상태로 두었으니 반려하면 그대로 바꾼다.

1. ~~**P00 `sampling.mismatch_locus`**~~ → **해소 (PI 확정 2026-08-16): `trajectory_timing` 유지.** 근거 ① 원 요청(장단점)은 이행되었으므로 content 층의 불일치가 아니다 ② C3 [정본]의 uptake가 내용 대체가 아니라 확장분 회수·범위 복귀다 ③ residual uncertainty가 대화의 다음 단계에 걸려 있다. 근거는 `dossiers/P00.json`의 `sampling.notes_ref`에 기록했다.
2. **dossier 더미 배치** — 위 [자산 현황](#자산-현황)의 2단 배치. CLAUDE.md("P01–P12는 커밋하지 않는다, 스키마 더미만 커밋")를 만족시키려면 실값과 더미의 경로가 갈려야 했다.
3. **`backend/app/notify/` 패키지 위치** — §2.3 폴더 목록에는 notify가 없지만 §2.1이 "`notify` 이식"을 지정한다. 구 리포와 같은 이름의 top-level 패키지로 두었다(`core/`에 넣는 대안도 있었음).
4. **서버 5xx 누적 알림 임계 = 3회 연속** — §2.8은 트리거만 있고 임계가 없다. `[파일럿 확정]` 태그를 달아 두었다(`notify/watch.py`).
5. **질문 검출 휴리스틱 초판** — §6.5가 "의문부호·의문형 종결 휴리스틱 [파일럿 확정: 검출 규칙 1회 조정 가능]"이라 한 그 규칙의 1판. 의문부호 우선 + 보수적 의문형 종결 어미 목록. 자산 계약(NT-22·23)과 런타임 R-3이 같은 함수를 쓴다.
6. **`downstream_actions.display_order`를 JSON 배열로** — §4.8은 "표시 순서", §8.1은 컬럼명만 준다. 제시된 7코드의 순서를 그대로 저장하도록 했다(선택 위치는 파생 가능).
7. **`presurvey_responses.value`를 JSON으로** — 사전설문 자산이 `<TODO: PH-01>`이라 응답 형식(정수 척도/범주 코드)이 미확정이다.
8. **flag 사유 암호화 위치** — §8.1 `events` 컬럼 목록을 유지하고, 🔒 사유는 `payload` 안의 암호문 필드로 넣도록 주석에 고정했다(컬럼 추가 없음).
9. **dossier hash 정규화** — §5.2의 "전체 JSON sha256"을 `hash` 필드 자신만 제외한 canonical JSON으로 계산한다(자기참조 회피). `locked_at`은 포함.
10. **§8.1 전 테이블을 NS1에 정의** — `init_db.py` 이식과 DEV_MODE 기동이 모델을 요구한다. 컬럼은 §8.1 표대로이고 **동작 로직은 넣지 않았다**(상태 전이 NS2, 생성 기록 NS3).

## 미해결 (명세서 TODO)

- `PH-03` dossier P01–P12 실값 작성·2인 판정·lock — **본 모집 전 필수**. 현재는 스키마 더미로 CI·시연이 돈다.
- `PH-04` 실값 배포 반입 절차(Railway volume/환경 주입) — 로더는 이미 실값 우선으로 찾는다.
- `PH-01` 사전설문 **문항 원문·번역** — 구조·로더·계약 테스트는 NS2에서 착지했다. 원문만 넣으면 된다.
- `PH-02` P10에서 sidecar 비표시 — 현재 비표시로 구현(PI 승인 대상).
- `PH-05` normalization 패턴 **보강 확정** — 부록 A.3의 NP-01~03 초판이 NS3에서 자산으로 들어갔다. 파일럿에서 1회 보강한다.
- `PH-IRB-1~7` 문안 — IRB 제출 시 착지. `screen_copy.CONSENT_TODO`·`DEBRIEF_TODO`가 자리를 잡고 있고, 모집 게이트(`core/freeze.py`)가 미착지 상태를 R1에 표시한다.
- 부록 A.1·A.2 프롬프트 문안의 **PI 승인·lock** — 현재 `prompts/prompt_config_v1.json`은 [제안] 상태다(§1.4).
- `[확인 4]` integrity checker 실모델 실행 시점·비용 — `scripts/run_fixtures.py --real`이 준비됐다(§10.1 "QA 직전 1회"). 부록 D.1 리허설의 수동 항목 D1-3b가 이것이다.
- `[확인 1·2]` 모델 슬러그(`anthropic/claude-opus-4.8`·`openai/gpt-5.4`) 가용성과 provider 고정 문법 — 실호출 전 확인. DEV_MODE에서는 불요.
- P00b(낮은 actionability 리허설 변형, 부록 A.6 "선택") 미작성.
- **NT-19 렌더 검증** — 정적 검사만 걸려 있다. JS 러너(vitest) 도입 여부가 미결이고, 현재는 §10.2 워크스루에서 사람이 확인한다(리허설 수동 항목 D1-4b).

## 다음 단계 — 구현 완료 이후 (운영·자산 착지)

NS1–NS4 구현은 끝났다. 남은 것은 **코드가 아니라 자산·승인·운영**이다.

1. **본 모집 게이트 해소** — `DEV_MODE=true python scripts/freeze_study_version.py --check`가 현재 4건(PH-03 · PH-IRB-1 · PH-IRB-2 · PH-01)을 보고한다. 착지 순서: PH-IRB(제출·승인) → PH-01(사전설문 원문) → PH-03(dossier 실값·2인 판정·lock) → PH-04(배포 반입).
2. **프롬프트 lock** — 부록 A.1·A.2 PI 승인 후 `prompt_config_v1.json` 동결, 그 뒤 실모델 fixture 1회(`--real`)와 [확인 4] 비용 기록.
3. **QA 워크스루(§10.2)** — `scripts/run_qa_rehearsal.py`로 자동분을 돌리고, 수동 2건(실모델·렌더)을 사람이 채운다.
4. **soft launch(§10.3)** — P01 세션 태깅 → 리뷰 회의 → [파일럿 확정] 파라미터 조정 → P02 전 동결(§1.4).
5. **설계 동결(§10.5)** — soft launch 종료 시 `scripts/freeze_study_version.py --actor <이름>` 1회.
6. **배포** — Railway 단일 서비스, `proto_v1` → `main_v1` schema 전환(§2.4), 환경변수 전 항목 설정, dossier 실값 반입(PH-04).

미결 결정 대기: 위 [확인 필요 (NS4)](#확인-필요-ns4--명세서에-없어-내가-정한-사항) ①–⑰ 및 NS1–NS3의 목록. 연구 의미가 걸린 것은 NS4 ④·⑫, NS3 ①·⑬, NS2 ②·⑭ 여섯 건이다.
