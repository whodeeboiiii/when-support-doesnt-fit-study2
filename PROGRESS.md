# PROGRESS — study2-enactment

정본: `docs/구현명세서_v2.0.md`. 이 파일과 명세서가 충돌하면 명세서가 우선한다.

v1.0.1(within, 12명 × 4-branch) 이력은 git 태그 **`v1.0.1-within`**(커밋 `dc9a673`)에 보존돼
있다. 이 문서는 §11.1의 **V2-0 → V2-4 전환**부터 기록한다.

---

## V2 전환 — 전 스프린트 완료 (2026-08-21)

### 한눈에

| Sprint | 완료 기준 (§11.1) | 결과 |
|---|---|---|
| **V2-0 정리** | 부록 H.1 삭제 적용, 태그 `v1.0.1-within`, grep 0건 | ✅ |
| **V2-1 자산·배정** | dossier 스키마 v2, P00 신 예시, dummy P01–P24, 배정표 로더·생성기 | ✅ NT-20·21·22·23·32 |
| **V2-2 상태머신·화면** | SS00–SS10 · F0–F5 · P0–P12 · checkpoint 수정 · 대안 노출 · pairwise | ✅ NT-07·08·09·12·14·16·31·33–38 |
| **V2-3 AI2** | 입력 3종, R-1 대상 갱신, R-2 플래그화, prompt_config_v2, fixture v2 | ✅ NT-01·02·04·10′·15·25 |
| **V2-4 콘솔·export·마감** | R2 diff·경보, R3 개편, R4 배정·segment, export 개편, 리허설, freeze | ✅ NT-26·28·30·39 |

**테스트 705 passed** (v1.0.1 기준선 508 → 705, 불감소). 부록 D.1 리허설 자동 34건 통과 ·
수동 2건 · 실패 0건.

### 검증 명령

```bash
./backend/.venv/bin/python -m pytest -q                      # 705 passed

export DEV_MODE=true DATABASE_URL="sqlite+aiosqlite:///./dev_local.db" \
       DB_SCHEMA=proto_v2 ADMIN_USER=demo ADMIN_PASS=demo-pass FERNET_KEY=<키>
./backend/.venv/bin/python scripts/init_db.py                # 16 tables (§8.1)
./backend/.venv/bin/python scripts/run_fixtures.py --out reports/fixtures.md
#   블록 R 12/12 · A 4/4 · C 4/4 = 100% → 게이트 통과
./backend/.venv/bin/python scripts/run_qa_rehearsal.py --out reports/qa_rehearsal.md
#   자동 34 · 수동 2 · 실패 0
./backend/.venv/bin/python scripts/freeze_study_version.py --check
#   모집 게이트 6건: PH-03 · PH-08 · PH-06 · PH-07 · PH-IRB-1 · PH-IRB-2
./backend/.venv/bin/python scripts/make_assignment.py --self-test   # 20/20 (NT-32)
./backend/.venv/bin/python analysis/export_trajectory.py --actor <이름> --out exports/

cd frontend && npm run build
./backend/.venv/bin/python -m uvicorn app.main:app --port 8000 --app-dir backend
```

콘솔은 `http://localhost:8000/admin/console` (Basic auth).

---

## V2-0 — 정리 (부록 H.1)

삭제 전 `git tag v1.0.1-within`을 찍었다. **NS4 작업물이 커밋되지 않은 상태였으므로 먼저
커밋(`dc9a673`)하고 태그를 걸었다** — 태그가 코드를 실제로 보존해야 부록 H의 지시가 의미를
갖는다.

**전체 삭제**: `core/williams.py` · `llm/normalization.py` · `assets/presurvey.py` ·
`fixtures/{presurvey_items_v0.json, normalization_patterns_v1.json, normalization_fixture_v1.jsonl,
integrity_fixture_v1.jsonl}` · `analysis/tagging_flags.py` · 대응 테스트 4종 ·
`dossiers/schema_dummy/P01–P12.json` · `prompts/prompt_config_v1.json`.

**개명**: `api/branch.py` → `api/focal.py`, `screens/Branch.tsx` → `screens/Focal.tsx`.

