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
**pair_order 전 행 정본 순서**(D-41 — 아래 파일럿 조정 ②) · 좌우 12/12 및 group 내 3/3 ·
**alt_order에 focal 미포함** · strata 편중(경고).

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

## 파일럿 조정 ② (§10.3, P08 세션 뒤) — 2026-08-26

P08(두 번째 실참가자, focal C3) 세션에서 PI 지시 3건. §10.3의 조정 창 안이므로 P10 전에
동결한다. **857 tests green**(기준선 772 → +85. 대부분 dossier 25종 parametrize 3건 = 75).

**① AI1 무대지시 (§4.4 · D-40).** C3·C4의 u는 "…해 보겠습니다"라는 **선언**으로 끝난다.
그대로 두면 참가자가 "왜 해준다고만 하고 실제로는 안 하지?"로 읽는다 — P08이 실제로 그렇게
반응했다. u 바로 뒤에 회색 한 줄을 붙인다: "(그 후 적절한 추천 제공)".

- **붙는 자리는 조건이 아니라 `u`의 존재가 정한다.** C3는 문말, C4는 **q 앞**이다 — q는 "다음
  응답을 위해 남은 질문"이라 마지막이어야 하고(부록 A.5 STO 문항이 "마지막에 한 질문"을
  지칭한다), 무대지시가 가리키는 것은 u가 약속한 지원이다.
- **조립을 둘로 갈랐다.** `assemble()`은 자산 그대로(= `stimulus_hash`·`stimuli_meta`·lock
  hash·자산 계약의 기준, **불변**), `presented()`는 거기에 무대지시를 얹은 표시·전달본이다.
  dossier 파일도 자산 hash도 건드리지 않았다는 것이 이 분리의 요점이다.
- **한 문자열이 세 곳에 간다** [PI 결정]: 화면(P4·P6·P7·P8 카드·P9·P10·P11) · **AI2 payload의
  focal AI1** · `turns.ai1` 기록. 화면에만 있고 AI2에 없으면, 참가자는 "추천을 이미 받은
  대화"를 이어가는데 AI2는 그 사실을 모른 채 추천을 처음부터 다시 한다 — P6에서 AI1과 AI2가
  나란히 보이므로 바로 어긋나 보인다. §1.2 표의 "focal AI1 원문" 행을 "표시본"으로 고쳤다.
