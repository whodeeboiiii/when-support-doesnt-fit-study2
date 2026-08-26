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
#   모집 게이트 4건: PH-03 · PH-08 · PH-IRB-1 · PH-IRB-2   (PH-06·07은 `_v1` 착지로 소멸)
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
- **freeze**: 모집 게이트가 PH-03 · PH-08 · PH-06 · PH-07 · PH-IRB-1 · PH-IRB-2를 본다 (PH-06·07은 2026-08-24 `_v1` 착지로 통과 — 검사 자체는 회귀 감지용으로 남는다)
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

## 참가자 UI 디자인 시스템 (D-39, 2026-08-21)

전 화면에 통일 디자인을 입혔다. 색은 **흰 배경 + 세 층**이다.

| 층 | 색 | 쓰는 곳 |
|---|---|---|
| 시스템이 요구하는 것 | 파랑 accent | 1차 버튼(채움), 선택 상태(테두리+연파랑), 사건 카드 |
| 연구자가 건네는 말 | 노랑 guide `#FEF7E6`/`#D97706` | 화면 상단 지시문 블록(`.callout`) **전용** |
| 자극 | 무채색 `#F2F2F2` (R=G=B) | AI 말풍선 |

**AI 버블 색조 금지**를 테스트 2건으로 고정했다. `test_ai_bubbles_have_no_color_tint`는
`.bubble-ai`에 accent·guide·yellow·blue가 들어오면 실패하고,
`test_ai_bubble_fill_is_achromatic`은 채움색의 **R=G=B**를 검사한다.

처음에 버블을 흰색으로 뒀다가 되돌렸다. 제약은 **색상(hue)이지 명도가 아니다** — 회색은
hue가 0이라 따뜻함 지각과 무관한데, 흰색으로 잡는 바람에 흰 카드 위 흰 버블이 되어 P10에서
말풍선이 카드 안에 묻혔다. `#F2F2F2` 채움으로 바꿨다. 숫자로 잡히는 경계라
`#F2F0EE`(살짝 따뜻한 회색)를 넣으면 테스트가 실패하는 것까지 확인했다.
같은 이유로 Likert 1–7 버튼도 흰색 → `bg-gray-50`.

**새 응답 하이라이트** — focal AI1 · 대안 AI1 3종 · AI2에 완전히 같은 표시가 붙는다. 말풍선
바깥에 옅은 파랑 링이 한 번 번졌다 남는다(버블 자체는 칠하지 않는다). 정의는 `.bubble-new`
한 곳뿐이고 화면은 boolean `isNew`만 넘긴다 — className을 넘길 수 있으면 호출부마다 갈리므로
prop 타입으로 막았다. 화면당 하이라이트는 **지금 판단 대상인 AI 응답 하나**뿐이다
(P4=focal AI1, P6·P7=AI2, P9=해당 대안). `test_new_response_highlight_is_defined_in_exactly_one_place`.

**모션** — 화면 전환 220ms·말풍선 등장 200ms CSS 애니메이션. **beacon 타이밍은 그대로다**:
마운트도 effect도 미루지 않으므로 `screen_enter`·`render_complete` 발화 시점이 안 바뀐다.
전환을 위해 렌더를 지연시키는 코드를 넣지 말라고 `App.tsx`에 주석으로 못박았다.
`prefers-reduced-motion: reduce`에서 모션은 끄되 하이라이트 표시 자체는 정적으로 남긴다.

**Likert** — 라디오 원 → 누를 수 있는 숫자 버튼 7개(h-12, 16px). 양 끝 앵커를 문항마다 반복
고정한다(블록 상단 1회면 스크롤 뒤에 7의 방향을 기억에 의존하게 된다). 선택은 파랑 테두리 +
연파랑 배경.

**P2 인라인 수정** — 별도 목록 5개를 없애고 버블·카드를 직접 고치게 했다. hover(및 focus)에서
"✎ 수정"이 뜨고, 누르면 그 자리가 원문이 채워진 편집창으로 바뀌며, 저장하면 "수정됨" 배지가
붙는다. 명세 §4.2 [제안]의 "해당 segment가 편집창으로 바뀜"에 오히려 더 맞다.
**배지는 P2에서만** 뜬다 — 이후 화면에서 "당신이 고친 문장"이라고 계속 상기시키면 그 자체가
자극이 된다. 구조로 막았다: 배지는 `edit` prop이 있을 때만 그려지고 그 prop은 P2만 넘기며,
`test_edited_badge_is_confined_to_the_checkpoint_edit_screen`이 다른 화면 유출을 잡는다.

**P10·P11 두 열** — 폭 동일(`grid-cols-2`), 높이 맞춤(`items-stretch`), A/B 헤더 sticky,
**열 내부 스크롤 없음**. 한쪽 열만 스크롤되면 두 응답을 같은 조건에서 읽지 못해 비교가
비대칭이 된다.

**진행 표시 없음** — `ProgressBar`를 삭제했다(어디서도 안 쓰고 있었다).
`test_no_progress_indicator_component`가 부활을 막는다. §4.9의 "다른 응답 1/2/3"과 §4.10의
pair 위치는 명세가 정한 화면 라벨이라 그대로 뒀다 — 진행 표시가 아니다.

### 명세에 없어 내가 정한 것