`grep -rE "branch_index|williams|normaliz|presurvey"` — 런타임 코드(`backend/app`·
`frontend/src`) **0건**. 남은 것은 ① 삭제 사실을 적은 주석 ② 부재를 확인하는 테스트
③ npm의 `normalize-path` 패키지뿐이다.

`CLAUDE.md`·`PLACEHOLDERS.md`는 이미 v2.0으로 교체돼 있었다(사용자 작업분).

---

## V2-1 — 자산·배정

### dossier 스키마 v2 (§5.3)

`sampling` → `evidence_code`, `derivation` → `stimulus`. **네 조건 전문을 저장하지 않고
R/U/Q segment를 조립한다**(D-35) — `Dossier.assemble(condition)`이 `r` / `r␣q` / `r␣u` /
`r␣u␣q`를 만든다.

기동 게이트가 보는 계약(§5.4): segment 질문 수(r·u = 0, q = 1) · 조립 결과 질문 수 ·
`stimuli_meta` ↔ 조립 결과 계량 일치 · fallback 질문 0·1,200자 이하 · segment에
researcher_only 문자열 미포함(8자) · `provenance`가 ai_visible 텍스트 필드 전부를 덮음 ·
`qc` 키 존재.

- `dossiers/P00.json` — §5.5의 [정본] segment 3종·trouble cue를 **초안 신 §7.6에서 글자
  그대로**. a_level A2 · locus `trajectory_timing` · permitted_operation·residual_uncertainty
  명세 문면 그대로.
- `dossiers/schema_dummy/P01–P24.json` — `scripts/make_schema_dummies.py`로 생성. 전 필드
  `<TODO: PH-03>` placeholder이면서 NT-20~23 통과. a_level·locus를 세 값·다섯 값에 고르게
  흩뿌려 배정표 self-test가 의미 있는 입력을 받는다.

### 배정표 (§5.2 — v2 신설)

**시스템은 배정을 계산하지 않는다**(D-30). `core/assignment.py`가 읽고, 기동 시 §5.2 제약을
전수 검증한다(NT-32): 24행 · focal 6/조건 · focal group 내 alt_order 6순열 각 1회 ·
pair_order 6순열 각 4회 · 좌우 12/12 및 group 내 3/3 · **alt_order에 focal 미포함** ·
strata 편중(경고).

`scripts/make_assignment.py`가 §5.2 ①–⑥ 절차를 그대로 구현한다. **생성기와 로더가 같은
검증 함수(`check_constraints`)를 쓴다** — 갈라지면 어느 쪽이 정본인지 알 수 없어진다.
`--self-test`가 A0=1인 극단 분포를 포함한 20종에서 전 제약을 통과한다.

`assignments/assignment_dummy.json`(P01–P24, seed 20260820)을 커밋했다. 실값
`assignment_v1.json`은 미커밋(§2.9)이고, dummy로 내려가면 R1·기동 로그·`/api/health`가
`is_dummy`를 표시한다(NT-42).

### 문항 자산

`fixtures/focal_items_v0.json`(부록 A.4 — focal 5 construct 7문항 + MC 2) ·
`fixtures/pairwise_items_v0.json`(부록 A.5 — 3 contrast 8문항). 둘 다 `<TODO: PH-06/07>`
placeholder이고 로더가 그 사실을 `is_placeholder`로 표시해 모집 게이트가 읽는다.

`assets/rating_items.py`가 코드 상수에서 **자산 로더**로 바뀌었다(부록 H.2). 블록 순서
focal → mc 고정과 MC의 AI1 카드 앵커를 자산 계약으로 강제한다(D-37).

`assets/pairwise_items.py`(신설)가 부록 A.5의 **A/B 치환**을 담당한다. 자산은 지칭 대상을
조건이 아니라 **성질**(`with_u`/`without_u`/`with_q`/`without_q`)로 적고, 서버가 배정된
좌우를 보고 "응답 A/B"로 치환한다 — 클라이언트는 조건을 모른다(NT-38).

---

## V2-2 — 상태머신·화면

### SS·F 재작성 (§3.1·§3.2)

SS00–SS10 단선(역방향 간선 0건) + F0–F5. **F 전이에 갈래가 없다** — v1.0.1의 B3는
disposition에 따라 둘로 갈렸지만, v2는 User1이 필수이고(D-32) F4의 reply/end가 둘 다 F5로
간다. `Disposition`에 `no_reply`가 없고 `has_ai2`·`b_state_after_sidecar`도 없다.