- 회색은 `.stim-note` 한 곳에서만 정의한다(`.bubble-new`와 같은 규율 — D-39). 색은 `stim`
  토큰의 무채색(#6E6E6E)이라 자극 색조 금지 규칙과 충돌하지 않는다.
- 문면은 **서버가 `ai1_note`로 내려주고**(NT-13 — 번들에 박지 않는다) 그 필드는 **조건과
  무관하게 항상** 내려간다: 조건에 따라 있고 없으면 필드의 유무 자체가 조건 단서가 된다.

**② pairwise 순서 고정 (§4.10 · §5.2 ③ · D-41).** contrast 순서를 전 참가자
Sequence → Scope → Stopping으로 고정했다. 세 대비의 난이도가 같지 않다 — P08은 배정표가 준
stopping 먼저 순서로 진행했고, 가장 미세한 대비(C3 vs C4)를 아무 준비 없이 먼저 만났다.

- **대가**: pair 순서 counterbalance 폐기. 순서 효과가 전 참가자에게 같은 방향으로 실려
  contrast 간 비교에서 순서와 대비가 교락한다(참가자 간 분산에는 들어오지 않는다).
  좌우(`pair_sides`) counterbalance는 그대로다.
- **배정표는 재배정이 아니라 한 열 수정**이다. 같은 seed(20260826)·같은 strata로 다시 생성해
  `pair_order`를 뺀 전 열이 이전 표와 한 글자도 다르지 않다 — 생성기가 pair 순서 draw를
  **소비만 하고 버리도록** 두어 rng 스트림을 보존했다. 그러지 않으면 스트림이 밀려 이미 세션을
  돌린 참가자의 focal·좌우까지 달라진다.
- 버전을 `assignment_v1` → `assignment_v1.1`로 올렸다. **P08은 stopping 먼저로 진행했고**
  그 세션의 정본은 DB(`participants.pair_order`·`pairwise_views`)다. 두 cohort는
  `participants.assignment_version`으로 구분된다(P08·P23 = `assignment_v1`, 이후 = `v1.1`).
  P23은 원래 배정이 정본 순서와 같아 영향이 없다.

**③ pairwise 문항 순서 고정 (§4.10 · §0.5 · D-42).** contrast 내 무작위를 폐기하고 자산 파일
순서를 제시 순서로 삼는다. 세 세트가 **논증 순서**로 쓰여 있다는 것이 이유다 —
정당성·필요성 → 과잉·부족 → 남은 비용·종합.

- 특히 SEQ3(순서 선호)는 **종합 판단**이라 마지막이어야 한다. 무작위면 1/3 확률로 먼저 나와
  나머지 두 문항이 그 커밋에 anchoring된다. scope처럼 같은 쪽을 연속으로 묻는 세트도 섞이면
  A/B referent가 매 문항 교대한다.
- **무작위가 통제하던 교락이 없다**: 문항 순서는 전 참가자·전 조건에 같은 자산이고 A/B 비교는
  문항 **안에서** 일어난다(`{side}`/`{other}` 치환). N=24·3문항이면 6순열에 4명씩이라 균형이
  아니라 잡음이다 — D-41과 같은 논거다.
- `presentation_order`의 시드 인자를 **시그니처에서 없앴다**(호출부 3곳). 순서가 세션에 따라
  달라질 자리를 남기지 않는 것이 이 결정의 구현이다.
- **P8 focal 평정은 블록 내 무작위 유지.** 그쪽은 construct별 독립 측정이라 같은 construct
  문항(gs_1·gs_2, ce_1·ce_2)이 붙어 나오면 오히려 일관성 압력이 생긴다. `randomization.py`는
  이제 `rating_items`만 쓴다.
- 자산 `_note`에 "문항 순서 = 제시 순서"를 적었다 — 이후 문면 개정은 순서까지 결정한다.
  새 테스트가 비교 문항(`{other}`)이 세트의 마지막인지를 지킨다.

**명세에 없어 내가 정한 것**

| 결정 | 이유 | 되돌리기 |
|---|---|---|
| 무대지시를 `screen_copy`가 아니라 `dossier_loader`에 둔다 | AI2 payload에도 실리므로 화면 문안이 아니라 **자극 조립의 일부**다. `screen_copy`에는 "P00 자극은 dossier 자산"이라는 같은 취지의 선례가 있다 | 상수 1개 이동 |
| `turns.ai1` 기록도 표시본으로 저장 | 기록·화면·AI2가 갈라지면 export가 참가자가 본 적 없는 대화를 보게 된다. `stimulus_hash`는 `assemble()` 기준이라 자산 대조는 그대로 성립한다 | `participant.py` 1줄 |
| R3(세션 뷰어)도 표시본으로 표시 | 연구자가 보는 것은 "참가자가 본 것"이어야 한다. **주의**: P08은 무대지시 없이 진행했으므로 그 완료 세션을 R3로 다시 열면 무대지시가 붙어 보인다 — 그 세션의 정본은 `turns.ai1`이다 | `admin_views.py` 3줄 |
| R4(자산 뷰어)는 `assemble()` 유지 + 표시본 병기 | R4는 자산 QC 화면이라 hash·계량의 기준 문자열이 정본이어야 한다. 둘이 다른 것 자체가 QC 대상이라 나란히 놓았다 | `admin_views.py` 1줄 |
| 배정표 파일명을 유지하고 version만 올림 | README는 재생성 시 `assignment_v2.json`을 지시하지만 그건 **전원 재배정**을 뜻한다. 한 열 수정에 파일명을 바꾸면 배포 `ASSIGNMENT_PATH`(§PH-04)까지 손대야 하고, 실제로 일어나지 않은 재배정을 기록에 남긴다 | 파일명 변경 + env 갱신 |

**남은 것 하나(이번 범위 밖).** `make_assignment.py --dummy`는 커밋된 더미 표를 더 이상
재현하지 않는다 — `_dummy_strata()`가 `dossier_loader.load()`로 strata를 읽는데 실값
dossier(P08·P10·P23)가 착지한 뒤로 그 세 행의 a_level·locus가 schema_dummy와 달라졌기
때문이다. 그래서 이번에는 더미를 재생성하지 않고 `pair_order` 열만 고쳤다(다른 열을 흔들면
CI가 보는 표가 통째로 바뀐다). 더미 생성기가 schema_dummy만 읽게 하는 것이 정공법이다.

## 파일럿 조정 ③ (§10.3, P23·P08 AI2 실적 검토 뒤) — 2026-08-27

**증상: 실참가자 2명 중 2명이 `neutral_fallback`으로 끝났다.** 지금까지 진짜 AI2를 본
참가자는 0명이다. `generations.checker_result`에 남은 6개 span을 열어 보니 전부 checker
오탐이었고, 원인이 셋으로 갈렸다 — PI가 `prohibited_inference` 재명세 + A.2 v3를 지시했다(D-43).

| 참가자 | checker가 잡은 span | 실제 정체 |
|---|---|---|
| P08 #1 | "…것**일 수도 있고**, …**일 수도 있습니다**" | 제3자(언니) + 조건부 병렬 — 단정 아님 |
| P08 #1 | "…뜻이라고 **단정할 수는 없습니다**" | **단정을 거부하는 문장**이 단정 위반으로 |
| P08 #2 | "위로를 기대한 상황에서는 …" | 지원 선호 — 6건 중 유일하게 판단이 갈릴 수 있는 건 |
| P23 #2 | "부담을 줄이려면" | 참석자(제3자)의 부담 — 주어 부재 |
| P23 #2 | "낯선 사람들끼리 하기 힘든 팀전 위주의 게임은 빼고" | **P23 dossier `u` segment 원문 그대로** |
| P23 #2 | "진행자가 이끌기 좋은 순서로" | 역할 서술 = 제안의 설계 근거 |

P23의 두 번째 span이 핵심이다: checker가 **locked 자극(AI1)** 을 AI2의 위반으로 귀속했다.
어제 넣은 D-40 무대지시는 AI2가 uptake를 이어받도록 더 강하게 유도하므로 이 오탐 경로는
방치하면 더 잦아진다. 그리고 P08은 사건 자체가 "AI가 제3자에 대해 부당한 판정을 내렸다"라
AI2가 **언니에 대해 말해야만** 하는 turn인데, 주어 없는 금지 목록은 그 서술을 전부 잡았다 —
그 조건에서는 통과가 구조적으로 불가능했다.

**① `prohibited_inference` 재명세 (§5.3 · NT-44).** 주어=사용자 · 단정형 · 여섯 범주 ·
3–5개 · 의도/선호 양방향. **AI 행위 제약은 목록에서 뺐다** — "record에 없는 새 방법 생성
금지"는 `permitted_operation`의 상한이고 **U 도출 단계에만** 적용된다. AI2는 User1 이후에
evidence 범위 안에서 실제 지원을 제시해야 하는 turn이라(§6.3 ③), 그걸 checker에 넘기면
정책상 해야 할 일이 위반이 된다. checker의 `expansion`이 대신 맡는 것도 아니다(expansion은
새 주제·장기 계획·위기 상담이다).

P00(`p00_qa_v3`)·P08(`p08_v2`)·P10(`p10_v2`)·P23(`p23_v2`) 재작성 후 재lock. 예:

- 구: "표현되지 않은 부담감·긴장·걱정 등 감정 추론" (P23)
- 신: "사용자가 부담·긴장·걱정 등 대화에 표현하지 않은 감정을 느끼고 있다고 단정하는 것"

**② checker A.2 v3 (부록 A.2 · `prompt_hash` `fbe5d92e…` → `ef052e03…`).** 판정 대상을
초안으로 한정 + AI1 오귀속 금지 / `unsupported_inference` 성립 조건 (a)(b)(c) / 비위반 사유
4종 / **[사용자 메시지] > 금지 목록** / 목록을 참고 목록으로 격하 / 보수 판정. 입력 5종·JSON
스키마·위반 임계(1건)는 그대로다.

**③ R-3 질문 검출 규칙 조정 (§6.5 조정 창 1회 사용).** `냐|니` 어미가 아무 단어 끝에나
걸려서 "어머니." "그러니." "도움이 될 거니."가 전부 질문이었다. **평서 종결 부호(`.`·`!`)로
끝나면 질문이 아니다**로 고쳤다. 부호 없는 진짜 질문("…잠이 깨나요")은 그대로 잡힌다.
전 dossier(실값 4 + schema_dummy 21)의 조립 질문 수·`stimuli_meta`가 **한 건도 안 움직인다** —
`test_declarative_fix_does_not_move_any_locked_asset`이 매 실행 전수 대조한다.

**cohort 경계.** v2로 AI2를 생성한 세션은 P23·P08 둘뿐이고 `llm_calls.prompt_hash`와
`participants.dossier_version`(`*_v1`)으로 식별된다. 둘 다 fallback 착지라 **그 두 명이 본
AI2는 실제 생성물이 아니다** — 분석에서 `generations.fallback_used`로 분리한다. 지금 고치는
편이 나은 이유이기도 하다: 미룰수록 이 cohort가 커진다.

**명세에 없어 내가 정한 것**

| 결정 | 이유 | 되돌리기 |
|---|---|---|
| 작성 규칙을 **기동 게이트가 아니라 테스트(NT-44)** 로 강제 | 게이트로 걸면 문면을 조금 달리 쓴 정당한 코딩 판단이 **라이브 기동 실패**가 된다. 미작성 21건은 어차피 커밋 전에 로컬 테스트를 지난다 | `dossier_loader.validate` 이관 |
| A.2 v3에서 데이터 블록 치환자를 **뺐다** | 제안서 원문대로 `{ai_visible_context}`·`{draft}` 등을 system에 넣으면 치환 안 된 중괄호가 모델에 가고 같은 내용이 user에도 붙는다. `_assert_filled`가 `{prohibited_inference}`만 보므로 **오류 없이** 그렇게 된다 | — |
| 대조 예시를 중립 도메인으로 교체 + NT-45 신설 | 제안서 예시 "많이 지치셨을 텐데"는 P08 `researcher_only.ideal_response_reported`의 문구와 사실상 같았다. 기능적 위반은 아니지만(R-1은 AI2 **출력**만 본다) 전 참가자 공통 lock 프롬프트에 한 참가자 문구가 박히는 것이다 | 예시 문구 교체 |
| P10 목록 5번에 "자리에서 움직일 수 있는 범위" 추가 | 제안서 §2-2에는 없지만 그게 P10의 `residual_uncertainty` 본체다 — AI2가 "잠깐 일어나서"를 전제하면 정확히 그 미확정을 단정하는 것이다. C4의 `q`가 묻는 것과 같다 | 항목에서 그 구절만 삭제 |
| P23 구 6번(진행자 역할·성향) **삭제** | 주어가 제3자라 규칙 위반이고, 실제로 오탐 3건 중 하나를 만들었다. 사용자 사정 항목이 필요한 부분을 흡수했다 | 항목 복원 |

**실모델 재검 (2026-08-27, 44회 호출 · $0.59).** DB 미기록 오프라인 replay —
실 dossier + 실 AI1 표시본 + **합성 User1**(실 User1·실 초안은 복호화하지 않았다).
MAIN `anthropic/claude-opus-4.8` · VALIDATOR `openai/gpt-5.4` · temperature 0.4라 실행마다 흔들린다.

| 참가자 | 전 파이프라인 3회 (생성 → 규칙 → checker → 재생성 1회) | 개정 전 |
|---|---|---|
| P10 (C3) | **3/3 정상** (전부 attempt 1) | — (미실시) |
| P23 (C3) | **2/3 정상** (1회 fallback) | 0/1 (fallback) |
| P08 (C3) | **1/3 정상** (2회 fallback) | 0/1 (fallback) |

- **회귀**: v2가 잡았던 6개 span을 v3로 재판정 → **4/6 통과**. 남은 둘은 P08의
  "위로를 기대한 상황에서는…"(평가 단계에서도 갈릴 것으로 본 건)과 P23의 "부담을 줄이려면…"
  (원 초안 문맥 없이 단문으로 넣은 재구성이라 판정이 불리하다).
- **recall**: 진짜 위반 4종(감정 단정·expansion·correction_ignored·선호 단정) **4/4 검출**.
  통과율만 오르고 눈이 먼 것은 아니다.
- **R-3**: 위 26회에서 발화 0건. 별도 실행에서 P23 초안 2건이 R-3에 걸렸으나 재현되지
  않았고, 그 초안이 진짜로 질문 2개였는지는 확인하지 못했다.

**남은 오탐 두 갈래(다음 조정 후보).**

1. **대화 맥락에 이미 있는 감정을 checker가 잡는다(P08 2회 모두).** 실패한 span이 전부
   "속상할 만해요" 계열인데, P08 `prior_evidence`에는 **"이 일로 언니와 다투어 속상하다고
   표현했다"**가 있다. 조건 (c)("맥락 어디에도 없음")와 비위반 사유("이미 쓴 표현을 같은
   강도로 되짚기")가 적용되지 않았다 — 금지 목록의 감정 범주("죄책감·분노·**서운함**")가
   (a)(b)(c) 게이트를 눌러버리는 것으로 보인다. → 작성 규칙에 **"대화 맥락에 이미 나타난
   감정·사정은 항목에 넣지 않는다"**를 추가하고(evidence와 충돌하는 금지 항목), A.2에
   "맥락에 있는 감정을 되짚는 것은 비위반" 예시를 1건 넣는 것이 후보다.
2. **제3자에 대한 설계 근거 서술(P23 1회).** "서로 모르는 분들도 자연스럽게 섞일 수
   있도록" — 참석자(제3자) + 제안의 근거인데도 잡혔다. (a)와 설계 근거 비위반 사유가
   둘 다 있는데 적용되지 않았다.

둘 다 **v3에 이미 있는 규칙이 적용되지 않은 것**이지 규칙이 빠진 것이 아니다. 그래서 다음
조정은 규칙 추가가 아니라 **금지 목록의 항목 선정**(1)과 **예시 보강**(2)이 먼저다.

**2차 조정 (A.2 v3.1 + 목록 ⑧, 같은 날).** 위 두 갈래는 규칙이 빠진 게 아니라 적용이 안 된
것이라, 규칙 추가 대신 ① 작성 규칙 ⑧("맥락에 이미 있는 감정·사정은 항목에 넣지 않는다")로
목록에서 충돌 항목을 빼고 ② A.2에 맥락 우선 두 줄 + 대조 예시 2건을 넣었다. 규칙 ⑧을
기계 검사로 돌리자 **내 재작성 자체의 결함이 먼저 잡혔다** — P23 목록에 "장소"를 넣었는데
`prior_evidence`에 "파티 장소는 파티룸이라고 말했다"가 있었다(참석자 수도 마찬가지).

| 항목 | 구 | 신 |
|---|---|---|
| P08 감정 | 죄책감·분노·**서운함** | 죄책감·분노 (맥락에 "속상하다") |
| P08 사정 | 가족 관계·직장 사정 | 언니와 평소 어떤 관계였는지·연구실에서 어떤 위치였는지 |
| P10 감정 | 짜증·**피로**·스트레스 | 짜증·스트레스 (맥락에 "졸리다") |
| P23 사정 | 참석자 수·서로 아는 정도·**장소**·예산 | 예산·시간대·참석자들의 연령대 |

**재측정 (30회 · $0.41 · `prompt_hash` `fe14a1c9…`).**

| 참가자 | 개정 전 | v3 | **v3.1 + 목록 ⑧** |
|---|---|---|---|
| P10 | — | 3/3 | **3/3** |
| P23 | 0/1 | 2/3 | **3/3** |
| P08 | 0/1 | 1/3 | **2/3** |
| P08 (`prior_evidence`의 "참가자" 제거본) | — | — | **3/3** |

**부수 발견 — P08 `ai_visible.prior_evidence`에 연구 어휘 "참가자".** 두 번 나온다
("책임을 참가자 쪽으로 돌렸고, 참가자는 그 메시지 캡처를 보여줬다"). 다른 dossier는 전부
주어 없는 서술이다("졸리다고 말했다", "파티 장소는 파티룸이라고 말했다"). 이 텍스트는
**참가자 화면(P2·P4·P6·P7·P9·P10·P11 checkpoint 카드)과 AI2 payload [대화 맥락]에 동시에**
나가고, 실제로 AI2 초안이 "참가자(사용자님)"라고 받아썼다. P08 세션은 이미 끝나 진행에는
영향이 없지만 ① 기록 정합 ② **미작성 21건 예방**이 남는다 — 문면 수정은 PI 확인 사항이다.

**A/B로 측정했다**(파일은 건드리지 않고 `build_effective` overlay로 수정본을 만들어 비교):
"참가자" 제거본이 **3/3 정상**(원문 2/3)이고, **AI2 초안에 "참가자"가 등장한 횟수는
원문 2/3회 → 제거본 0/3회**다. 즉 이 어휘는 화면 문체 문제이자 **AI2 출력 오염원**이다.
다만 prohibited_inference 오탐의 주원인은 아니었다 — 그건 목록↔evidence 충돌(⑧)이었고,
둘은 별개 결함이다. 명세 §5.3에 `ai_visible` 문체 규칙을 `<TODO: PH-15>`로 걸어 뒀다.

## 배포 준비 — PH-04 닫기 · Postgres 경로 실측 (2026-08-27)

**왜 지금.** 인터뷰 세션을 연구자 2인이 각자 진행하기로 하면서 상시 구동 배포가 필요해졌다.
로컬 터널 구성은 호스팅하는 사람의 노트북이 세션 일정에 묶이고, 절전·네트워크 전환 한 번에
참가자 화면이 끊긴다 — §9.1이 막는 dead-end를 운영 층위에서 만든다.

배포에서 처음 만나는 미지수를 줄이려고 **로컬에서 배포 구성을 그대로 재현해 때려봤다.**
컨테이너 + Postgres 16 + 볼륨 오버레이 + 실값 배정표 조합이다.

### 실측 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 이미지 빌드 | `docker build .` | 성공 · 354MB |
| Postgres DDL | `init_db.py` → PG 16 | 16 테이블 |
| **세션 SS00→SS10 전 구간** | Postgres 대상 full-flow(FakeLLM 주입, `DEV_MODE=false`) | 완주 · 14/16 테이블 기록 |
| 🔒 필드 | `turns.text` = `bytea` | Fernet 토큰 저장 확인 |
| **transaction-mode 풀러** | pgbouncer 1.25 경유 full-flow + 동일 쿼리 25회 | 완주 · prepared statement 문제 없음 |
| 볼륨 오버레이 | 스테이징 산출물을 `/data`로 마운트 | 실값 3건 + 더미 21건 · 「자산 출처」 일치 |
| 콘솔 인증 | `/admin/console` | 무인증 401 · Basic 200 |
| 로컬→PG 이관 | 580행 이관 후 실키 복호화 | 시각·암호문 무손실 |

풀러를 굳이 때려본 이유: Supabase 접속 경로가 direct / session pooler / transaction pooler로
갈리는데, transaction 모드는 커넥션이 문장 단위로 갈려 `SET search_path`가 날아갈 수 있다.
`models/session.py`가 **트랜잭션마다 다시 거는** 방식으로 이미 대비돼 있었고, 그 설계가
실제로 유효함을 확인했다. (그래도 배포 기본값은 보수적으로 session pooler로 둔다.)

### 발견 ① — 콘솔이 주는 DB URL 그대로는 기동이 죽는다

Supabase·Railway가 복사해 주는 형태는 `postgresql://…`다. SQLAlchemy는 드라이버가 빠진 이
형태를 **psycopg2**(동기·미설치)로 해석하므로 `ModuleNotFoundError: No module named 'psycopg2'`
로 기동이 끊긴다. 원인이 URL에 있다는 단서가 어디에도 없고, 하필 배포 도중에 터진다.

`core/config.normalize_db_url()`을 신설해 **드라이버만** 명시한다(`postgresql+psycopg://`).
연결 대상은 한 글자도 바뀌지 않으므로 §2.4가 막는 "조용한 흘러내림"(=의도와 다른 DB에
붙는 것)과는 층위가 다르고, 우리가 설치한 async 드라이버가 psycopg3 하나뿐이라 붙일
드라이버에 선택지가 없다는 점이 이 정규화를 안전하게 만든다. 테스트 5건 추가
(`tests/unit/test_config.py`) — DEV_MODE 구멍이 다시 열리지 않는지도 함께 건다.

### 발견 ② — 배포 구성에서 세션 쿠키는 `Secure`다

`api/deps.py`가 `secure=not settings.dev_mode`로 쿠키를 굽는다. 즉 **참가자 링크가 `http://`면
P0에서 더 나아가지 못한다.** Railway가 HTTPS를 주므로 실제 문제는 아니지만, 포트 포워딩이나
평문 커스텀 도메인으로 접근하면 그 자리에서 막힌다. 런북 2.5에 경고로 박았다.

### PH-04 닫기

남아 있던 2건을 실측으로 닫았다.

- **호스트 CLI 문법** — Railway CLI v5.44.1 기준 `railway volume files upload <local-dir>
  <remote-dir> --overwrite`가 디렉터리째 올린다. 종전 문서의 `railway ssh -- cat >` 24회
  반복보다 정확하고, 전송 요건 셋(TLS · 중간 저장소 없음 · 파일명 보존)을 그대로 만족한다.
- **볼륨 백업 정책** — 볼륨에 있는 것은 로컬에 원본이 있는 lock 파일이고, 세션이 시작되면
  수집 데이터는 DB에 쌓인다. 그러므로 **볼륨 백업의 목적은 복구가 아니라 반입 상태의 대조**로
  두고(`railway volume files download`), 실제 백업 대상은 DB로 규정했다. 장기 보관은
  PH-IRB-4의 오프라인 백업이 정본이다.

**`scripts/stage_volume_assets.py`를 신설했다.** 올린 뒤에 발견하는 실수는 그 참가자의 세션이
실제로 뜬 다음에야 티가 난다. 그래서 올리기 전에 기계로 건다 — 파일명↔`participant_no` 일치 ·
dossier 계약 · lock 완료(§5.3) · 배정표에 있는 번호 · P00 제외. 하나라도 어긋나면 반입본을
만들지 않는다. 현재 P08·P10·P23 3건이 반입 가능이고 나머지 21명은 더미로 뜬다(정상).

### 로컬 파일럿 데이터

`proto_v2_local.sqlite3`에 **P08(완주 SS10)** 과 **P23(진행 중 SS08 · active)** 이 있다. 배포로
옮기면 따라오지 않는다 — P08은 export가 두 곳으로 갈리고, **P23은 배포에서 재개할 수 없다**.

`scripts/migrate_local_to_deploy.py`를 신설했다(기본 미리보기, `--apply`로 실행). 대상 schema가
비어 있어야 돌고, SQLite의 tz 없는 값에 UTC를 명시해 넣는다 — 이 변환이 없으면 세션 시각이
조용히 밀린다. 580행 이관 후 **실 `FERNET_KEY`로 복호화까지 확인**했다.

**옮길지 말지는 연구 판단이라 실행하지 않았다.** 파일럿을 §10.3 조정용으로만 쓰면 옮기지
않는 것이 맞고, P23을 재개할 생각이면 옮겨야 한다.

### 문서

- **`docs/배포_실행_v1.md` 신설** — 배포 전체 절차의 정본. 외부 사이트에서 사람이 해야 하는
  일(Railway·Supabase·OpenRouter·Discord)을 순서대로, 검증 체크리스트와 사고 대응까지.
- `docs/배포_자산_반입_v1.md` → **v1.1** — §3.3 실측 문법 · §7 백업 정책 신설.
- `PLACEHOLDERS.md` — PH-04 ◐ → ✅. 개발자 단독 항목이 이제 없다.

### 명세에 없어 내가 정한 것 (전부 되돌리기 쉬운 형태)

| # | 정한 것 | 근거 | 되돌리려면 |
|---|---|---|---|
| 1 | 드라이버 없는 Postgres URL을 `postgresql+psycopg://`로 정규화 | §2.4는 `DATABASE_URL`만 말하고 드라이버 표기를 규정하지 않는다. 콘솔이 주는 형태로 기동이 죽는 것이 더 나쁜 결과이며, 연결 대상은 불변이라 §2.4의 취지를 건드리지 않는다 | `config.normalize_db_url()` 삭제 + 호출부 1줄 · 테스트 5건 |
| 2 | 볼륨 백업 = 복구가 아니라 대조 | 볼륨 내용은 로컬에 원본이 있고, 수집 데이터는 DB에 쌓인다. PH-04가 열어둔 결정 | `배포_자산_반입_v1.md` §7 |
| 3 | 반입 전 스테이징 검증을 **기계로** 건다 | 반입 문서 §3.3의 요건이 사람 눈 대조로만 남아 있었다 | `scripts/stage_volume_assets.py` 삭제 |
| 4 | 로컬→배포 이관 도구를 만들되 **실행하지 않는다** | 이관 여부는 연구 판단이고, 도구 부재로 선택지가 닫히는 것은 피한다 | `scripts/migrate_local_to_deploy.py` 삭제 |
| 5 | 배포 기본 접속 경로를 session pooler로 권고 | transaction 모드도 실측 통과했으나 검증은 pgbouncer 대역이고 Supavisor 실물이 아니다 | `배포_실행_v1.md` 2.2 |

### 사람이 해야 했던 결정 — 2026-08-27 착지

| 항목 | 결정 | 여파 |
|---|---|---|
| **콘솔 계정 분리** | **하지 않는다** — §2.7의 HTTP Basic 단일 자격 유지 | 코드·명세 변경 0건. 연구자 2인이 같은 자격을 쓰므로 `audit_logs`로는 행위자가 구분되지 않는다 → **세션마다 진행자를 연구 기록에 수기 기입**하는 것이 IRB 문안 4항의 이행 수단이다 |
| **파일럿 데이터 이관** | **한다** (P08 완주 · P23 진행 중) | 첫 배포 직후·세션 생성 전에 `migrate_local_to_deploy.py --apply`. P23은 `active`(SS08)로 옮겨져 재접속 시 이어진다 |
| **Supabase 리전** | **서울**(Northeast Asia) | 수집 데이터는 국내 |
| **Railway 리전** | **싱가포르** (서울 불가 확인 후 확정) | 지원 리전은 US West·US East·EU West·Southeast Asia 넷뿐. Fly.io도 서울이 없고(도쿄 최근접), 서울이 되는 것은 Cloud Run `asia-northeast3`뿐인데 **Cloud Run은 Railway식 영구 볼륨이 없어 PH-04를 GCS FUSE로 다시 짜야 한다** — 채택하지 않았다. 국외로 나가는 것은 dossier 볼륨뿐이고 수집 데이터는 Supabase 서울에 있다 |

환경변수 주입은 `scripts/push_env_to_railway.py`로 자동화했다. 손으로 14개를 옮기면 하나쯤
빠지는데, 이 구성에서는 변수 하나가 틀려도 **기동 실패가 아니라 조용한 오작동**일 수 있다 —
`FERNET_KEY`가 다르면 서버는 멀쩡히 뜨고 세션도 돌지만 기존 🔒 데이터만 못 읽는다. 그래서
목록을 코드에 뒀다. 볼륨 변수 2개는 반입 뒤에만 걸리도록 2단계로 분리했다.

### 테스트

871 passed → **876 passed** (42 skipped 동일). 기준선 불감소.

---

## 사전 설문 복원 (D-44) — 2026-08-27

**연구자 지시.** "사전설문 내용을 구현해 줘. 일단은 v1.0.1 명세 이대로 구현. 화면은
checkpoint 보여주기 이전에, 동의서 직후에."

**정본과 어긋난다는 점을 먼저 적어 둔다.** 명세 v2.0은 D-31(Q&A #1)로 사전 설문을 삭제했고
(§0.2 "사전 설문이 없다 … 표본 기술은 Study 1 자료로 대체"), 부록 H가 `assets/presurvey.py`·
`fixtures/presurvey_items_v0.json`·`presurvey_responses`의 삭제를 지시했다. 이번 작업은 그
결정을 뒤집는다. 지시가 명시적이므로 구현하되, **명세서 개정이 남아 있다** — 정본이 코드를
따라오지 않으면 다음 사람이 D-31을 근거로 다시 지운다(PLACEHOLDERS.md §3b "잔여").

### 되살린 범위

v1.0.1 §4.2(P2 사전 설문)·§7.1(측정)과 그 자산 하나뿐이다. v1.0.1의 다른 폐기 항목
(williams · normalization · no_reply/end 3분기 · 12문항 2블록 · downstream 7메뉴 · cue form)은
**그대로 사용 금지**다. CLAUDE.md의 Legacy 참조 규칙에서 `assets/presurvey.py` 한 줄만 뺐다.

| 층 | 파일 | 성격 |
|---|---|---|
| 자산 | `fixtures/presurvey_items_v0.json` | 태그 `v1.0.1-within`에서 **한 글자도 고치지 않고** 복원(12문항) |
| 로더 | `backend/app/assets/presurvey.py` | v1 로직 유지 + v2 규약으로 개조 — `ASSET_PATH` 단일 상수 → `ASSET_CANDIDATES`(`_v1`→`_v0`)·`is_placeholder`(`rating_items` 패턴) |
| 상태 | `SsState.PRESURVEY = "SS01S"` | `SS_NEXT` 사슬에 CONSENT와 CHECKPOINT 사이로 삽입 |
| 화면 | **P1S** | 동의(P1) 직후 · checkpoint(P2) 직전 |
| API | `POST /api/presurvey` | 전 문항 필수, 위치로만 오간다(NT-05) |
| 저장 | `presurvey_responses` | v1.0.1 §8.1 정의 그대로 + `(session_id, item_id)` unique |
| export | `presurvey.csv` | 문항 1행. trajectory의 열이 **아니다** |
| 게이트 | `freeze.blockers()` PH-01 | 자산이 `_v0`이면 모집 게이트에 뜬다 |

### 명세에 없어 내가 정한 것

| 결정 | 이유 | 되돌리기 |
|---|---|---|
| 화면 ID **`P1S`** · 상태 **`SS01S`** (재번호 아님) | v1.0.1의 P2는 v2.0에서 checkpoint가 차지했다. 화면 하나를 끼우자고 SS02–SS10·P2–P12를 한 칸씩 밀면 명세서 §0.2·§3.1, 콘솔, rewind 대상(P8–P11), 부록 C 테스트 표, `PROGRESS`의 과거 기록이 전부 갈라진다. 진행 순위는 번호가 아니라 `SS_NEXT` 사슬이 정하므로 삽입만으로 성립한다 | 재번호가 필요하면 `_SS_SCREEN`·`SS_NEXT`·프런트 switch 세 곳 |
| 사전설문 문안 3건 `[제안]` 신설 (`PRESURVEY_INTRO`·`SUBMIT_BUTTON`·`INCOMPLETE`) | v1.0.1 §4.2가 화면 문안을 주지 않았다. 다른 화면과 같은 규율로 **서버 자산**에 두고, 안내문은 Study 1 사건을 건드리지 않는다 — 이 화면은 checkpoint **앞**이라 사건을 떠올리게 하면 §4.2·§4.3의 선호 재활성화 금지와 같은 문제가 된다(`test_presurvey_copy_is_back_and_stays_neutral`이 어휘를 건다) | 문안 교체 |
| PH-01을 **모집 게이트에 다시 올림** | 자산이 `_v0` 초안이다. 되살린 화면에 자산 규율(문항 원문 미착지 = 게이트)을 걸지 않으면, 초안 문항으로 본 모집이 시작될 수 있다 | `freeze.blockers()`의 PH-01 블록 삭제 |
| export를 **별도 파일**로(`presurvey.csv`) | participant characterization 전용이라 focal trajectory 행에 붙일 이유가 없고, 붙이면 열 수가 문항 수를 따라 흔들린다. 역채점은 적용하지 않고 `reverse` 플래그만 실어 보낸다 — export가 미리 뒤집으면 원자료가 사라진다 | `trajectory` 행에 열로 병합 |
| 복수 선택에서 마지막 항목을 지우면 **미응답으로 되돌림**(프런트) | 빈 배열을 응답으로 올리면 서버가 400(선택지 1개 이상)을 주는데, 화면은 왜 막혔는지 설명하지 못한다 | `Intro.tsx`의 `toggleMulti` |

### evidence boundary

사전설문 응답은 **어떤 LLM 호출에도 들어가지 않는다**(§1.2 · v1.0.1 NT-01). 두 겹으로 건다.

- 정적 — `llm/`이 `app.assets.presurvey`를 직접·전이적으로 import하지 못한다
  (`test_evidence_boundary_static.py`, NT-04와 같은 폭).
- 런타임 — 세션을 끝까지 돌린 뒤 AI2·checker에 나간 문자열 전문에서 **문항 문면·문항 ID·
  선택지 라벨** 전수를 찾는다(`test_presurvey_never_reaches_any_llm_payload`). sidecar처럼
  sentinel을 심을 수 없어서(응답이 자산의 선택지 집합에 갇혀 있다) 평정·pairwise와 같은
  방식을 썼다.

### 명세서 개정 · PH-01 착지 (같은 날 오후)

**① 명세서 v2.0을 사전설문 포함으로 개정했다.** 코드가 정본을 앞서 있는 상태를 닫은 것이다 —
정본이 따라오지 않으면 다음 사람이 D-31을 근거로 다시 지운다. 결정 번호는 **D-44**다
(D-43은 `prohibited_inference` 재명세가 이미 쓰고 있어서 임시로 붙였던 D-43 표기 47건을 옮겼다).

| 절 | 내용 |
|---|---|
| 머리말·§0.2·§0.3 | 개정 고지 · P화면 14종(P0–P12 + P1S) · "사전 설문이 없다" 철회 |
| §1.2 | 방화벽 표에 「사전 설문 응답」행 — AI2 ❌ / checker ❌ / 참가자 제출 화면만 |
| §2.3·§3.1 | 폴더 트리 복원 · SS01S 행 + **번호를 밀지 않은 이유** |
| **§4.1S·§7.0 신설** | 화면 전문 / 측정 절 |
| §8.1·§8.2·§9.3·§10.5·§11.1·§11.2 | 테이블·API·국외 이전 제외·동결 지문·V2-0 grep 주석·DoD |
| 부록 B·C·D.1·E·G·H | 데이터 사전 · **NT-05 부활 + NT-46 신설** · QA 체크리스트 · D-44 결정행 · 처분표 DROP→RESTORE · H의 삭제 지시 3건에 ↩ |

부록 H는 **이미 실행이 끝난 지시서**라 지우지 않고 ↩로 표시했다. 나머지 삭제 항목은 그대로
유효해야 하고, 통째로 무효화하면 그 구분이 사라진다.

명세에 NT-46을 적었으니 CI에 실물이 있어야 한다 — 통합 테스트 7건을 붙였다(전이 · 건너뛰기
409 · 전 문항 필수 400에 행 0건 · 유형별 값 검증 · 문항 ID로 저장 · 재제출 idempotent ·
payload 메타 미노출).

**② PH-01이 닫혔다 (PI 확인).** `fixtures/presurvey_items_v1.json` — `_v0` 초안 12문항을
**문면 변경 0건**으로 승격했고, 코드 변경도 0건이다(로더가 `_v1`을 먼저 본다 — PH-06·07과
같은 경로). 모집 게이트 4건 → **3건**(PH-03 · PH-IRB-1 · PH-IRB-2).

PI 확정 2건을 파일 `_pi_decisions`와 명세 §4.1S에 남겼다.
- **순서 프라이밍 기각** — ②(빗나갔을 때의 평소 대응)가 P2 직전에 correction repertoire를
  활성화한다는 검토 의견은 채택하지 않는다. 화면 위치는 그대로다.
- **회상 창 정합** — 모집이 최근 6개월 이내 사건을 조건으로 걸었으므로 빈도 문항의 "최근
  6개월"은 표본과 맞는다.

`_v0`은 **지우지 않았다**. `_v1`이 사라지면 로더가 내려가면서 게이트가 다시 울리는 것이 회귀
감지 장치다 — `test_freeze.py`의 PH-01 검사도 삭제가 아니라 **방향만 뒤집었다**(PH-06·07과
같은 처리).

### 문면 관찰 4건 — 미반영 (기록)

승격이 문면 변경 0건이었으므로 검토에서 나온 아래 4건은 그대로 남아 있다. 고치기로 하면
`_v1` 파일의 `text`만 수정하면 되고 게이트는 다시 열리지 않는다(§1.4 — 모집 전 변경).

| # | 관찰 | 성격 |
|---|---|---|
| 1 | misfit 문항의 호칭 **"회원님"** | 연구 문안 전체에서 유일 1회(다른 곳은 "참여자님"·무주어 존댓말) |
| 2 | misfit 5지에 **"그 외" 없음 + 전 문항 필수** | 5개 중 어느 것도 아닌 참가자가 강제 선택된다(§7.4 downstream에는 `other`가 있다) |
| 3 | `disclosure_1` ↔ `ai_use_freq_personal_concern` 문면 중복 | "개인적인 고민이나 신경 쓰이는 일"이 verbatim |
| 4 | DDI 발췌 근거 미기록 | 12문항 중 1·2·3·10을 고른 이유 / ddi_1이 원문 "my friends"를 "가까운 사람"으로 넓힌 사실 |

### 남은 일

1. **PH-P-7 (신설 — 논문 역반영)**: 신 §6–7(정본)에 사전 설문 절이 **없다**. 자산이 가리키는
   §7.4는 **구 초안**이고 구 §6–7은 더 이상 정본이 아니다(명세 머리말). 모집 게이트는 아니지만,
   논문에 절이 서기 전에는 "출처를 논문이 답하지 못하는 측정"이 남는다. 함께: 신 §7.11의 턴
   수준 코드 `new support-relevant disclosure`와 사전설문의 성향 `disclosure_1·2`가 같은 단어를 쓴다.
2. 문면 관찰 4건의 반영 여부 (PI).

### 테스트

876 passed → **921 passed** (40 skipped). 기준선 불감소.

---

## 파일럿 조정 ⑤ (§10.3, P00 QA 워크스루 뒤) — 2026-08-28

**P3 재진입 타이머를 없앴다 (D-46).** 30초 버튼 비활성 · 60초 "진행하셔도 됩니다" 보조문 ·
그 DEV_MODE 면제를 함께 제거했다. 진행 버튼은 처음부터 활성이다.

- **화면이 잡아 둘 이유가 없다.** 모든 세션이 연구자 진행이고 문안도 "연구자의 안내가
  있으면 아래 버튼을 눌러 진행합니다"라고 말한다 — 회상 속도를 정하는 주체가 이미 사람이다.
  화면이 30초를 강제하면 이미 떠올린 참가자에게는 회상이 아니라 대기가 되고, 그 대기가
  사건 재진입의 온도를 오히려 떨어뜨린다. 절차(구두 회상 안내)는 그대로 남는다.
- **DEV_MODE 분기가 같이 사라진 게 부수 이득이다.** 종전 구조는 "실세션 30/60 · 시연 0"이라
  P3만 구성에 따라 다르게 동작했다. 이제 두 구성이 같은 화면이다 — QA에서 본 것이 참가자가
  보는 것과 같아진다.
- **cohort 경계**: P23·P08·P05·P15는 30초 대기 화면을 거쳤고 이후 참가자는 거치지 않는다.
  강제 대기만 사라진 것이라 측정 항목에는 변화가 없다.

### 손댄 곳

| 층 | 파일 | 내용 |
|---|---|---|
| 자산 | `screen_copy.py` | `REENTRY_MIN_SECONDS`·`REENTRY_HINT_SECONDS`·`REENTRY_READY_NOTICE` **삭제**. `REENTRY_NOTICE` 문안은 한 글자도 안 바뀐다 |
| API | `state_payload.py` | P3 payload = `{"notice": …}` 하나. 임계값·면제 로직 삭제 |
| 화면 | `screens/Focal.tsx` `Reentry` | `elapsed` 타이머·보조문·`disabled` 제거 |
| 테스트 | `test_dev_reset.py` | `test_reentry_timer_is_waived_only_in_dev_mode` → `test_reentry_has_no_timer_in_either_configuration`. 삭제된 상수가 되살아나면 실패한다 |
| 명세 | §0.2 · §0.5 · §4.3 · §10.3(조정 ⑤) · 부록 D.1 · E.1(D-46) · E.2 | |

### 테스트

**923 passed** (38 skipped). 기준선 불감소. `npm run build` 통과.

---

## 파일럿 조정 ④ (§10.3, P05 dossier 문안 검토 중) — 2026-08-28

**AI1 무대지시 문안을 행위 중립으로 바꿨다 (D-45).** `(그 후 적절한 추천 제공)` →
**`(그 후 적절한 답변 제공)`**. D-40의 나머지는 한 글자도 손대지 않았다 — 붙는 자리(u 바로
뒤) · 회색 · AI2 payload와 `turns.ai1` 동반 · `assemble()`/hash/`stimuli_meta` 불변.

- **P05만의 예외가 아니라 문안의 과적합이었다.** u가 약속하는 행위는 사건마다 갈린다:
  비교(P00) · 판단(P05·P08) · 재검토(P15) · 범위 좁히기(P23) · 추천(P10). 착지된 6종 중
  "추천"이 맞는 건 P10 하나뿐이라, 나머지에서는 무대지시가 자극과 어긋났다. dossier별 예외를
  두면 P00·P08·P15에서 같은 질문이 세 번 더 온다.
- **무대지시가 해야 하는 일은 행위 유형과 무관하다.** D-40의 목적은 "…해 보겠습니다"라는
  선언이 "하겠다고만 하고 안 한다"로 읽히는 것을 막는 것이고, 그러려면 "약속한 것이 실제로
  이어졌다"는 신호만 있으면 된다.
- **dossier별 `uptake_note` 필드는 만들지 않았다** [내가 정한 것 아님 — PI 선택]. 맞춤도는
  높지만 dossier마다 문안 QC 항목과 계약 테스트가 하나씩 늘고, "u 안에 실제 내용을 적지
  않는다" 규칙이 새는 통로가 생긴다. D-40의 "전 참가자 공통 한 문자열" 성질을 유지했다.
- **cohort 경계가 생기지 않는다.** 진행된 실세션 P23·P08은 둘 다 D-40 채택(조정 ②) 이전이라
  무대지시를 아예 보지 않았고, D-40 이후 진행된 세션은 아직 없다. 즉 **현재 문안을 본 참가자는
  0명**이고, 지금이 cohort 분할 비용 0으로 고칠 수 있는 마지막 시점이었다.
- **자산은 불변이다.** `assemble()` 기준이라 `stimulus_hash`·`stimuli_meta`·lock hash가 그대로다
  → 이미 lock된 P00·P05·P08·P10·P15·P23 재lock 없음. §10.5 freeze의 `assets_hash`도 영향 없다.

### 손댄 곳

| 층 | 파일 | 내용 |
|---|---|---|
| 코드 | `backend/app/assets/dossier_loader.py` | `UPTAKE_NOTE` 상수 1줄 + 근거 주석. 나머지 코드·테스트는 전부 이 상수를 참조하므로 문자열 하드코딩 수정 0건 |
| 명세 | `docs/구현명세서_v2.0.md` | §1.2(AI1 정의 한 곳) · §4.4(무대지시 문단 + 행위 중립 근거) · §10.3(조정 ④) · 부록 E.1(D-40 행 개정 + **D-45 신설**) · E.2(변경 이력) |
| 자산 문서 | `dossiers/README.md` §2 | 작성 규칙 — 행위 유형과 무관하게 같은 한 줄이 붙는다 |
| 주석 | `backend/app/api/focal.py` · `tests/integration/test_evidence_boundary.py` | "추천을 다시 한다" 설명문을 "답변"으로 |

### 테스트

**923 passed** (38 skipped). 기준선 불감소. 문자열 계약은 전부 `dossier_loader.UPTAKE_NOTE`
참조라 문안 교체에 테스트 수정이 필요 없었다 — 그 자체가 D-40의 "정의가 한 곳" 설계가
작동한다는 확인이다.

## 파일럿 조정 ⑥ (§10.3, P14·P17 dossier 문안 검토 중) — 2026-08-29

**무대지시 문안을 A-level별 3종으로 갈랐다 (D-47).** D-40·D-45의 나머지는 한 글자도 손대지
않았다 — 붙는 자리(u 바로 뒤, C4는 q 앞) · 회색 · AI2 payload와 `turns.ai1` 동반 ·
`assemble()`/hash/`stimuli_meta` 불변.

| a_level | 무대지시 | 종전 |
|---|---|---|
| A2 | `(그 후 적절한 답변 제공)` | 같음 (현행 유지) |
| A1 | `(이후 응답은 위 범위 안에서 이어짐)` | A2와 같은 줄이 붙었다 |
| A0 | (없음 — 빈 문자열) | A2와 같은 줄이 붙었다 |

- **A1에서 문안이 자극과 모순됐다.** A1의 uptake는 확장의 중단이라 제공되는 것이 없다.
  P14의 u는 "…여기서 일단 멈추고 **그대로 두겠습니다**", P17은 "…**더 이어가지 않겠습니다**"로
  끝나는데, 거기에 "그 후 적절한 답변 제공"이 붙어 있었다. D-45가 "추천 → 답변"으로 고친 것은
  **행위 유형**의 과적합이었고, 이번 것은 **행위의 유무**다.
- **실제로 가르는 성질은 a_level이 아니라 "u가 후속 행위를 선언했는가"다** [기록해 둘 값].
  A1 6건 중 P14·P17·P24는 순수 정지형이고 P03·P12·P23은 "다시 보겠습니다"류로 후속을
  선언한다. 그래도 범위한정형 문안이 후자와도 양립하므로 a_level 분기로 실질 오작동은 없다 —
  기준이 정확해서가 아니라 문구가 넉넉해서 맞는 것이다.
- **§1.5-4에 예외를 명시했다** [PI 결정]. "A-level을 조건·분기·검증의 입력으로 쓰면 결함"이라는
  조항에 표시 문안 선택 1건을 명시적으로 뚫었다. 값 자체는 참가자 화면·LLM 경로 어디에도
  나가지 않고(선택된 문자열만 나간다), 읽는 지점은 `UPTAKE_NOTE_BY_A_LEVEL` 한 곳이다.
  대안이었던 `stimulus.uptake_note_kind` 자산 필드는 규율이 더 깨끗하지만 dossier 내용이
  바뀌어 lock된 13건 재lock + 이미 진행한 4명의 `participants.dossier_hash` 불일치를 만든다 —
  그 비용 때문에 채택하지 않았다(D-45의 "dossier별 문안 금지"도 그대로 유지된다).
- **A0은 무표시다** [PI 결정]. "(해당 없음)" 같은 placeholder를 붙이지 않는다 — 참가자 화면에
  연구 어휘가 들어가고 그 자체가 사건 분류의 단서가 된다. 착지된 실값 dossier에 A0은 아직
  없지만 schema_dummy 8건이 A0이라 경로는 테스트로 덮인다.
- **cohort 경계가 생기지 않는다.** D-40 채택(조정 ②) 이후 focal을 지난 세션이 없어 무대지시를
  본 참가자가 **0명**이다. 자산·hash 불변이라 재lock도 없다.

### 손댄 곳

| 층 | 파일 | 내용 |
|---|---|---|
| 코드 | `backend/app/assets/dossier_loader.py` | `UPTAKE_NOTE` → `UPTAKE_NOTE_BY_A_LEVEL` 표 + `Dossier.uptake_note` 속성. `_parts()`는 빈 문면을 끼우지 않는다(공백 하나가 남는다). `has_uptake_note()`는 "u가 있고 문면이 있을 때"로 바뀌었다 |
| 코드 | `backend/app/api/state_payload.py` | `ai1_note` 6곳이 상수 대신 `dossier.uptake_note`를 쓴다. `_ratings_view()`는 문면을 인자로 받는다(P8에는 dossier가 없었다) |
| 프런트 | — | **변경 0**. `StimulusText`가 서버가 준 문면을 본문에서 찾아 회색을 칠하는 구조라, 빈 문자열이면 그냥 본문을 그린다 |
| 명세 | `docs/구현명세서_v2.0.md` | §1.2(두 행) · **§1.5-4(예외 폭)** · §4.4(문안 표) · §5.4 · §10.3(조정 ⑥) · 부록 C(NT-47) · E.1(D-45 행 + **D-47 신설**) · E.2 |
| 자산 문서 | `dossiers/README.md` §2 | 작성 규칙 — 문안은 `a_level`이 고르고 dossier에 문안 필드를 두지 않는다 |

### 테스트

**970 passed** (16 skipped). 개정 전 938 passed에서 32건 증가이고 **기준선 불감소**다.
신설은 NT-47 — 자산 계약 4건(표가 `A_LEVELS`를 정확히 덮음 · 문안 3종 정본 · dossier별
`uptake_note`가 자기 a_level의 값 · 문면이 R-3·R-4 통과)과 정적 규율 4건(`a_level` 사용처
allowlist **양방향** · `llm/` 부재 · `state_payload` 부재 + `dossier.uptake_note` 경유).

⚠ **전체 green이 아니다.** 개정 **전에도 같은 7건**이 실패한다 — 이번 변경과 무관한 착지 중
자산 문제다: NT-44 5건(P02·P06·P09·P13·P24 `prohibited_inference` 작성 규칙 미준수) ·
NT-45 1건(P19 문면의 8자 조각 `correcti`가 checker 프롬프트의 `correction_ignored`와 우연히
일치) · `test_asset_import` 1건(볼륨 해석). 커밋 전에 이 7건을 먼저 닫아야 한다.

---

## 파일럿 조정 ⑦ (§10.3, P15 세션 AI2 실적 검토 뒤) — 2026-08-29

**AI2 사다리를 라운드로 바꿨다 (D-48).** 초안 2개(최초 + 재생성 1회) → **R1(후보 3 병렬) →
R2(후보 3 병렬 + 수정 요청) → R3(후보 1, 최대 제약) → neutral_fallback**.

**증상: 실참가자 4명 중 3명이 `neutral_fallback`으로 끝났다.** D-43(조정 ③) 이후에도
P15가 같은 자리에 착지했고, 참가자가 화면에서 "무슨말이야 그게"라고 되물었다. DB를 열어 보니
**실패의 원인이 시도마다 달랐다**:

| 시도 | 판정 |
|---|---|
| attempt 1 | checker `unsupported_inference` — "이미 …방향을 잡아가고 계신 것 같은데요"(사용자는 고민이라고만 말했다) |
| attempt 2 | **R-3 질문 2개** — checker는 아예 호출되지 않았다 |

즉 탐지기 하나를 손봐도 남는 구조였다. 그리고 재생성 안내가 위반 **유형 문자열**만 보내고
있어서, 규칙 위반이면 모델에게 가는 문구가 문자 그대로 `"R-3"`이었다(전달되는 정보 0).

**① 라운드 + 병렬 후보.** 통과율이 가장 낮은 사건(P08)의 시도당 통과율을 replay에서 역산하면
q≈0.43이다. 2시도면 fallback 32%, 3후보 2라운드면 3.5%다. **직렬로 늘리면 시간이 먼저
터진다**(한 후보 12–17초) — 그래서 라운드 안에서는 `asyncio.gather`로 뽑고 라운드 사이에서만
정보를 넘긴다. 선택은 **통과 후보 중 인덱스 최소**이고 내용 비교는 하지 않는다(§1.5-8).

**② R3 최대 제약 모드(부록 A.1b 신설).** 후보를 더 뽑아도 같은 벽에 부딪히는 사건이 있다
(P08처럼 사건 자체가 제3자에 대해 말해야 하는 경우). R3은 프롬프트를 바꿔 출력 공간을 좁힌다 —
질문 0개면 R-3이, 사용자에 대한 서술이 없으면 `unsupported_inference`가, 맥락 안에서만 쓰면
`expansion`이 성립할 수 없다. **"하겠다는 말만 남기지 않는다" 조항이 핵심이다** — 없으면 R3이
곧 fallback과 같아진다. A.1은 한 글자도 건드리지 않았다.

**③ 재생성 피드백 수리.** 유형별 **사람이 읽는 지시** + checker **span**을 싣는다. span을
실어도 되는 근거는 구조적이다 — checker는 R-1을 포함한 규칙 계층을 통과한 초안에만 도므로 그
초안에 금지 문자열이 8자 이상 남아 있을 수 없다. **규칙 위반 쪽 `detail`은 어떤 경우에도
싣지 않는다**(라벨뿐이라도 그 규율을 흐리지 않는다).

**④ 벽시계 상한 45초 · `LLM_CONCURRENCY` 2→8.** 시도 수만으로는 §9.1이 닫히지 않는다. 상한은
두 곳에서 건다: 남은 예산으로 라운드를 끝낼 수 없으면(<10초) 시작하지 않고, 호출 타임아웃을
잔여로 깎는다. 동시성을 안 올리면 후보 3건이 세마포어에서 직렬화돼 라운드가 3배로 늘고
45초 안에 R2·R3에 닿지 못한다(연구자 2인 병행이면 3×2 + checker 여유가 필요하다).

**명세에 없어 내가 정한 것**

| 결정 | 이유 | 되돌리기 |
|---|---|---|
| 예산이 checker를 못 돌릴 만큼(<3초) 남으면 **checker를 건너뛰고 규칙 계층만으로 판정**한다(`checker_skipped`) | 호출하지 않은 것도 판정 불능이고, §9.1은 판정 불능을 이미 "규칙 계층만으로 진행"으로 처리한다. 여기서 fallback으로 보내면 "느린 제공사 = 캔 문구"가 되어 PI가 지시한 1순위(fallback 회피)와 정면으로 어긋난다 | `_run_round`의 `MIN_CHECKER_SECONDS` 분기 삭제 |
| checker를 **라운드 안에서 동시에** 부른다(규칙 통과 후보 전부) | 순차면 후보 3건에 7–8초가 들어 45초 예산에서 R3이 사라진다. 동시면 2–3초다. validator 호출이 늘지만 단가·지연이 작다 | `zip` 루프를 "첫 통과까지만"으로 바꾸기 |
| 후보를 전부 `generations`에 남긴다(쓰이지 않은 후보 포함) | §8.4는 호출 1건 = `llm_calls` 1행을 요구하고, 그 행은 `generation_id`를 참조한다. 남기지 않으면 실제로 부른 호출이 기록에서 사라진다 | — |
| `attempt`를 **라운드 번호**로 재해석(스키마 변경 없음) | 후보 열을 새로 만들면 Postgres ALTER가 필요한데 Alembic 미도입이라 schema 단위 전환이 규율이다(§2.4). 한 라운드의 후보는 같은 `attempt` + `created_at` 순서로 복원된다 | `candidate` 열 신설 |
| A.1b temperature를 A.1과 같은 0.4로 둔다 | R3이 좁히는 것은 **문면**이지 파라미터가 아니다. 0.2로 낮추면 §6.6의 "AI2 temperature 0.4 [파일럿 확정]"이 둘로 갈린다 | `prompt_config`의 블록 파라미터 |

**아직 하지 않은 것** — 이전 대화에서 논의한 **B(A.1에 원칙 6 신설)** 와 **C(작성 규칙 ⑨ +
A.2 대조 예시)** 는 넣지 않았다. 둘 다 **PI 승인 lock된 프롬프트의 문면**을 바꾸는 일이라
문안 확정이 필요하다. R3의 6번 조항("아직 정해지지 않은 것을 정해진 것처럼 쓰지 않는다")이
B의 효과를 R3 한정으로 먼저 넣어 둔 형태다.

### 손댄 곳

| 층 | 파일 | 내용 |
|---|---|---|
| 코드 | `llm/gateway/calls.py` | **왕복(`dispatch_model`)과 기록(`record_call`) 분리**. `AsyncSession`은 동시 사용이 안전하지 않아, 나누지 않으면 후보 3건 `gather`에서 "another operation is in progress"로 세션이 깨진다. `timeout_override_ms`로 잔여 예산을 반영 |
| 코드 | `llm/checker.py` | 같은 이유로 `dispatch`/`absorb` 분리 + `skipped_verdict()`(호출 자체를 안 한 경우) |
| 코드 | `llm/ai2_pipeline.py` | 전면 재작성 — `_run_round`·`_Candidate`·`_RoundResult`·사다리·벽시계 |
| 코드 | `llm/context.py` | `render_feedback()` 신설, `build_ai2_payload(..., feedback, prompt_key)` |
| 자산 | `prompts/prompt_config_v2.json` | `ai2_constrained` 블록 신설, `version` v2 → **v2.1**, `prompt_hash` 재계산 |
| 설정 | `core/config.py` · `.env` · `.env.example` | `llm_concurrency` 2→8, `ai2_deadline_seconds` 45 신설 |
| 명세 | `docs/구현명세서_v2.0.md` | §0.4 · §0.5 · §2.4 · §6.1(전면) · §6.4 · §10.3(조정 ⑦) · 부록 **A.1b 신설** · C(NT-48) · E.1(D-48) · E.2 |

### 테스트

**976 passed** (D-47 시점 970 → +6, 기준선 불감소). NT-48 신설 — 라운드 안에서 후보 하나의
규칙 위반이 라운드를 소모하지 않음 · R2 피드백에 규칙 ID가 아니라 지시문과 span이 실림 ·
R3이 A.1b로 1회 돌아 fallback을 막음 · 예산 소진 시 새 라운드 미시작 · 예산 소진 시 checker
생략 후 규칙 계층 판정(fallback 아님) · 실제 요청 타임아웃이 45초 이내.

⚠ 남은 7건은 이 변경 이전부터 실패하던 착지 중 자산 문제다(NT-44 5건 · NT-45 1건 ·
볼륨 해석 1건). **PI 지시로 이번 배포에서는 보류한다.**

---

## 세션 후 dossier 수정 4건 — 유지 결정과 기록 — 2026-08-29

**§1.4를 어겼다.** "lock된 dossier는 해당 참가자 세션 시작 후 변경 금지"인데, NT-44 작성 규칙
정리와 `ai_visible` 코더 주석 제거를 하면서 **이미 세션이 끝난 넷을 함께 고쳤다**. 볼륨에도
반입해 재기동까지 마친 뒤에야 프로덕션 DB를 조회하고 알았다 — 로컬 sqlite에는 초기 5건만
있었고 실제 세션은 **10명**이었다(P23·P08·P05·P15·P17·P03·P12·P02·P19·P13).

| dossier | 세션 | 바뀐 층 | 세션 당시 hash | 현재 |
|---|---|---|---|---|
| **P17** | done 08-28 05:02 | **`ai_visible.problematic_ai_response`** | `addf2973cc96…` | `p17_v2` |
| **P19** | done 08-28 11:23 | **`ai_visible.problematic_ai_response`** | `16d0181bbecd…` | `p19_v2` |
| P02 | done 08-28 09:28 | `evidence_code.prohibited_inference` | `703b651edd5a…` | `p02_v2` |
| P13 | done 08-28 12:18 | `evidence_code.prohibited_inference` | `883ea6be1ba3…` | `p13_v2` |

- **P02·P13은 참가자 화면과 무관하다.** `prohibited_inference`는 checker 입력 전용이고
  (§1.2), 참가자는 이 층을 본 적이 없다. 바뀐 것은 괄호 주석 제거(P02)와 문말 마침표
  제거(P13)뿐이다.
- **P17·P19는 참가자가 읽은 문면이다.** P17은 코더 주석(`도입부 — 요약:` ·
  `← problematized component`)을 벗긴 것이라 실질 내용이 같다. **P19는 다르다** — 회상된
  이유 두 개 중 `(b) 지금 상황을 봤을 때(내용 미회상)`가 통째로 빠졌다. 표기 정리가 아니라
  **내용 변경**이고, 그 참가자의 체크포인트 카드에는 이유가 둘이었다.
- **콘솔·export는 수정본을 렌더한다.** `ai_visible`은 파일에서 live로 읽히므로(overlay는
  참가자 수정분만) R2·R3와 export가 지금 보여주는 문면은 그 넷이 본 것과 다르다. 참가자가
  본 **AI1 자극**은 영향이 없다 — `turns.ai1`(암호화)과 `focal_runs.stimulus_hash`에 따로
  남아 있고 `stimulus` 층은 건드리지 않았다.

**PI 결정: 복원하지 않고 수정본으로 간다** (2026-08-29). 대신 갈라진 지점을 기계가 알아볼 수
있게 **`version`을 `_v1` → `_v2`로 올렸다** — D-43 때 P08·P23을 `_v2`/`_v3`로 올린 것과 같은
장치다. `participants.dossier_version`(`*_v1`)과 파일(`*_v2`)이 다르면 그 세션은 세션 후
수정된 dossier를 가진다. 분석에서 그 넷의 `ai_visible` 인용이 필요하면 아래 복원 경로를 쓴다.

**복원 경로(쓰지 않기로 했지만 남아 있다).** 볼륨의 미사용 중첩 디렉터리
`/dossiers/dossiers/`에 예전 사본이 있고 **P02·P17·P19는 hash가 `participants.dossier_hash`와
정확히 일치**한다 = 세션 당시 원본이다. **P13만 복원 불가**다(어디에도 없다). P13의 두 번째
수정은 볼륨본과 대조해 `prohibited_inference`만 바뀐 것을 확인했지만, 첫 번째 수정 구간은
증명하지 못했다 — 코더 주석 스캔에 P13이 걸린 적이 없다는 정황뿐이다.
**⚠ `/dossiers/dossiers/`를 지우지 마라.** 지금 유일한 세션 당시 사본이다.

**왜 늦게 알았나 — 재발 방지.** `lock_dossier.py`는 자산 계약만 본다. DB를 모르므로 "이
참가자는 이미 세션이 돌았다"를 말해 줄 수 없고, 나도 로컬 sqlite(5건)를 보고 "세션 있는
참가자는 안 건드렸다"고 판단했다. **실제 세션 목록은 프로덕션 DB에만 있다.** 자산을 고치기
전에 `participants`를 조회하는 절차가 없으면 같은 사고가 다시 난다 — 반입 스크립트
(`stage_volume_assets.py`)에 "세션이 있는 참가자의 dossier hash가 DB 기록과 다르면 경고"를
붙이는 것이 정공법이다(미구현).

---

---

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
