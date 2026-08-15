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

## 확인 필요 — 명세서에 없어 내가 정한 사항

NS1을 진행하기 위해 필요했지만 명세서가 값을 고정하지 않은 항목이다. **연구 의미가 걸린 것은 ①뿐이고 나머지는 구현 관례**다. 되돌리기 쉬운 상태로 두었으니 반려하면 그대로 바꾼다.

1. **P00 `sampling.mismatch_locus = "trajectory_timing"`** — 부록 A.6은 P00의 mismatch locus를 명시하지 않는다. "요청 범위를 넘어 장기 계획으로 진행"을 §5.1의 5축 중 trajectory·timing으로 읽었다. `content_depth`로 보는 것이 맞다면 한 줄 수정이다. (P00은 분석 제외 QA 자산)
2. **dossier 더미 배치** — 위 [자산 현황](#자산-현황)의 2단 배치. CLAUDE.md("P01–P12는 커밋하지 않는다, 스키마 더미만 커밋")를 만족시키려면 실값과 더미의 경로가 갈려야 했다.
3. **`backend/app/notify/` 패키지 위치** — §2.3 폴더 목록에는 notify가 없지만 §2.1이 "`notify` 이식"을 지정한다. 구 리포와 같은 이름의 top-level 패키지로 두었다(`core/`에 넣는 대안도 있었음).
4. **서버 5xx 누적 알림 임계 = 3회 연속** — §2.8은 트리거만 있고 임계가 없다. `[파일럿 확정]` 태그를 달아 두었다(`notify/watch.py`).
5. **질문 검출 휴리스틱 초판** — §6.5가 "의문부호·의문형 종결 휴리스틱 [파일럿 확정: 검출 규칙 1회 조정 가능]"이라 한 그 규칙의 1판. 의문부호 우선 + 보수적 의문형 종결 어미 목록. 자산 계약(NT-22·23)과 런타임 R-3이 같은 함수를 쓴다.
6. **`downstream_actions.display_order`를 JSON 배열로** — §4.8은 "표시 순서", §8.1은 컬럼명만 준다. 제시된 7코드의 순서를 그대로 저장하도록 했다(선택 위치는 파생 가능).
7. **`presurvey_responses.value`를 JSON으로** — 사전설문 자산이 `<TODO: PH-01>`이라 응답 형식(정수 척도/범주 코드)이 미확정이다.
8. **flag 사유 암호화 위치** — §8.1 `events` 컬럼 목록을 유지하고, 🔒 사유는 `payload` 안의 암호문 필드로 넣도록 주석에 고정했다(컬럼 추가 없음).
9. **dossier hash 정규화** — §5.2의 "전체 JSON sha256"을 `hash` 필드 자신만 제외한 canonical JSON으로 계산한다(자기참조 회피). `locked_at`은 포함.
10. **§8.1 전 테이블을 NS1에 정의** — `init_db.py` 이식과 DEV_MODE 기동이 모델을 요구한다. 컬럼은 §8.1 표대로이고 **동작 로직은 넣지 않았다**(상태 전이 NS2, 생성 기록 NS3).

## 미해결 (명세서 TODO — NS1 밖)

- `PH-03` dossier P01–P12 실값 작성·2인 판정·lock — **본 모집 전 필수**. 현재는 스키마 더미로 CI·시연이 돈다.
- `PH-04` 실값 배포 반입 절차(Railway volume/환경 주입) — 로더는 이미 실값 우선으로 찾는다.
- `PH-01` 사전설문 자산, `PH-05` normalization 패턴 목록, `PH-IRB-1~7` 문안 — 각 스프린트에서 착지.
- `[확인 1·2]` 모델 슬러그(`anthropic/claude-opus-4.8`·`openai/gpt-5.4`) 가용성과 provider 고정 문법 — 실호출 전 확인. DEV_MODE에서는 불요.
- git 저장소는 아직 초기화하지 않았다(`.gitignore`만 배치). 최초 커밋 시점은 사용자 판단.
- P00b(낮은 actionability 리허설 변형, 부록 A.6 "선택") 미작성.

## 다음 단계 — NS2 (상태머신·화면)

완료 기준(§11.1): NT-06–NT-09·NT-12·NT-14 통과, 문안 [정본] 항목 초안 대조.

1. `core/williams.py` — §3.3 표 + `(P번호−1) mod 4 + 1` 결정론 매핑 (NT-06)
2. `core/` 상태머신 SS00–SS07·SS90/91 × B0–B7, 합법 전이만 허용 (NT-14)
3. §8.2 참가자 API + idempotency(`session_id, branch_index, step`) (NT-09), 새로고침·재접속 복구 (NT-07·08)
4. P0–P11 화면 — [정본] 문안(sidecar 2변형·평정 12문항)은 명세서에서 **복사**, 데스크톱 가드(NT-19)
5. 사전설문 로더 + 자산 계약(NT-05), `tests/helpers.py` 신판
6. 접속 코드 발급·TTL·재발급 동일 세션 바인딩 (NT-27), 참가자당 완료 세션 1개 (NT-12)