`alt_exposure_allowed(ss_state)`가 NT-31의 **단일 판정 지점**이다 — SS05 자체는 포함하지
않는다(평정 화면은 아직 제출 전이다).

`assert_position()`이 position 건너뛰기를 끊는다(NT-33).

### checkpoint 수정 (§4.2·§3.4 — D-25)

v1.0.1의 표시 전용 P3(D-08)가 **참가자 직접 수정**으로 바뀌었다.

- `checkpoint_edits`에 `(segment, original🔒, edited🔒, edited_at)`을 **누적**한다. `original`은
  그 수정 시점의 직전 값이다(최초 수정이면 dossier 원문) — 각 행이 "무엇을 무엇으로
  바꿨는가"의 한 걸음이어야 R2 diff와 사후 코딩(§7.7)이 과정을 읽는다.
- `EffectiveAiVisible`이 원문 + 최종 수정본이고, **`llm/context.py`의 시그니처가 이 타입을
  받는다** — 원문(`AiVisible`)을 넘기는 호출은 타입이 맞지 않는다.
- **AI1은 수정과 무관하게 locked 그대로**다. `assemble()`에 수정본이 들어올 자리가 없다는
  것이 NT-34의 구현이다. 실서버에서 `trouble_cue`를 고쳐도 `stimulus_hash`가 불변임을 확인했다.
- `trouble_cue`·`problematic_ai_response` 수정 시 R2 붉은 경보 + Discord notify(§2.8 신설).
  **시스템은 막지 않는다** — 계속/abort 판단은 사람이 한다(부록 D.3).

### 화면 P0–P12

| 화면 | 내용 |
|---|---|
| P2 | checkpoint 확인·**수정**([정본] 안내 + segment별 편집창) |
| P3 | 재진입 타이머(30초 후 활성, 60초 보조문) |
| P4 | focal AI1 + User1 **필수**([정본] 지시문, 보내기 버튼 하나뿐) |
| P5 | sidecar 3단 조건부([정본] 3문항, 3단은 `preexisting`에서만) |
| P6 | AI2 (채팅 맥락 위에 표시) |
| P7 | User2 이어쓰기 / 종료 6유형 + 이유 — **AI 응답 없음** |
| P8 | focal 5 construct + MC 2 (블록 2에 AI1 카드 앵커) |
| P9 ×3 | 대안 노출 — 입력창 없음, 라벨은 "다른 응답 1/2/3" |
| P10 ×3 | pairwise — 「응답 A」/「응답 B」, contrast 내 문항 무작위 |
| P11 | 인터뷰 대기 — 세 pair 읽기 전용, **문항·응답값 재표시 없음** |

### §8.1 테이블

삭제: `branches` · `normalizations` · `presurvey_responses`.
신설: `checkpoint_edits` · `focal_runs` · `alt_exposures` · `pairwise_views` ·
`pairwise_responses`. 개정: `participants`(배정표 열) · `sessions`(f_state·alt_index·
pair_index) · `turns`(user2 role, `text_normalized` 삭제) · `sidecar_entries`(has_more·
provenance) · `downstream_actions`(disposition·end_type) · `ratings`(scope·construct,
세션 수준) · `generations`(`alt_overlap` 신설) · `events`(`branch_id` 삭제). **16 테이블.**

---

## V2-3 — AI2 파이프라인

### 입력 계약이 뒤집힌 지점 둘 (D-34)

1. **focal AI1 원문이 payload에 들어간다.** v1.0.1은 "AI1 원문 금지 + normalization으로 지시
   복원"이었다. v2는 AI1을 직접 주므로 `normalization.py`가 삭제됐다 — 지시 대상이 payload
   안에 있어 복원할 것이 없다.
2. **checkpoint는 수정본이다.** 수정 **전** 원문은 오히려 R-1의 금지 문자열이다.

`context.build_ai2_payload(effective, focal_ai1, user1, *, violation_types)` — 시그니처가
allowlist다. NT-01은 **양방향**이다: 금지된 것이 없는지 + 허용된 셋이 실제로 들어가는지.

### R-2가 위반에서 플래그로 (§6.4)