| 결정 | 근거 | 되돌리기 |
|---|---|---|
| 노랑 = 지시문 블록 전용 | "보조색 노랑"인데 버튼 금지라 남는 자리가 지시문이다. 연파랑 사건 카드와 뜻이 갈린다 | `.callout` 색 2줄 |
| 하이라이트 = 파랑 링(노랑 아님) | 노랑을 쓰면 지시문 블록과 같은 색이 된다. 링은 버블 바깥이라 색조 금지와 충돌하지 않는다 | `@keyframes ring-settle` |
| DEV 도구 색 amber → violet | 노랑이 참가자 지시문 색이 되어 시연 중 둘이 헷갈린다 | DevNote·DevBar 클래스 |
| 선택 상태 검정 → 파랑 윤곽 | 구 주석은 "선택=검정"으로 1차 버튼과 갈랐지만, 검정 채움이 참가자 말풍선과 같은 색이었다. **채움/윤곽** 구분으로 바꿨다 | `.is-selected` |
| `test_no_mobile_css_rules`의 `@media` 통짜 금지 → 폭 기반 질의 금지 | `prefers-reduced-motion`은 반응형이 아니라 D-12와 무관한데 통짜 금지가 막고 있었다 | 테스트 1건 |

### 잡은 결함 — 하이라이트가 실행되지 않고 있었다

첫 적용에서 **링이 아예 안 보였다**. 원인은 CSS 레이어 충돌이다.

- 말풍선에 `animate-bubble-in`(utilities 레이어)을 붙이고 `.bubble-new`(components 레이어)에
  링을 두었다. 둘 다 `animation` **shorthand**에 명시도도 같다.
- Tailwind는 components를 먼저, utilities를 나중에 낸다 → 소스 순서로 utilities가 이긴다.
  빌드 CSS에서 `.bubble-new{animation:ring-settle...}`은 byte 6310, `.animate-bubble-in`은
  byte 9001이었다. 링은 정의되어 있었지만 한 번도 실행되지 않았다.
- 게다가 `bubble-in`은 `both`라 끝 상태에 box-shadow가 없다 — 잔여 링도 남지 않는다.

빌드도 통과하고 CSS도 존재해서 **눈으로 보기 전에는 안 잡히는** 종류였다. 고친 방식:
등장 애니메이션을 `.bubble`로 내리고 `.bubble-new`가 두 애니메이션을 **한 선언에서** 합성한다.
말풍선에서 `animate-*` 유틸리티를 걷어냈다(번들에서 `animate-bubble-in`이 사라진 것으로 확인).

회귀 테스트 2건 — 소스 층(`.bubble-new`가 두 애니메이션을 합성 + 말풍선 className에
`animate-` 없음)과 **빌드 산출물 층**(컴파일된 `.bubble-new`에 `ring-settle`이 남아 있는지).
레이어 순서는 컴파일 후에야 확정되므로 소스만 봐서는 부족하다. 버그를 되돌려 두 테스트가
실제로 실패하는 것까지 확인했다.

**그리고 그 수정이 두 번째 조용한 실패를 만들었다.** `@apply animate-ring-settle`을
raw `animation: ring-settle ...`으로 바꾸자 빌드 CSS에서 `@keyframes ring-settle`이
**사라졌다**(grep 0건). Tailwind는 config의 `keyframes`를 대응 `animate-*` 유틸리티가
소스에서 발견될 때만 내보내는데, 컴포넌트 클래스의 raw 참조는 JIT가 보지 못한다. 선언은
남고 정의만 없어지니 브라우저는 조용히 아무것도 하지 않는다.

최종 형태: **keyframes 3종을 `index.css`의 레이어 밖 평범한 CSS로** 옮겼다(Tailwind가 그대로
통과시키므로 JIT 탐지에 의존하지 않는다). `tailwind.config.js`의 `keyframes`·`animation`
확장은 삭제했고, 화면 전환도 `animate-screen-in` 유틸리티 대신 `.screen-in` 컴포넌트
클래스로 통일해 같은 함정을 두 번 밟지 않게 했다.

회귀 테스트 3건 — ① `.bubble-new`가 두 애니메이션을 합성 + 말풍선 className에 `animate-` 없음
② 빌드 CSS의 `.bubble-new`에 `ring-settle`이 남아 있음 ③ **빌드 CSS에서 참조된 모든
애니메이션 이름에 `@keyframes` 정의가 존재함**. ③이 이번 부류를 통째로 잡는다 —
`@keyframes ring-settle`만 지우고 빌드해서 실제로 실패하는 것까지 확인했다.

교훈 둘.
- **레이어가 다른 두 클래스가 같은 shorthand를 쓰면 소스 순서가 이긴다.** `@layer components`에
  둔 규칙은 유틸리티 한 개로 조용히 무력화된다.
- **클래스가 있다 ≠ 동작한다.** 두 번 다 "클래스도 선언도 빌드 CSS에 있다"를 확인하고
  적용됐다고 보고했지만 둘 다 틀렸다. 참조와 정의를 **연결해서** 봐야 한다.

713 → 724 green. 디자인 계약 테스트 12건 추가.

---

## P7 채팅 맥락 복원 (2026-08-21)

P7이 AI2 말풍선 하나만 그리고 있었다. §4.7 지시문은 "AI의 답변을 **보셨습니다**. 실제
상황이라면 지금 어떻게 하시겠어요?"인데, 무엇에 대한 판단인지가 화면에서 사라진 상태였다 —
참가자가 직전 화면(P6)에서 본 대화를 기억에 의존해 답하게 된다.

- 서버: P7 payload에 `checkpoint`·`ai1`·`user1`·`user2` 추가. P6와 같은 `checkpoint_chat`·
  `dossier.assemble`을 쓰므로 두 화면이 어긋날 수 없다.
- 화면: `FocalTranscript`(effective checkpoint → AI1 → User1 → AI2 → User2)를 P6·P7이
  공유한다. P7 제출 후 화면(F5)에도 같은 것을 그린다 — 답장을 보냈으면 그 답장까지 기록이다.
- 지시문은 그 아래에 그대로 둔다. 문안은 §4.7 [제안] 원문 그대로 변경 없음.

AI3는 여전히 없다(D-33) — User2 뒤에 AI 말풍선을 두지 않는다.
회귀 테스트 2건(`test_p7_carries_the_same_transcript_as_p6` ·
`test_p7_shows_user2_after_reply`). 711 → 713 green.