v1.0.1의 "타 branch 문자열"은 4-branch 설계와 함께 폐기됐다. 대신 **대안 AI1의 u·q segment
전문 일치**를 보되 **위반으로 세지 않고** `generations.alt_overlap`에 기록만 한다 — AI2는
공통 정책상 스스로 비슷한 조정·질문을 할 수 있고, 그걸 위반으로 승격시키면 정상 생성물이
fallback으로 떨어져 조작 자체가 바뀐다. `flag_alt_overlap()`이 `check_all()`과 **분리돼**
있는 것이 그 구분이다.

R-1의 대조 대상도 갱신했다: researcher_only · sidecar · **checkpoint 수정 전 원문** ·
평정 문항 문면 · User2. `allowed`(payload 전문) 예외가 특히 중요해졌다 — 수정본과 원문은
대부분의 문장이 겹치므로, 예외가 없으면 정상 응답이 R-1로 잡힌다.

### 자산

`prompts/prompt_config_v2.json` — 부록 A.1·A.2 v2 전문 + `prompt_hash`
(`c3adbf9f…`). `normalization_patterns_version` 키 삭제.

`fixtures/integrity_fixture_v2.jsonl` — 20 케이스, 3블록: **R**(규칙 12) · **A**(alt_overlap
4 — 위반 아님) · **C**(checker 3유형 + 정상 4). 전 블록 100%.

---

## V2-4 — 콘솔·export·마감

- **R1**: 배정표 행(focal·대안 순서·pair 순서·좌우·A-level) 열 신설 + `GET /admin/assignment`
  (읽기 전용) + 모집 게이트 6항목 표시.
- **R2**: **checkpoint 수정 diff + 경보**(자극 전제 segment는 붉게) · focal 상태 ·
  `alt_overlap`(기록만이라고 화면에서도 그렇게 표시) · 대안/pairwise 진행표.
- **R3**: contrastive interview 뷰로 개편 — focal trajectory(조건 라벨·sidecar·generation
  경로) + 평정·MC + 대안 순서 + 세 pair(좌우·조건·`focal_included`·응답값) + evidence_code +
  researcher_only + flag. 부록 D.3 가이드 문구를 화면에 실었다.
- **R4**: R/U/Q segment + **조립 레시피** + 조립된 4자극 + QC + 배정표 행.
- **export 8파일**: trajectory(참가자 1행 — D-23) · checkpoint_edits · ratings · pairwise ·
  alt_exposure · generation_integrity · events · **dossier_provenance**(§7.7 구성비).
  자유 텍스트는 `--include-text`의 `free_text.csv`에만. `--latency`가 §2.11의 유일한 파생
  변수 산출 지점이다.
- **freeze**: 모집 게이트가 PH-03 · PH-08 · PH-06 · PH-07 · PH-IRB-1 · PH-IRB-2를 본다
  (부록 H.2 목록 그대로). `assets_hash` = dossier 25 + assignment + 문항 2종 + consent.

### 실서버 확인 (DEV_MODE, `localhost:8011`)

P00 세션을 SS00 → SS10 완주했다.

- 배정: focal C1 · 대안 C2→C3→C4 · pair sequence→scope→stopping
- P2에서 `trouble_cue` 수정 → **AI1은 locked 그대로**, checkpoint만 수정본 표시
- sidecar 3단(있음 → preexisting → 이유) → AI2 `clean` → 종료 `seek_human`
- 평정 블록: focal 7(카드 없음) → mc 2(**AI1 카드 있음**)
- 대안 노출은 **평정 제출 후에야** 등장(NT-31), pairwise A/B 치환이 좌우와 정합
- R2: 경보 True · transcript 3턴 복호화 · `focal_included`는 `scope`만 True
- **SQLite 바이트 검사 — User1·sidecar·이유·수정본 평문 0건**
- 기본 export 8파일에 참가자 문장 0건

---

## 이번 전환에서 잡은 결함 1건

**`write_csv`가 첫 행 기준으로 열을 잡았다.** `pairwise.csv`는 contrast마다 문항이 다르므로
(`item_seq_*` / `item_sco_*` / `item_sto_*`) 행끼리 열이 다르다. 테스트는 `collect()`만 봐서
통과했고, 실서버 export에서 `ValueError: dict contains fields not in fieldnames`로 터졌다.
전 행의 **합집합**(최초 등장 순)으로 고치고 회귀 테스트 2건을 추가했다
(`test_write_csv_unions_columns_across_rows` · `test_written_files_round_trip`).

교훈은 기록해 둔다: **`collect()`만 검사하면 쓰기 단계의 결함을 놓친다.** 이제
`test_written_files_round_trip`이 8파일 전부를 파일까지 쓰고 되읽는다.

---

## 테스트 ↔ 부록 C 매핑

| NT | 위치 |
|---|---|
| NT-01 (양방향) | `integration/test_evidence_boundary.py` — sentinel 주입 + 허용 3종 포함 확인 |
| NT-02 | 〃 — checker 허용 5종 외 불포함 |
| NT-04 | `unit/test_evidence_boundary_static.py` — `llm/`의 import 정적 검사 |
| NT-07 | `integration/test_session_flow.py` — 조건·hash·배정 불변 |
| NT-08 | 〃 — 재접속 복구, AI2 재생성 0건 |
| NT-09 | 〃 — 세션·focal·위치 단계 재제출 |
| NT-10′ | `test_evidence_boundary.py` — 대안 segment가 payload에 0회 |
| NT-12 | `test_session_flow.py` — 실참가자 409, P00 무제한 |
| NT-13 | `assets/test_frontend_contract.py` — 소스·번들·콘솔에 자산 원문·조건 라벨 0건 |
| NT-14 | `unit/test_state_machine.py`(규칙) + `test_session_flow.py`(API 409) |
| NT-15 | `integration/test_ai2_pipeline.py` — generations만으로 경로 복원 |
| NT-16 | `test_session_flow.py` — sidecar 전 AI2 호출 0건 |
| NT-20·21·22·23 | `assets/test_dossier_contract.py` — 25 dossier 전수 + 거부 8종 |
| NT-25 | `test_ai2_pipeline.py` · `test_fixture_runner.py` — 블록 R·A·C 100% |
| NT-26 | `integration/test_console.py` — flag 상태 불변, 전 엔드포인트 audit |
| NT-28 | `integration/test_encryption_audit.py` — 전 테이블 덤프 + 복호화 지점 5곳 정적 열거 |
| NT-29 | `integration/test_events.py` — beacon 쌍 |
| NT-30 | `integration/test_export.py` — 비식별·opt-in·8파일·삭제 열 부재 |
| NT-31 | `test_session_flow.py` — 평정 제출 전 대안 문자열 0회 |
| NT-32 | `unit/test_assignment.py` — 제약 전수 + 거부 6종 + self-test 20종 |
| NT-33 | `test_session_flow.py` — position 건너뛰기 409, 배정 순서 일치 |
| NT-34·35 | `test_session_flow.py` · `test_ai2_pipeline.py` · `test_console.py` |
| NT-36 | `test_session_flow.py` — sidecar 3단 분기 검증 |
| NT-37 | `assets/test_item_assets.py` — 2블록·MC 마지막·합산 부재 |
| NT-38 | `assets/test_item_assets.py` · `test_export.py` — A/B 치환·좌우 정합 |
| NT-39 | `test_console.py` — R3 포함 / 참가자 P11 미포함 |
| NT-40·41 | `test_session_flow.py` · `test_console.py` |
| NT-42 | `test_assignment.py` · `test_freeze.py` · `test_boot_and_gateway.py` |
| [정본] 7건 | `assets/test_screen_copy_canonical.py`(화면 5) · `test_p00_canonical_text.py`(자극 3) |

---

## 확인 필요 (V2) — 명세서에 없어 내가 정한 사항

**연구 의미가 걸린 것은 ①–④**이고 나머지는 구현 관례다. 전부 되돌리기 쉬운 상태다.