---

## P3 재진입 타이머 — DEV_MODE 면제 (2026-08-21)

시연 중 화면을 넘길 때마다 30초를 기다려야 해서 워크스루가 성립하지 않았다.
`state_payload`의 P3 분기에서 `DEV_MODE=true`면 `min_seconds`·`hint_seconds`를 0으로 내린다.
클라이언트는 서버가 준 값을 쓸 뿐이라 "지금이 개발이다" 플래그가 프런트에 생기지 않는다
(DevBar·DevNote와 같은 규율).

**실세션(DEV_MODE=false)은 30/60 그대로다.** §0.5·§4.3의 [파일럿 확정] 값이고 초안 §7.3의
interactional re-entry 절차(verification 이후 30–60초 회상) 자체라, 시연 편의가 참가자
구성까지 따라가면 안 된다. `test_reentry_timer_is_waived_only_in_dev_mode`가 두 방향을
같이 못박는다 — 면제가 실세션으로 새거나 [파일럿 확정] 값이 바뀌면 실패한다. 709 → 710 green.

⚠ **PI 확인 대기**: "타이머를 걸지 마"가 실세션까지인지는 확인하지 않았다. 실세션에서도
빼려면 `screen_copy.REENTRY_MIN_SECONDS`를 0으로 두고 §0.5 확정 파라미터 표·§4.3·초안 §7.3을
함께 고쳐야 한다(결정 ID 신규 발급). 지금은 DEV 전용이다.

---

## DEV_MODE 설명 레이블 (2026-08-21, 명세 범위 밖 도구)

팀원에게 화면을 설명할 때 "이 박스가 초안의 무엇인가"를 화면 위에서 가리키기 위한 것이다.
`frontend/src/components/DevNote.tsx` — `DevNote`(알약) · `DevAside`(박스 옆) ·
`DevScreenNote`(화면 상단 배너). 문안은 `docs/연구 7 초안 - 섹션 6, 7.md` 용어 그대로다.

**DevBar와 같은 규율에 묶었다**: 존재 여부는 `/api/dev/status`가 정한다(404 = 미표시).
`import.meta.env` 같은 빌드 플래그로 켜지 않는다 — §4.10(construct label 참가자 비공개)이
빌드 설정 하나로 깨지는 경로를 만들지 않기 위해서다. 계약 테스트 2건으로 고정
(`test_dev_labels_are_gated_by_the_server_not_a_build_flag` ·
`test_dev_label_components_render_nothing_without_dev_mode`). 707 → 709 green.

`/api/dev/status`는 모듈 수준 promise로 창 수명당 1회만 호출한다 — 레이블이 화면마다 여러
개라 각자 fetch하면 화면 전환마다 요청이 수십 건이 된다.

**적용 현황** — 두 층으로 나눴다.
- **화면 배너(`DevScreenNote`)**: P0–P12 + 종료 화면 **전부**. 화면 맨 위 한 줄에 Pn +
  초안·명세 용어 + 한 줄 설명. `test_dev_screen_notes_cover_every_screen`이 누락을 막는다.
- **component 레이블(`DevNote`·`DevAside`)**: **P2에서만**. `CheckpointCard`는 P4·P6·P10에도
  쓰이지만 `devLabels` prop이 꺼져 있다 — AI2 화면에서 카드에 알약 5개가 붙으면 정작 봐야
  할 AI2가 묻힌다.

배너를 손으로 넣다가 P7·P11이 각각 **다른 화면 안에** 들어간 적이 있다. 원인은 anchor로 쓴
`    <div className="screen">`가 6칸 들여쓴 줄과 wide 변형(`maxWidth: 1100px`)에 각각
어긋나 잡힌 것이다. 커버리지 테스트는 존재만 보므로, 위치는 QA 워크스루에서 배너의 `screen`
값과 화면 제목을 눈으로 대조한다(§10.2).

| 박스 | 레이블 | 출처 |
|---|---|---|
| 화면 상단 | Interactional Re-entry | §7.3 |
| 상황 요약 카드 | AI-visible Layer · 최소 context | §7.4 · §7.3 |
| 목록 3줄 → 2줄 | Prior Evidence | §7.4 |
| 말풍선 1 | Original Request | §7.3 |
| 말풍선 2 | Problematic AI-response | §7.3 · §7.5 |
| 말풍선 3 | AI-visible Trouble Turn | §6.2 |
| 수정 UI | Editable Segments (5종) | §4.2 · §7.9 |

---

## proto_v2 검증 — P2 상황 카드 (2026-08-21)