| # | 정한 것 | 명세서 상태 | 반려 시 비용 |
|---|---|---|---|
| ① | **P00의 배정을 QA 고정값(focal C1 · 대안 C2→C3→C4 · pair 표 순서 · 좌우 오름차순)으로** | §5.1은 "P00 = QA 합성"만. 배정표에는 없다 | 낮음 — 다만 P00으로 다른 focal 조건을 리허설하려면 값을 바꿔야 한다. **리허설이 C1만 밟는다는 한계**가 여기서 온다 |
| ② | **`checkpoint_edits.original`을 dossier 원문이 아니라 "직전 값"으로** | §8.1은 `original🔒`만 | 중간 — 원문 고정으로 바꾸면 재수정 이력에서 중간 단계가 사라진다 |
| ③ | **R-1 대조에 평정 문항 문면 추가**(전문 일치) | §6.4는 "평정 유래 문자열" | 낮음 |
| ④ | **`END_REASON_REQUIRED = True`**(종료 이유 필수) | §4.7 `[파일럿 확정: 필수 여부]` | 낮음 — 상수 하나로 끈다 |
| ⑤ | 배정표 검증을 생성기·로더가 **같은 함수**로 | §5.2는 절차와 로더를 따로 서술 | 낮음 |
| ⑥ | `make_assignment.py`의 focal 배정을 **탐욕적 restricted randomization**으로 | §5.2 ①은 "가능한 한 균등, 동률이면 locus 편중 최소, seed 무작위" | 낮음 — 결과가 제약을 만족하고 self-test가 20종에서 통과한다 |
| ⑦ | pairwise 문항 중 `sto_*`에 `target`을 두지 않음 | 부록 A.5는 sco_*에만 (A/B) 표기 | 낮음 — 문면이 서술로 한쪽을 지칭한다 |
| ⑧ | `GET /admin/assignment` 신설 | §8.2는 명시(승계 + 이 항목) | 없음 |
| ⑨ | `scripts/make_schema_dummies.py` 신설 | 부록 H.3에 없음 | 낮음 — 더미 24건을 손으로 쓰지 않기 위한 도구 |
| ⑩ | `store.turns()` 정렬을 `coalesce(rendered_at, submitted_at)`으로 | §8.1은 컬럼만 | 낮음 — 안 하면 R2 transcript 순서가 뒤집힌다 |
| ⑪ | export `write_csv` 열 = 전 행 합집합 | §7.7은 파일 목록만 | 없음 — 결함 수정이다 |
| ⑫ | dossier 로더가 **파일이 있는 번호만** 로드(P00–P30 중) | §5.1은 24명 + P00 | 낮음 |
| ⑬ | 세션 생성 시 **배정표 소속을 dossier보다 먼저** 검사 | §9.1은 사유 표시만 | 낮음 — 사유가 정확해진다 |
| ⑭ | `events.payload`의 `viewport`도 export에서 제거 | §2.9는 비식별만 | 낮음 |
| ⑮ | R2 폴링이 매 호출 audit 2행(승계 — NS4 ④) | §2.7은 "모든 콘솔 조회" | 중간 — 3s 폴링이면 세션당 수백 행 |

**승계된 미결 사항**: v1.0.1 PROGRESS의 NS1–NS4 목록 중 v2에서도 유효한 것 —
복호화 audit 요청 단위(NS4 ③), dropout 알림 없음(⑦)·사유 없음(⑧), 콘솔 정적 HTML 분리(①),
`[[fixture:…]]` 트리거(NS3 ⑭), 세션 토큰 HMAC(NS2 ④), 접속 코드 해시 방식(⑬).

---

## 한계로 남긴 것

- **NT-19(데스크톱 가드)는 정적 검사만**이다 — 임계값 1024·문안 일치·가드가 화면 선택보다
  앞이라는 것까지 본다. 렌더 동작 검증에는 JS 러너가 필요한데 이 리포의 테스트는
  pytest다(CLAUDE.md). **vitest 도입은 미결**이고, 지금은 §10.2 워크스루에서 사람이 확인한다
  (리허설 수동 항목 D1-5c).
- **실모델 1회 미실행** — `scripts/run_fixtures.py --real`이 준비돼 있고 실키·[확인 4] 비용
  기록이 필요하다(리허설 수동 항목 D1-5b).
- **§2.9 복호화 지점이 5곳**이다(콘솔·참가자 재표시·수정본 읽기·leakage 대조·AI2용 User1).
  §2.9 v2가 이 다섯을 열거형으로 명시했으므로 v1의 "2곳" 긴장은 해소됐다.
  `test_encryption_audit.py`가 다섯을 정적으로 세므로 여섯 번째가 생기면 먼저 깨진다.
- **P00 리허설은 focal C1만 밟는다**(위 ① 참조). 네 focal 조건 전부를 리허설하려면 배정표
  참가자로 세션을 열거나 P00 고정값을 바꿔야 한다.