**색**: 상황 요약 카드를 `bg-gray-50` → `border-accent bg-accent-soft`(#E0F2FE)로 바꿨다.
채팅 말풍선과 다른 층(사건 재구성 vs 발화 기록)임을 색으로 분리한다. tailwind 토큰 주석의
"accent.soft는 배경 전용 / 파랑 = 안내" 규칙 안에 있다. `CheckpointCard`는 공용이라 P2뿐
아니라 P4·AI2·pairwise의 checkpoint 카드에 모두 적용된다(의도).

**`prior_evidence` 중복**: P00에서 3줄이 같은 화면의 다른 텍스트와 전부 중복이었다 —
①② `situation_summary` 3번째 문장의 재진술, ③ `original_request` 말풍선의 재진술.
필드 자체는 초안 §7.4 AI-visible layer("AI가 접근할 수 있었던 information")의 구현이고
§4.2 편집 segment·부록 A.1 AI2 렌더·evidence firewall이 여기 걸려 있어 폐기하지 않았다.
대신 **P00 문안만** 고쳤다(PI 선택):
- `situation_summary` → "이직을 할지 말지 AI와 상의하는 대화다." (명세 §5.2 "사건 이해에
  필요한 최소 context"로 환원 — evidence는 `prior_evidence`가 진다)
- `prior_evidence` 3줄 → 2줄 (`original_request` 중복분 제거)

교훈: **`situation_summary`에 evidence를 다시 쓰면 화면과 AI2 프롬프트가 같이 중복된다.**
P01–P24 실값 착지 때 같은 실수가 반복되기 쉬운 자리다 — 자산 작성 지침에 반영할 것.

---

## proto_v2 검증 — 데스크톱 가드 임계값 (D-38, 2026-08-21)

**증상**: "이 연구는 데스크톱(노트북) 브라우저에서만 진행할 수 있습니다."가 정상적인 데스크톱
사용에서 떴다. 종전 임계값은 폭 < 1024px 단독(`copy.ts` · `screen_copy.py`)이라 Zoom 화면공유 중
1920 모니터를 좌우로 나누면(960px) 즉시 차단됐다. 가드는 앱 셸 최상단이라 진행이 통째로 멈춘다.

**검증에서 나온 것**: 1024px은 자신이 내세운 근거와도 맞지 않았다. `App.tsx` 주석은 "자극 표시
조건이 참가자마다 달라진다"를 근거로 들지만, 2단 비교 화면(`Exposure.tsx`·`Wrap.tsx`)의
max-width는 **1100px**이다. 1024–1100 구간은 가드를 통과하면서 열 폭이 472px↔510px로 갈린다.
단일 컬럼(`.screen` max-width **760px**)과도, 2단(1100px)과도 무관한 값이었다.

**변경**: 폭 < 768 **또는** 높이 < 600이면 차단.
- 폭 768 — `.screen` max-width 760px의 포화점. 768px부터 P0–P10 본문 폭이 큰 모니터와 동일하다.
  세로 모드 휴대폰(최대 ~430px)은 계속 전부 걸린다.
- 높이 600 — 폭만 낮추면 가로 모드 휴대폰(956×440 등)이 데스크톱으로 통과해 D-12가 뚫린다.
  그 기기들의 판별자는 폭이 아니라 높이(390–440px)다.

**대가**: 통과 범위가 넓어져 2단 비교 화면의 열 폭 편차가 커진다(768px에서 344px ↔ 1100px+에서
510px). 균일성을 차단으로 강제하지 않고 §4.0의 viewport 기록으로 사후 확인하는 쪽을 택했다.
`GET /api/dev/status`가 아니라 events에 남는 값이라 분석 단계에서 봐야 한다.

**테스트**: NT-19 정적 층 3건으로 교체·추가 — 임계값 일치(서버↔클라이언트), 임계값 ≥ `.screen`
max-width(둘이 따로 움직이면 실패), 가로 모드 휴대폰 차단 + 1280×720·960×1040 통과.
705 → 707 green.

**남은 결정 1건**: 2단 비교 화면을 768–1100px에서 어떻게 다룰지는 정하지 않았다. 선택지는
① 현행 유지(열이 좁아짐) ② 좁으면 세로로 쌓기 ③ 비교 화면에만 별도 상위 게이트.
①로 두었다 — ②는 D-12의 "모바일 대응 CSS 금지"와 부딪히고, ③은 화면별 가드라 §2.10 단일
임계 구조를 깬다. PI 확인 후 바꾸는 편이 낫다.

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

- **NT-19(데스크톱 가드)는 정적 검사만**이다 — 임계값 768×600(D-38)·`.screen` max-width와의
  관계·문안 일치·가드가 화면 선택보다 앞이라는 것까지 본다. 렌더 동작 검증에는 JS 러너가 필요한데 이 리포의 테스트는
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

## IRB 문안 초안 착지 (2026-08-24) — PH-IRB-1·2

`docs/IRB_문안_정본_초안_v1.md`(심의용 연구계획서 v0.9 + 첨부물 작성계획 v1에서 도출)의 초안
문안을 **코드에 착지**시켰다. P1·P12가 더 이상 리터럴 `<TODO: PH-IRB-1 — 동의서 정본>`을 띄우지
않는다 — QA 리허설·워크스루에서 실제 화면을 볼 수 있다.

| 대상 | 전 | 후 |
|---|---|---|
| P1 상단 | `CONSENT_TODO` 문자열 | `CONSENT_NOTICE` (초안 §1-C) |
| P1 항목 6종 | `① 연구 참여 <TODO…>` | `CONSENT_ITEMS` 축약 라벨 (초안 §1-B) |
| P1 하단 | (없음) | `CONSENT_PII_NOTICE` — payload `footnote` 신설 |
| P12 본문 | `DEBRIEF_TODO` 문자열 | `DEBRIEF_BODY` — 공개 ①–⑦ + 연락처 4행 (초안 §2-A) |
| 저장 | `consent_version = irb_v0_placeholder` | `irb_draft_v1_2026-08-24` |

**모집 게이트는 열리지 않았다.** `CONSENT_TODO`·`DEBRIEF_TODO`는 화면에서 내려왔을 뿐 상수로
남아 `freeze.blockers()`의 미착지 표식 역할을 계속한다 — 승인은 IRB가 하지 코드가 하지 않는다.
`freeze_study_version.py --check`는 여전히 6건을 보고하고, PH-IRB 두 줄의 사유만
"문안 미착지" → "IRB 승인 대기 — 초안 문안 착지본 사용 중"으로 정확해졌다.

`tests/assets/test_irb_copy_contract.py`(신규 20건)가 세 가지를 건다: ① 화면 문안 ↔ IRB 문서
**글자 대조**(상수를 테스트에 복사하지 않는다 — [정본] 5건과 같은 규율, 대조 대상만 다르다)
② 표식·`CONSENT_VERSION` **정합**(승인 시 둘 중 하나만 바꾸면 실패) ③ 동의 6종·디브리핑 ①–⑦
필수 항목. 기존 금지 어휘 검사(`test_screen_copy_canonical.py`)가 새 문안도 자동으로 훑는다 —
조건명·R/U/Q·focal·규범 어휘 0건.

**테스트 744 passed** (직전 724 → 744, 불감소). `tsc -b` + `vite build` clean.

### 명세에 없어 내가 정한 것 (전부 되돌리기 쉬운 형태)

| # | 결정 | 근거 | 되돌리는 법 |
|---|---|---|---|
| 1 | 초안 문서에 **§1-C(P1 상단 안내)** 신설 | 초안은 서면 동의서(§1-A)와 재확인 라벨(§1-B)만 줬고 화면 도입문이 없었다. §1-A 상단 안내 5문장 중 **네 문장을 글자 그대로** 옮기고 서면 회신 문장 1개만 뺐다 — 새로 쓴 문장 0건 | 문서 §1-C + `CONSENT_NOTICE` 교체 |
| 2 | `CONSENT_VERSION` 명명 규약 `irb_draft_v1_<날짜>` / 승인본 `irb_v1_<승인일>` | 저장 기록·`assets_hash`가 초안 여부를 말해야 한다. 계약 테스트가 접두사로 승인 상태를 판정한다 | 상수 1개 |
| 3 | `CONSENT_TODO`·`DEBRIEF_TODO`의 **역할 전환**(화면 문안 → 게이트 표식) | 게이트 로직(`freeze.py`)을 바꾸지 않고 게이트를 ⛔로 유지하는 최소 변경. 문안 착지와 승인을 분리한다 | 승인 시 상수 + freeze 블록 동시 삭제(위 표 5단계) |
| 4 | P1 payload에 `footnote` 필드 신설 | PII 안내는 체크 항목이 아니라 하단 고정 안내다(초안 §1-B 하단). 항목에 섞으면 동의 항목이 7종이 된다 | payload 키 1개 + JSX 3줄 |
| 5 | freeze blocker 사유 문구만 갱신 | 콘솔이 "문안 미착지"라고 말하면 거짓이 된다. **판정 로직·태그·상태는 그대로** | 문자열 1개 |

⚠ 남은 비-IRB 의존: **[확인 3]** 재실측(동의서 ④ "최대 30일" 보유 기간) · **상담 기관 3곳**
목록 확정(PH-IRB-3 안전 자원 안내문). 둘 다 IRB 승인과 별개로 지금 닫을 수 있다.

---

## 설계 잔여 결정 승인 (2026-08-24) — PH-09·10·11·13·14

PI가 다섯 건을 **전부 명세 기본값 그대로** 승인했다. 반려 0건이라 **동작 변경도 0건**이고,
코드에서는 `<TODO: PH-nn>` 표식을 걷어내고 `[PI 승인 2026-08-24]`로 바꿨다.

| ID | 확정 | 코드 |
|---|---|---|
| PH-09 | 이탈 유형 6코드·라벨·표 순서 고정 | `screen_copy.END_TYPE_OPTIONS` · `state_machine.EndType` |
| PH-10 | §4.9·§4.10 안내 문안 그대로 | `ALT_EXPOSURE_INTRO` · `PAIRWISE_INTRO` |
| PH-11 | 개방 비교는 **구술만** — 시스템 필드 없음 | 만들지 않는 결정(변경 0) |
| PH-13 | checkpoint 수정 UI 현행(segment 단위) | `CHECKPOINT_EDIT_*` |
| PH-14 | sidecar 1단 「있어요/없어요」 2종, 건너뛰기 없음 | `SIDECAR_HAS_MORE_CHOICES` |

`screen_copy.py` 표기 규약에 **`[PI 승인 <날짜>]`** 를 추가했다 — `[제안]`이 승인되면 이 표식이
된다. `[정본]`과 구분되는 점은 §0.4 동결 항목이 아니어서 명세서 원문 글자 대조를 걸지 않는다는
것이다(문안이 명세서와 같지만 대조 테스트의 대상은 아니다).

**테스트 744 passed** (변동 없음 — 주석만 바뀌었다).

### 명세에 없어 내가 정한 것

| # | 결정 | 되돌리는 법 |
|---|---|---|
| 1 | `[PI 승인 <날짜>]` 표기 신설 | 주석 표기 규약 1줄 + 상수 주석 6곳 |
| 2 | PH-09 해소 범위에서 *이유 필수 여부*를 제외 | 명세 §4.7이 그 항목만 `[파일럿 확정]`으로 따로 표시하고 있어 그대로 뒀다. §8 표 참조 |

---

## 문항 자산 `_v1` 착지 (2026-08-24) — PH-06·PH-07

두 자산이 실값으로 올라왔다. 문면 출처는 프로젝트 문서 『연구7_PH06_focal문항_후보_v1』·
『연구7_PH07_pairwise문항_후보_v1』의 추천 세트다.

**코드 변경 0건이었다.** `ASSET_CANDIDATES = ("*_v1.json", "*_v0.json")`가 앞의 것을 먼저 잡도록
설계돼 있어서, 파일을 놓는 것만으로 로더·게이트·화면이 전부 새 문면으로 갈아탔다. NS2에서
"자산은 코드 변경 없이 교체된다"고 적어 둔 설계가 실제로 값을 한 지점이다.

### focal — 9문항 (`focal_items_v1.json`)

| construct | 문항 | 비고 |
|---|---|---|
| Grounding Sufficiency | `gs_1` · `gs_2` | gs_1은 record 언어로 재작성, gs_2는 "지원"→"도움" 참가자 언어 교체 |
| Correction Effort | `ce_1` · `ce_2` | 구 정본 계승 |
| Reinvestment | `ri_1` | 구 정본 계승 |
| Clarification Need | `cn_1` | "지원"→"도움" 교체 |
| Retrospective Continuation Intention | `rci_1` | **신규** — v0의 `<TODO: 신규 작성 필요>` 해소 |
| manipulation check | `mc_recognition` · `mc_uptake` | mc_uptake의 referent를 **"위 답변"**(AI1 카드)으로 고정 |

### pairwise — contrast당 3문항, 계 9 (`pairwise_items_v1.json`)

- **전 지칭 문항이 `target`/`{side}` 치환으로 통일**됐다. v0은 서술형 지칭("조정을 한 뒤에도…")과
  치환 문항이 섞여 있었는데, v1은 지칭 문항 전부 `{side}` 치환이다 — 좌우가 뒤집혀도 문면이 따라간다.
- 2026-08-26 PI 문면 개정: 문항 코드가 `SEQ1_Q_CONSEQUENTIALITY` 등 서술 코드로 바뀌었고,
  `sequence`의 paired-stem 2문항은 공통 Q 결과성(target 없음)·순서 직접 비교로 대체됐다.
  순서 비교 문항은 양측을 함께 지칭하므로 `{other}`(=target 반대쪽) 치환 자리를 추가했다 —
  `{side}`가 C4, `{other}`가 C2로 렌더된다. `pairwise_responses.item_id`는 새 코드 길이(최장
  34자)에 맞춰 `String(48)`로 넓혔다.
- 이유는 **구술만**(F4-ⓒ) — PH-11 확정과 정합하며 시스템 자유기술 필드를 만들지 않았다.

target → 조건 대응이 세 contrast 모두 **정확히 한쪽**을 지칭하는지 로더가 검증한다
(`with_u`={C3,C4} ∩ sequence{C2,C4} = {C4} …). 9문항 전부 통과.

### 게이트·테스트

`freeze.blockers()`가 **4건으로 줄었다**: PH-03 · PH-08 · PH-IRB-1 · PH-IRB-2.
PH-06·07 검사 코드는 **지우지 않았다** — `_v1`이 사라지면 로더가 `_v0`으로 내려가는데
그 회귀를 잡는 것이 그 두 줄이다. `_v0` 파일도 같은 이유로 남긴다.

**테스트 746 passed** (724 → 744(IRB 계약) → 746(문항 계약 2건 추가), 불감소).

### 정리한 뒤처진 참조

`rating_items.py` docstring · `ASSET_CANDIDATES` 주석 2곳 · `asset_path()` 오류 문구 2곳 ·
`screen_copy.py`의 지시문 자산 경로 · `freeze.py`의 게이트 주석 — 전부 `_v0` 기준으로 적혀 있던
것을 `_v1` 착지 사실과 회귀 감지 의도가 드러나게 고쳤다. 동작 변경 0건.

---

## 실값 배포 반입 절차 확정 (2026-08-25) — PH-04

정본 문서 **`docs/배포_자산_반입_v1.md`**를 썼다. 방식은 v1 권고 A(볼륨) 승계 — JSON 24건을
환경변수로 주입하면 크기 제한·이스케이프·회전이 전부 문제가 되므로 볼륨이다.

절차를 실제로 따라가 보니 **코드가 그 절차를 못 견디는 자리가 둘** 나왔다. 둘 다 증상이
같다 — *틀렸는데 떠 있다*.

### ① 볼륨 오버라이드가 이미지 자산을 가렸다

`DOSSIER_DIR=/data/dossiers`로 돌리는 순간 탐색 범위가 볼륨 하나로 좁아져서, 이미지에
커밋된 **P00(QA 전용, §5.5)** 과 **schema_dummy 24건**이 사라졌다. 결과:

- 24명이 한 명씩 lock되는 부분 착지 상태(§5.3 — 정상 상태다)에서 나머지 참가자가
  `DossierNotFound`로 떨어져 **기동 게이트(§5.4)가 죽는다**
- 배포 환경에서 **QA 워크스루(§10.2)가 돌지 않는다** (P00이 없다)

→ `files.dossier_search_paths()` 신설. **볼륨은 오버레이**다:

```
① $DOSSIER_DIR/Pnn.json        반입한 실값
② <이미지>/dossiers/Pnn.json   P00만 해당
③ schema_dummy/Pnn.json        볼륨 → 이미지 순
```

볼륨에는 **실값만** 올린다. 더미를 볼륨에 복사하는 운용으로도 막을 수 있었지만, 그러면
커밋된 QA 자산이 두 벌이 되어 갈라진다.

### ② 경로 오타가 조용히 수렴했다

| 오타 | 종전 결과 |
|---|---|
| `DOSSIER_DIR` 오타 | `available_participant_numbers()`의 루프가 `DossierNotFound`를 참가자마다 삼켜 **dossier 0건으로 기동 성공** |
| `ASSIGNMENT_PATH` 오타 | 조용히 dummy로 내려가 **더미 배정표를 실은 채 기동 성공** |

→ `AssetLocationError`(RuntimeError) 신설. `DossierNotFound`와 계보를 **일부러 나눴다** —
저쪽은 "이 참가자 파일이 없다"라 루프가 삼켜도 되지만, 이쪽은 "가리킨 디렉터리가 없다"라
삼키면 안 된다. `assignment_path()`도 오버라이드가 설정됐는데 파일이 없으면 끊는다:
명시적으로 지정한 경로가 무시되는 것 자체가 사고다.

### ③ 반입 직후 확인 수단

`freeze.asset_sources()` 신설 → `freeze_study_version.py --check`가 「자산 출처」 블록을
먼저 찍는다. 게이트가 PH-03을 보고할 때 **"볼륨이 안 붙었다"와 "파일은 있는데 lock 전이다"**
가 구분되지 않으면 손을 댈 수 없다.

```
자산 출처 (§2.4 · PH-04)
  dossier 디렉터리 : /data/dossiers (DOSSIER_DIR 오버라이드)
  스키마 더미      : /app/dossiers/schema_dummy (리포 바닥으로 내려감)
  dossier          : 실값 25건 (lock 24건) · 더미 0건
  배정표           : /data/assignments/assignment_v1.json [실값 · assignment_v1 · 24행]
```

**테스트 746 → 755 passed** (`tests/assets/test_asset_import.py` 9건 신규).

### 명세에 없어 내가 정한 것

| # | 결정 | 근거 | 되돌리는 법 |
|---|---|---|---|
| 1 | dossier 탐색을 **3단 오버레이**로 (종전 2단) | §2.4는 `DOSSIER_DIR`가 "볼륨 마운트 오버라이드"라고만 하고 이미지 자산과의 관계를 말하지 않는다. P00이 배포에서 사라지는 것은 §5.5·§10.2와 모순이므로 오버레이로 읽었다 | `dossier_search_paths()`에서 ② 제거 |
| 2 | 오설정 시 **기동 중단**(종전 조용한 폴백) | §5.4가 "자산이 깨진 채 세션을 받는 것보다 안 뜨는 편이 안전하다"고 이미 말한다. 그 태도를 위치 설정에도 적용했다 | 두 함수의 raise를 폴백으로 되돌린다 |
| 3 | 마운트 경로 `/data` 권고 | 이미지의 `/app`(소스 트리)과 섞이지 않게. Dockerfile 주석이 `__file__` 기준 경로 계산을 경고한다 | 문서 §3.1 — 경로 자체는 환경변수와 일치하기만 하면 무엇이든 된다 |

---

## 미해결 (명세서 TODO)

- `PH-03` dossier P01–P24 **실값 작성·2인 판정·lock** — 본 모집 전 필수. 현재는 스키마 더미.
- `PH-03b` `mismatch_locus` 목록 확정 — 초판 5종이 로더 상수로 들어가 있다.
- `PH-04` 실값 배포 반입 — **절차 확정 + 코드 구멍 2건 수정**(아래 절). 남은 것은 호스트 CLI 문법 실측뿐이고, 그건 PH-03·PH-08 착지 후 실제 반입 시점에 닫힌다.
- ~~`PH-06`·`PH-07` 문항 원문~~ — **2026-08-24 `_v1` 착지 완료**(아래 절). 코드 변경 0건.
- `PH-08` **배정표 생성·동결** — 생성기·검증·self-test 완료. `--from-dossiers`로 실값 생성.
- ~~`PH-09`·`PH-10`·`PH-11`·`PH-13`·`PH-14`~~ — **2026-08-24 PI 전건 승인, 전부 기본값 확정**
  (아래 절). PH-09의 *이유 필수 여부*만 `[파일럿 확정]` 창에 남는다.
- `PH-12` 부록 A.1·A.2 v2 프롬프트 **PI 승인·lock** — 현재 `prompt_config_v2.json`은 [제안].
- `PH-IRB-1~7` — 초안 문안 착지 완료(위 절). **IRB 승인**과 슬롯 3종 치환만 남았다. PH-IRB-3의 상담 기관 3곳 목록은 승인과 무관하게 미확정.
- `[확인 1·2]` 모델 슬러그·provider 고정 문법 / `[확인 3]` OpenRouter 보존 정책(전송 항목이
  effective checkpoint·focal AI1·User1로 바뀌었다 — 동의서 문안 갱신) / `[확인 4]` checker
  실모델 비용 / `[확인 5]` Zoom.

---

## 다음 단계 — 구현 완료 이후 (운영·자산 착지)

V2-0–V2-4 구현은 끝났다. 남은 것은 **코드가 아니라 자산·승인·운영**이다.

1. **PH-IRB 제출·승인** → 초안 착지본을 승인본으로 교체(`PLACEHOLDERS.md` §6 「승인 후 교체 절차」 5단계).
2. ~~**PH-06·PH-07** 문항 문면~~ — ✅ 2026-08-24 `_v1` 착지(코드 변경 0건, 예측대로였다).
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

## 2026-08-26 — P23 실세션 준비 (DEV_MODE=false 전환)

**고친 코드 1건 (버그, 문안 불변).** `llm/context._split_at_context`가 `[대화 맥락]`을 단순
`find`로 찾아 **A.1 v2 첫 문단 안의 언급**에서 잘렸다 — system은 "…돕는 대화형 AI입니다. 아래"
25자 조각만 남고 **원칙 1–5가 통째로 user 메시지로** 나갔다. 경계를 "줄 첫머리에 홀로 선 블록
머리말"로 바꿨다(정규식 `^\[대화 맥락\]$`). 프롬프트 문안·hash는 그대로다. 회귀 계약:
`tests/unit/test_prompt_config.py::test_system_part_carries_the_whole_policy_not_just_the_first_line`.

**실LLM 스모크(P00, scratch DB).** DEV_MODE=false로 전 구간 완주(SS00→SS10). MAIN
`anthropic/claude-opus-4.8` 7.06s·$0.0127(947/320 tok), VALIDATOR `openai/gpt-5.4`
1.76s·$0.0021(745/16 tok, JSON 모드·`pass:true`). rule_violations 0 · fallback 0 · 1회 생성으로
final. 두 슬러그 모두 OpenRouter 현행 목록에 존재 — **[확인 1] 해소**, [확인 4] 실측치 확보.

**운영 구성.** `DEV_MODE=false` · `DATABASE_URL`=로컬 SQLite 절대경로(`proto_v2_local.sqlite3`) ·
schema `proto_v2`. dossier P23 lock 완료(§5.3) — PH-03 blocker에서 P23 제외. 남은 blocker는
PH-03(나머지 23건)·PH-IRB-1·2.

**명세에 없어 내가 정한 것** (되돌리기 쉬운 형태로 둔다)

| 결정 | 이유 | 되돌리기 |
|---|---|---|
| DB 파일명 `proto_v2_local.sqlite3` · **절대경로** URL | 상대경로면 `scripts/init_db.py`(리포 루트)와 `uvicorn`(cwd에 따라)이 **서로 다른 빈 DB**를 만든다. 확장자는 기존 `.gitignore`의 `*.sqlite3`가 덮는다 | `.env` 한 줄 |
| `.gitignore`에 `P[0-9][0-9]_interview.csv`·`_screening.csv` 추가 | 리포 루트의 원자료 48건이 untracked였다 — `git add -A` 한 번이면 §2.9 위반이고 이력은 지워지지 않는다 | `.gitignore` 2줄 |
| `pairwise_responses.item_id` `String(32)`→`String(48)` | 새 문항 코드 최장 34자(`STO3_ADDITIONAL_EXPLANATION_BURDEN`) | 코드 1줄. Alembic 미도입이라 반영은 새 schema `create_all` 시점 |

**운영 주의 — secure 쿠키.** `api/deps.py`가 `secure=not dev_mode`이므로 DEV_MODE=false에서는
세션 쿠키가 **https에서만** 저장된다. 자체서명 https로 join→state 왕복을 실측 확인했다.
평문 http는 `localhost` 예외를 주는 브라우저(Chrome·Firefox)에서만 통하고 **Safari는 통하지
않는다**. 원격 참가자는 터널(https)이 필요하다.

---

## 2026-08-26 (2) — 파일럿 조정 1회 (§10.3): pair별 인터뷰 · P11 재작성 · 연구자 rewind

P23(첫 실참가자) 세션 뒤 PI가 지시한 세 건. §10.3이 연 **[파일럿 확정] 1회 조정 창**이므로
P24 세션 전에 동결한다. 772 tests green(기준선 756 → +16).

**① pair별 인터뷰 (§4.10).** 세 pair를 모아 한 번에 인터뷰하던 것을 pair마다로 바꿨다.
별도 화면·상태를 만들지 않았다 — 참가자가 문항을 채운 뒤 **버튼을 누르기 전**이 이미
인터뷰 자리이고(두 응답·문항이 화면에 그대로 있다), 바뀐 것은 **버튼 문안 하나**다:
`PAIRWISE_SUBMIT_BUTTON = "연구자의 안내를 받은 뒤 눌러주세요"`. 백엔드·DB·상태머신 변경 0건.

**② P11 재작성 (§4.11).** 구판(세 pair 좌우 재배치)은 폐기. 지금은 처음 상황 → focal 대화
(AI1 → User1 → AI2) → 나머지 세 응답 **나열**이다. 화면 ID·상태머신은 그대로라 events·
export·R2가 영향을 받지 않는다. 경계는 유지(NT-39): 조건 라벨·문항·평정값·sidecar 없음.

**③ 연구자 rewind (§9.1.1 신설).** 참가자에게 뒤로가기를 주는 대신 콘솔에 되돌리기를 뒀다.
`POST /admin/sessions/{id}/rewind {screen, position?, reason}` — abort·dropout과 같은 개입 계열.

- 대상 P8·P9(1–3)·P10(1–3)·P11, 받을 수 있는 현재 상태 SS05–SS08. 전진은 409.
- **금지 ①** focal(SS04): AI1·User1·AI2가 1회성이라 되돌려도 복구되지 않는다 → abort의 영역.
  **금지 ②** SS09 이후: 디브리핑이 설계를 공개한 뒤의 재측정은 오염이다.
- `generations`·`llm_calls`는 손대지 않는다(§6.6).
- 지우는 것은 UNIQUE가 걸린 측정 행 둘(`ratings`·`pairwise_responses`)뿐. 나머지는 지울
  필요가 없다 — 노출 행 생성기가 기존 행을 건너뛰므로 조건·좌우·`stimulus_hash`가 그대로
  재사용된다(NT-08). 지운 값은 `events(type="rewind")` 스냅샷, 사유는 flag와 같이 🔒.
- **DB 마이그레이션 0건.** idempotency가 상태 자체라(§3.5) 상태만 되돌리면 재제출이 신규
  제출로 처리된다 — 그 성질이 이 기능을 컬럼 추가 없이 성립시켰다.

**명세에 없어 내가 정한 것**

| 결정 | 이유 | 되돌리기 |
|---|---|---|
| rewind 금지 구간 2곳(focal · SS09 이후) | 되돌려도 과학적으로 복구되지 않는 구간을 API로 열면 "복구했다"는 오해가 남는다 | `REWIND_TARGETS`·`REWINDABLE_FROM` 표 2줄 |
| 되돌린 뒤 참가자 화면은 **수동 새로고침** | `App.tsx`는 폴링하지 않는다. 폴링 추가는 §4.0 events에 잡음을 만들고 Zoom 동석이라 구두 안내로 충분하다 | 폴링 5–10초 추가 |
| `SS_RANK`를 `state_machine`으로 승격 | idempotency 판정과 rewind 방향 검증이 같은 순위표를 봐야 한다 — 두 벌이면 갈라진다 | — |

**P23 파일럿 관측 — AI2가 neutral_fallback으로 끝났다.** attempt 1이 R-3(질문 3개 > 상한 1개)로
재생성, attempt 2는 규칙은 통과했으나 checker가 `unsupported_inference` 3건을 잡아 pass=false →
§9.1대로 `neutral_fallback` 착지. 참가자가 본 AI2는 fallback 문안(70자)이다. 파이프라인은 설계대로
동작했지만 **focal AI2가 실제 생성물이 아니므로** P23의 focal 측정 해석에는 이 사실이 붙는다.
세션 비용 $0.046(main 2회 + validator 1회).

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