---

## 미해결 (명세서 TODO)

- `PH-03` dossier P01–P24 **실값 작성·2인 판정·lock** — 본 모집 전 필수. 현재는 스키마 더미.
- `PH-03b` `mismatch_locus` 목록 확정 — 초판 5종이 로더 상수로 들어가 있다.
- `PH-04` 실값 배포 반입 절차 — `DOSSIER_DIR` 환경변수가 자리를 잡았다.
- `PH-06` focal 문항 원문 — 구조·로더·계약 테스트 완료. `focal_items_v1.json`으로 올리면 된다.
- `PH-07` pairwise 문항 원문 — 〃 (`pairwise_items_v1.json`).
- `PH-08` **배정표 생성·동결** — 생성기·검증·self-test 완료. `--from-dossiers`로 실값 생성.
- `PH-09` 이탈 유형 라벨·이유 필수 여부 PI 승인.
- `PH-10` P9·P10 안내 문안 PI 승인 / `PH-11` 개방 비교 문항(기본값: 구술) /
  `PH-13` 수정 UI 문안 / `PH-14` sidecar "건너뛰기"(기본값: 두지 않는다).
- `PH-12` 부록 A.1·A.2 v2 프롬프트 **PI 승인·lock** — 현재 `prompt_config_v2.json`은 [제안].
- `PH-IRB-1~7` — 동의 항목 6종(⑥ 대안 노출 신설) 구조는 섰고 문안만 남았다.
- `[확인 1·2]` 모델 슬러그·provider 고정 문법 / `[확인 3]` OpenRouter 보존 정책(전송 항목이
  effective checkpoint·focal AI1·User1로 바뀌었다 — 동의서 문안 갱신) / `[확인 4]` checker
  실모델 비용 / `[확인 5]` Zoom.

---

## 다음 단계 — 구현 완료 이후 (운영·자산 착지)

V2-0–V2-4 구현은 끝났다. 남은 것은 **코드가 아니라 자산·승인·운영**이다.

1. **PH-IRB 제출·승인** → 동의서·디브리핑 문안 착지.
2. **PH-06·PH-07** 문항 문면 PI 승인 → `*_v1.json`으로 교체(코드 변경 0).
3. **PH-03** dossier 24건 실값 작성 → 2인 독립 판정·adjudication → `scripts/lock_dossier.py`.
4. **PH-08** `make_assignment.py --from-dossiers --seed <n>` → 생성 로그와 함께 동결.
   ⚠ **배정표는 생성 후 금지**다(§1.4) — 재생성 = 새 seed·새 버전·전원 재배정, 모집 전에만.
5. **PH-04** 배포 반입(`DOSSIER_DIR`·`ASSIGNMENT_PATH`).
6. **PH-12** 프롬프트 lock → 실모델 fixture 1회(`--real`) + [확인 4] 비용 기록.
7. **QA 워크스루(§10.2)** — `run_qa_rehearsal.py` + 수동 2건.
8. **soft launch(§10.3)** — 첫 실참가자 1명 → 리뷰 회의 → [파일럿 확정] 1회 조정 → 두 번째
   참가자 전 동결.
9. **설계 동결(§10.5)** — `scripts/freeze_study_version.py --actor <이름>` 1회.
10. **배포** — Railway 단일 서비스, `proto_v2` → `main_v2` 전환(§2.4).

---

<details>
<summary>v1.0.1 (within, 12명 × 4-branch) 이력 — 태그 <code>v1.0.1-within</code></summary>

NS1 이식·골격(188 tests) → NS2 상태머신·화면(400) → NS3 AI2 파이프라인(444) →
NS4 콘솔·마감(508). 상세 기록은 태그 `v1.0.1-within`의 `PROGRESS.md`에 있다:

```bash
git show v1.0.1-within:PROGRESS.md
```

v2.0에서 폐기된 것: Williams 4-branch 배정 · referential normalization · 사전 설문 ·
no_reply/end 3분기 · 12문항 2블록 · downstream 7메뉴 · cue form 분류 · carryover 태깅 ·
P10 cross-branch review. 처분 근거는 명세 부록 G, 파일 단위 지시는 부록 H.

</details>
