# PLACEHOLDERS.md — 미확정 항목 레지스트리 (study2-enactment v2.0, focal-between)

정본은 `docs/구현명세서_v2.0.md`의 **부록 E.4**(`<TODO>` 색인)·**부록 F**(`[확인 N]`)·**§0.5**(`[파일럿 확정]`)다.
이 문서는 그 색인에 **① 코드상 빈 자리 ② v1.0.1(within) 구현 대조 결과 ③ 해소 경로**를 붙인 작업용 레지스트리다.
명세서와 충돌하면 명세서가 우선한다. **v1.0.1의 PLACEHOLDERS.md는 이 문서로 대체되었다**(2026-08-20).

**상태 범례** — ⬜ 미해소 · ◐ 부분 해소(자산·문안이 어딘가 존재하고 착지·승인만 남음) · ✅ 해소(교체 커밋 완료) · ✂ v1.0.1 항목 중 설계 전환으로 **소멸**(기록만 남김)

**v1.0.1 대조 열의 의미**
- **승계** — v1.0.1 코드·자산을 그대로(또는 소폭 수정으로) 쓴다.
- **개조** — 패턴은 쓰되 내용을 v2.0 기준으로 다시 쓴다.
- **사용 금지** — 신 설계가 명시적으로 폐기했다. 가져오면 설계 오염이다(Williams·normalization·presurvey·no_reply/end·12문항 2블록·downstream 7메뉴·carryover 태깅·cue form).
- **선례 없음** — v1.0.1에 대응물이 없다(v2.0 고유).

---

## 0. 한눈에 — 지금 무엇이 막혀 있는가

**코드로 닫을 수 있는 항목은 전부 닫혔다.** V2-0~V2-4 전환도, PI 결정 5건(PH-09·10·11·13·14)도, 문항 자산 2건(PH-06·07)도 끝났다. 남은 것은 **연구팀이 쓰는 자산 · IRB 승인 · 외부 실측**뿐이며, 개발자가 혼자 진행할 수 있는 항목은 PH-04 하나다.

```bash
DEV_MODE=true ./backend/.venv/bin/python scripts/freeze_study_version.py --check
#   모집 게이트 4건(2026-08-25 현재): PH-03 · PH-08 · PH-IRB-1 · PH-IRB-2
```

| 분류 | 건수 | 성격 | 본 모집 게이트(§11.2) |
|---|---|---|---|
| 자산 — 연구팀 작성 (PH-03·03b·08) | 3 | dossier 24건(R/U/Q·evidence code)·locus 목록·배정표 | PH-03·PH-08 ⛔ |
| ~~자산 — 문항 문면 (PH-06·07)~~ | 0 | **2026-08-24 `_v1` 착지 — 추천안 문면 확정, 게이트 소멸**(§3) | — ✅ |
| ~~설계 잔여 결정 — PI (PH-09·10·11·13·14)~~ | 0 | **2026-08-24 전건 승인 — 전부 기본값 확정**(§4) | — ✅ |
| 프롬프트 lock (PH-12) | 1 | A.1·A.2 v2 PI 승인 | — (실모델 실행 선행 조건) |
| IRB·문안 (PH-IRB-1~7) | 7 | IRB 승인 | PH-IRB-1~7 ⛔ |
| 운영·배포 (PH-04 ◐, 확인 1–5) | 6 | PH-04 절차 확정(§7) — 남은 5건은 계정 실측 | — |
| `[파일럿 확정]` 파라미터 | 12 | soft launch 1회 조정 창 | — |
| `[제안]` 화면 문안 | 28 | PI 승인 (코드 변경 0 예상). PH-09·10·13·14 관련 6건은 `[PI 승인 2026-08-24]`로 전환됨 | — |
| 논문 역반영 (PH-P-1~6) | 6 | 시스템 밖 | — |
| v1.0.1 소멸 항목 (✂) | 4 | 기록 | — |

### 지금 열려 있는 것 — 누가 움직여야 하나

| 주체 | 항목 | 다음 행동 | 막고 있는 것 |
|---|---|---|---|
| **연구팀** | PH-03 · PH-03b | dossier 24건 작성 → 2인 코딩·adjudication → QC → `lock_dossier.py` | 모집 ⛔ · **PH-08의 선행 조건** |
| **연구팀+개발자** | PH-08 | PH-03 완료 후 `make_assignment.py --from-dossiers --seed <사전 기록>` | 모집 ⛔ · 생성 후 변경 금지(§1.4) |
| **IRB** | PH-IRB-1~7 | 제출 → 승인 → 슬롯 3종 치환 → `screen_copy` 교체(§6 5단계) | 모집 ⛔ |
| **PI** | PH-12 | 프롬프트 A.1·A.2 v2 승인·lock | 실모델 fixture([확인 4])의 선행 조건 |
| **개발자** | PH-04 ◐ | 절차·코드 완료(`docs/배포_자산_반입_v1.md`). 실제 반입 시 호스트 CLI 문법만 실측 | — |
| **개발자** | [확인 1~5] | 모델 슬러그·단가 재실측, OpenRouter 보존 정책, checker 비용, Zoom | [확인 3]은 동의서 ④ 문안에 물려 있다 |
| **연구팀** | PH-IRB-3 부속 | 상담 기관 3곳 목록 확정 | IRB 첨부물 |
| — | `[파일럿 확정]` 12 | soft launch 1회 조정 창 | — |
| — | PH-P-1~6 | 논문 역반영 — 시스템 밖 | — |

착지 순서 권고: **PH-IRB(제출) → PH-03(dossier 실값·lock) → PH-08(배정표 생성·동결) → PH-04(반입) → PH-12(프롬프트 lock) → 실모델 fixture([확인 4]) → soft launch → 설계 동결(§10.5)**.
~~V2-0~V2-4 전환~~·~~PH-06·07(문항)~~·~~PH-09·10·11·13·14(PI 결정)~~은 완료됐다.

---

## 1. 요약 표

| ID | 유형 | 무엇이 비어 있나 | 코드 위치 (V2 전환 후 기준) | v1.0.1 대조 | 해소 주체 | 상태 |
|---|---|---|---|---|---|---|
| PH-03 | 자산 | dossier P01–P24(배정 참가자) 실값 — ai_visible(provenance 태그 포함)·researcher_only·evidence_code·**R/U/Q segment**·neutral_fallback·QC 기록·lock (§5.3) | `dossiers/schema_dummy/*` · `backend/app/assets/dossier_loader.py` · `scripts/lock_dossier.py` · `backend/app/core/freeze.py` | **개조** (3층 로더·계약 테스트 패턴 승계, 스키마 v2) | 연구팀 | ⬜ |
| PH-03b | 자산 | `evidence_code.mismatch_locus` 허용값 목록(broad locus) 확정 — 초판: content_depth · affective_tone_intensity · context_memory_use · interpretation · trajectory_timing | `dossier_loader.MISMATCH_LOCI` · `scripts/make_assignment.py`(편중 최소화 입력) | 승계(v1 5종) | 연구팀 | ◐ |
| PH-04 | 운영 | ~~배포 반입 절차~~ → **절차 확정 + 코드 구멍 2건 수정**(`docs/배포_자산_반입_v1.md`). 볼륨 오버레이 방식, `--check`에 「자산 출처」 블록 신설. 남은 것: 호스트 CLI 문법 실측·볼륨 백업 정책 | `files.dossier_search_paths()`(신설) · `files.AssetLocationError`(신설) · `assignment.assignment_path()` · `freeze.asset_sources()`(신설) · `scripts/freeze_study_version.py` | 승계(권고 A: 볼륨) + 오버레이 개조 | 개발자 | ◐ |
| PH-06 | 자산 | ~~focal 5 construct + MC 2 문항 문면~~ → **`fixtures/focal_items_v1.json` 착지(2026-08-24)** — 9문항(GS 2·CE 2·RI 1·CN 1·RCI 1 + MC 2), 문면 출처 『연구7_PH06_focal문항_후보_v1』 추천 세트. gs_1은 record 언어 재작성본, mc_uptake는 referent를 "위 답변"으로 고정. PI 최종 문면 확정 시 v1 파일만 수정(모집 전 가능) | `fixtures/focal_items_v1.json` · `backend/app/assets/rating_items.py` | **개조** (문면 7개 재사용 + 재작성 2 + 신규 1) | 연구팀·PI | ✅ |
| PH-07 | 자산 | ~~pairwise 3 contrast 문항 문면·응답 형식~~ → **`fixtures/pairwise_items_v1.json` 착지(2026-08-24)** — contrast당 3문항(계 9), 전 지칭 문항 `target`/{side} 치환(서술형 지칭 폐기 — PROGRESS 확인 ⑦ 해소), sequence는 paired-stem(동일 문면 양측 평정), 7점 + 이유 구술(F4-ⓒ, PH-11 정합). 문면 출처 『연구7_PH07_pairwise문항_후보_v1』 추천 세트 | `fixtures/pairwise_items_v1.json` · `backend/app/assets/pairwise_items.py` | 선례 없음 | 연구팀·PI | ✅ |
| PH-08 | 자산 | **배정표 실값** `assignments/assignment_v1.json` — strata CSV(24명 a_level·locus) + seed → 생성·제약 검증·로그 (§5.2) | `scripts/make_assignment.py` · `backend/app/core/assignment.py` · `assignments/assignment_dummy.json` | 선례 없음 (Williams는 **사용 금지**) | 연구팀(seed 기록)·개발자 | ⬜ |
| PH-09 | 승인 | ~~이탈 유형 6코드 라벨 + 이유 필수 여부 (§4.7)~~ → **6코드·라벨·표 순서 현행 확정**. 이유 필수 여부만 `[파일럿 확정]` 창에 남는다 | `screen_copy.END_TYPE_OPTIONS` · `core/state_machine.EndType` — `<TODO>` 제거, `[PI 승인 2026-08-24]` | **사용 금지** (구 7메뉴 복원 아님 — 3개 코드명만 우연히 겹침) | PI | ✅ |
| PH-10 | 승인 | ~~대안 노출·pairwise 안내 문안 (§4.9·§4.10)~~ → **명세 [제안] 문안 그대로 확정**. demand 우려 3건은 조건 간 교락이 아니라 전 참가자 공통이며, focal 편향은 `focal_included`·`focal_side` sensitivity로 확인한다 | `screen_copy.ALT_EXPOSURE_INTRO`·`PAIRWISE_INTRO` — `<TODO>` 제거 | 선례 없음 | PI | ✅ |
| PH-11 | 결정 | ~~개방 비교 1문항(F4-ⓔ)의 시스템 입력 여부~~ → **구술로만 받는다. 시스템 필드 없음** | 코드 변경 0건 — `tables.OpenComparison`·P9 추가 화면을 **만들지 않는다** | 선례 없음 | PI | ✅ |
| PH-12 | 승인 | AI2·checker 프롬프트 v2(부록 A.1·A.2 — `[AI의 직전 답변]` 블록 신설) PI 승인·lock | `prompts/prompt_config_v2.json` · `backend/app/llm/context.py` | **개조** (원칙 5항 승계, 입력 블록 추가) | PI | ◐ |
| PH-13 | 승인 | ~~checkpoint 직접 수정 UI 문안 + trouble_cue 대응 규칙~~ → **현행 UI·문안 확정**(segment 단위 수정 유지 — 범위 축소안 미채택) | `screen_copy.CHECKPOINT_EDIT_*` — `<TODO>` 제거 | **사용 금지** (v1 D-08 표시 전용 폐기) | PI | ✅ |
| PH-14 | 결정 | ~~sidecar 1단 「건너뛰기」 유지 여부~~ → **두지 않는다.** 「있어요」/「없어요」 2종 | `screen_copy.SIDECAR_HAS_MORE_CHOICES` — `<TODO>` 제거. `tables.SidecarEntry.has_more`는 `nullable=False` 유지(무응답 상태 없음) | **개조** (v1은 없음/있음/건너뛰기) | PI | ✅ |
| PH-IRB-1 | 문안 | 동의서 정본 — **항목 ⑥ 대안 노출 신설**, 국외 이전 전송 항목을 "재구성 대화(수정 반영)·첫 AI 응답·답장"으로 갱신 (§4.1·§9.3) | **초안 착지**: `screen_copy.CONSENT_NOTICE`·`CONSENT_ITEMS`(6키)·`CONSENT_PII_NOTICE`·`CONSENT_VERSION` / 게이트 표식 `CONSENT_TODO` 존치 · `core/freeze.py` | 승계(국외 이전 6항목·30일 상한) + 개조 | IRB | ◐ |
| PH-IRB-2 | 문안 | 디브리핑 정본 — 공개 7항목(§4.12: 대안 응답·"정답 없음"·checkpoint 수정 이용 범위 추가) | **초안 착지**: `screen_copy.DEBRIEF_BODY` / 게이트 표식 `DEBRIEF_TODO` 존치 | 승계(구조) + 개조(내용) | IRB | ◐ |
| PH-IRB-3 | 문안 | 연구자 안전 대응 프로토콜 (§9.2) | (코드 없음) | 승계 | IRB | ◐ |
| PH-IRB-4 | 문안 | 녹화물 보관·파기 | (코드 없음) | 승계 | IRB | ◐ |
| PH-IRB-5 | 문안 | Study 1 자료 이용·dossier 보관 | (코드 없음) | 승계 | IRB | ◐ |
| PH-IRB-6 | 문안 | 철회 절차 | (코드 없음) | 승계 | IRB | ◐ |
| PH-IRB-7 | 문안 | 보상 문안(수동 지급) | (코드 없음) | 승계 | IRB | ◐ |
| ~~PH-01~~ | ✂ | 사전 설문 — **삭제**(D-31, Q&A #1). 표본 기술은 Study 1 자료 재사용 | 파일 삭제(부록 H.1) | 사용 금지 | — | ✂ |
| ~~PH-02~~ | ✂ | P10 cross-branch review sidecar 비표시 — 화면 자체 소멸. v2.0은 sidecar를 참가자에게 재표시하는 화면이 없다(P11 인터뷰 대기는 pair만) | — | — | — | ✂ |
| ~~PH-05~~ | ✂ | normalization 패턴 — **삭제**(D-34) | 파일 삭제 | 사용 금지 | — | ✂ |
| ~~PH-P-1~5 (v1)~~ | ✂ | v1 논문 역반영 5건은 구 §6–7 기준 — 신 §6–7로 대체됨. 아래 §9에 v2 목록 | — | — | — | ✂ |

`tests/unit/test_placeholder_registry.py`가 코드·자산의 모든 `PH-nn` 참조를 이 표와 대조한다 — 표에 없는 placeholder가 코드에 남아 있으면 CI가 깨진다. **V2-0 전환 시 `PH-01`·`PH-02`·`PH-05` 참조는 코드에서 전부 제거해야 한다**(남으면 ✂ 항목이라 CI가 깨진다).

---

## 2. 자산 — 연구팀 작성

### PH-03 — dossier P01–P24 실값 ⬜ **본 모집 전 필수**

**현재 상태.** V2-1에서 스키마 v2(§5.3) 로더·계약 테스트·`schema_dummy/P01–P24`가 착지한다. P00만 실값(초안 신 §7.6 worked example — 3-year career plan). 로더는 실값 우선(`dossiers/Pnn.json` → `schema_dummy/`)이고 `is_dummy`가 기동 로그·R1·R4·모집 게이트에 노출된다.

**v1.0.1 대조 — 개조.** 3층 분리·정적 import 검사(NT-04)·기동 게이트·hash 계산(`hash` 필드 제외 canonical JSON)·lock 절차는 그대로 쓴다. 바뀌는 것:
- `sampling` → `evidence_code`(a_level `A0|A1|A2` 문자열, locus, locus_text, directional_constraint, permitted_operation, residual_uncertainty, consequential_justification, prohibited_inference, coders, adjudicated_at)
- `trouble_cue.{text, form}` → 문자열 하나(cue form 분류 폐기)
- `derivation.stimuli.C1–C4` + `referent_map` + `focal_repair_relevant_content` + `warranted_uptake` → **`stimulus.{r, u, q, stimuli_meta, neutral_fallback, qc}`**. 네 자극은 시스템이 조립한다(`r` / `r␣q` / `r␣u` / `r␣u␣q`).
- `ai_visible.provenance`(필드별 `verbatim_log | participant_quote | researcher_paraphrase`) + `excerpt_note` 신설
- `researcher_only.verification_notes` 신설(P2·인터뷰에서 나온 private preference — stimulus 미반영 기록)

**해소 경로**
1. 프로젝트 문서 『연구7_study2_selection_audit_trail_v1』·『연구7_study2_actionability_coding_v1』의 참가자별 판정을 **두 번째 코더 독립 판정 + adjudication**으로 확정(시스템 밖). 결과가 `evidence_code`로 들어간다.
2. 재구성: 원 로그 확보 여부에 따라 provenance 태깅. 발췌 규칙(problematized component 포함 최소 완결 단위 + 직전 사용자 turn, trouble turn이 참조하는 대상 절단 금지)을 `excerpt_note`에 기록. 재구성 비참여 연구자 1인이 "발췌가 trouble의 의미·locus를 바꾸지 않는가" 확인.
3. R/U/Q 작성(초안 §7.5): R = 최소 recognition(4조건 동일), U = permitted_operation 상한 내 least-assumptive adjustment(질문 0), Q = minimum U 적용 후 남는 consequential uncertainty의 minimum branching question(정확히 1개). LLM은 wording assistant로만(D-36).
4. 독립 QC(`stimulus.qc` 6항목: r/u/q identity·permitted boundary·leakage·minimum-Q) → 불합격은 반려.
5. `scripts/lock_dossier.py Pnn` → 계약 검증 → `locked_at`·`hash` 기입. **손으로 hash를 계산하지 말 것.**
6. `dossiers/Pnn.json`에 배치, 커밋 금지(`.gitignore`). 배포 반입은 PH-04.
7. 확인: `pytest tests/assets -q`(NT-20~23) → 기동 경고 소멸 → R4 lock 표시 → `freeze_study_version.py --check`에서 PH-03 소멸.

**주의.** 배정표(PH-08)는 lock된 dossier의 `a_level`을 입력으로 받으므로 **PH-03이 PH-08보다 먼저**다. lock 후 evidence_code를 고치면 배정표를 재생성해야 한다(§1.4 — 모집 전에만 가능).

### PH-03b — mismatch_locus 목록 ◐

v1.0.1의 5종을 초판으로 유지한다. 초안 신 §7.2는 "broad mismatch locus의 편중 최소화"만 말하고 목록을 주지 않는다. actionability coding 문서의 실제 사건들을 5종에 매핑해 보고 부족하면 추가한다(예: `support_type`, `premature_closure`). 변경 시 `dossier_loader.MISMATCH_LOCI`·schema_dummy·P00·`make_assignment.py` self-test를 함께 갱신.

### PH-08 — 배정표 실값 ⬜ **본 모집 전 필수**

**현재 상태.** V2-1에서 `make_assignment.py`(restricted randomization + 제약 검증 + 로그)와 `assignment_dummy.json`(P01–P24, 결정론 seed)이 착지한다. 로더는 `ASSIGNMENT_PATH` → dummy 순으로 찾고 `is_dummy`를 R1에 표시한다.

**v1.0.1 대조 — 선례 없음.** `core/williams.py`의 결정론 매핑은 **사용 금지**(삭제). 승계할 것은 "배정 로직은 한 파일에만 둔다"는 규율뿐이다.

**해소 경로**
1. PH-03 lock 완료 → `scripts/make_assignment.py --from-dossiers --seed <사전 기록 seed> --out assignments/assignment_v1.json`. seed는 실행 전 연구 노트에 기록한다(초안 §7.2 "pre-recorded random seed").
2. 산출 로그(`assignment_v1.log`)에서 제약 통과·strata 분포표·재시도 횟수 확인. A0가 1–2건이면 "네 조건 분산 불가" 경고가 남는다 — 오류가 아니며 논문 limitations에 옮긴다.
3. 파일 배치(커밋 금지), R1에서 24행·`is_dummy=false` 확인, `freeze_study_version.py --check`에서 PH-08 소멸.
4. **생성 후 변경 금지**(§1.4). 참가자 거절·일정 불가로 교체가 필요하면 교체 참가자의 dossier를 lock한 뒤 **같은 seed로 전체 재생성**하고 버전을 `assignment_v2`로 올린다 — 이미 세션을 마친 참가자가 있으면 재생성 불가(그 경우 연구팀 결정 사항이며 시스템이 부분 재배정을 지원하지 않는다).

---

## 3. 자산 — 문항 문면 ✅ **2026-08-24 `_v1` 착지**

두 자산 모두 실값 `_v1`이 fixtures에 착지했고 로더가 이를 우선 선택한다(`ASSET_CANDIDATES` — `_v0`은 기록용 보존, 무해). `freeze.blockers()`에서 PH-06·PH-07 소멸, 모집 게이트는 PH-03·PH-08·PH-IRB-1·2만 남는다. 문면의 문헌 근거·후보 대안은 프로젝트 문서 『연구7_PH06_focal문항_후보_v1』·『연구7_PH07_pairwise문항_후보_v1』에 기록.

### PH-06 — focal 5 construct + MC 2 ✅

**착지 내용** (`fixtures/focal_items_v1.json`, 9문항):
- 문항 수 확정: GS 2 · CE 2 · RI 1 · CN 1 · RCI 1 (+MC 2). 블록 1(대화 전체, 카드 없음) → 블록 2(MC, AI1 카드) 순서는 계약 그대로.
- **gs_1 교체**: 구 문면("…충분히 이해했다") → record 언어 재작성본("…판단할 근거가 충분히 마련되었다") — 구 문면은 mind-perception 언어라 mc_uptake와 변별 실패(수정사항 (b)).
- gs_2·cn_1: 연구 용어 "지원" → 참가자 언어 "도움". ce_1·ce_2·ri_1·mc_recognition: 구 정본 계승.
- **rci_1 신규**: "실제 상황이었다면, 나는 이 대화를 여기서 더 이어갔을 것 같다." — continuance intention(Bhattacherjee 2001; Ashfaq et al. 2020)의 대화 수준 번안, P7 이탈 유형의 연속형 삼각측정.
- **mc_uptake referent 고정**: "…위 답변에 실제로 반영했다" — 구 문면의 "다음 반응"은 P8 시점에 AI2로 오독 가능.
- MC referent 처리: 명세 기본값(블록 지시문 + AI1 카드, 문면 괄호 없음) 채택.

**계약**: `tests/assets/test_item_assets.py`에 착지 계약 추가 — `is_placeholder=False`·version 확인, 금지 표현(조건명·규범 어휘·`<TODO`) 0건 검사. (계획서의 `test_focal_items_contract.py`는 별도 파일 대신 기존 계약 파일에 통합.)

**잔여**: PI가 최종 문면을 다르게 고르면 `_v1` 파일의 text만 교체(모집 전 가능 — §1.4, hash는 §10.5 freeze 시 동결).

### PH-07 — pairwise 3 contrast ✅

**착지 내용** (`fixtures/pairwise_items_v1.json`, contrast당 3문항):
- **Sequence**(C2–C4): paired-stem 정당성 2문항(동일 문면 "그 시점에 물어볼 만한 질문"을 양측에 각각 평정 — 동일 질문의 지각이 선행 조정 유무로 달라지는지를 쌍 차이로 직접 측정) + 떠넘김 1문항(without_u). 구 seq_2는 질문 문면이 두 조건에서 동일해 좌우 구분 불가 — 폐기.
- **Scope**(C1–C3): warrant(with_u, record 언어) · overreach(with_u — 구 초안 §7.10 overreach 이식) · omission(without_u — "문제를 알아차리고도 조정 미수행").
- **Stopping**(C3–C4): 필요성(with_q) · 조기 철회(without_q — 구 premature withdrawal 이식) · 재설명 부담(with_q).
- **응답 형식 확정**: 7점 동의 척도(focal과 동일) + 이유 구술만(F4-ⓒ — PH-11 확정 정합). 한쪽 지칭은 전부 `target`/{side} 치환 — 서술형 지칭 폐기(PROGRESS 확인 ⑦ 해소).

**계약**: contrast당 2–3문항·target 유효·A/B 치환 정합·금지 표현 0건 — `test_item_assets.py`.

**잔여**: PH-06과 동일 — 최종 문면 변경은 `_v1` 파일 수정으로(모집 전).

---

## 4. 설계 잔여 결정 — PI ✅ **2026-08-24 전건 승인**

다섯 건 모두 **명세 기본값 그대로** 확정됐다. 반려·변경 0건이므로 동작 변경도 0건이고,
코드에서 한 일은 `<TODO: PH-nn>` 표식을 걷어내고 `[PI 승인 2026-08-24]`로 바꾼 것뿐이다.

| ID | 확정된 내용 | 코드에 남긴 것 |
|---|---|---|
| **PH-09** | 이탈 유형 6코드(`stop_here`·`new_chat`·`switch_ai`·`seek_human`·`no_further_need`·`other`)·국문 라벨·**표 순서 고정**(무작위 아님, `display_order`에 기록) | `screen_copy.END_TYPE_OPTIONS` · `state_machine.EndType` |
| **PH-10** | §4.9 대안 노출 안내 · §4.10 pairwise 안내 — 명세 [제안] 문안 그대로 | `ALT_EXPOSURE_INTRO` · `PAIRWISE_INTRO` |
| **PH-11** | 개방 비교 1문항(F4-ⓔ)은 **구술로만**. 시스템 입력 필드·테이블·export 열을 만들지 않는다 | (없음 — 만들지 않는 결정) |
| **PH-13** | checkpoint 수정 UI 현행 확정 — segment별 "수정" → 편집창(원문 채워진 채로) → 저장/취소, 보조문 "기억하시는 사실과 다른 부분만 고쳐주세요.", 확인 "확인했습니다 — 다음으로". trouble_cue·problematic_ai_response 수정 시 R2 붉은 경보 + Discord notify + 연구자 구두 확인 | `CHECKPOINT_EDIT_*` · `dossier_loader.ALERT_SEGMENTS` |
| **PH-14** | sidecar 1단은 **「있어요」/「없어요」 2종**. 「건너뛰기」를 두지 않는다 | `SIDECAR_HAS_MORE_CHOICES` · `tables.SidecarEntry.has_more` (`nullable=False`) |

**남는 것 하나** — PH-09의 *이유 필수 여부*(`END_REASON_REQUIRED = True`)는 승인 항목이 아니라
`[파일럿 확정]` 파라미터다(§8 표 "종료 이유 필수 여부"). soft launch 1회 조정 창에서만 바꾼다.

### PH-10 판단 근거 (기록)

문안이 없던 것이 아니라 **demand characteristics 우려 때문에 승인 보류돼 있던** 항목이다.
확인된 우려 3건과 현행 유지 판단:

1. "AI가 **다르게** 응답했다면" — 비교 프레임을 미리 깐다. 그러나 이 문장을 빼면 참가자가 같은
   상황을 왜 세 번 더 보는지 이해하지 못한다. 혼란이 만드는 노이즈가 더 크다.
2. "이번에는 답장을 작성하지 않으셔도 됩니다" — focal(User1 강제)과의 대비가 "focal만 진짜"라는
   신호가 될 수 있다. 그러나 실제로 입력창이 없으므로 고지하지 않을 수 없다.
3. "이어서 연구자가 몇 가지 질문을 드립니다" — accountability 효과로 정당화 가능한 답 쪽으로
   움직일 수 있다. 그러나 P11이 인터뷰 대기 화면이라 어차피 알게 되고, 예고가 놀람을 줄인다.

셋 다 **전 참가자에게 동일하게** 적용되므로 focal 조건과 교락되지 않는다(between 비교 안전).
위협받는 것은 pairwise의 focal 대 대안 within 비교뿐이고, 그 검정을 위해 서버가
`pairwise_views.focal_included`·`focal_side`를 기록한다(초안 §7.12 sensitivity).

## 5. 프롬프트 lock (PH-12) ◐

`prompts/prompt_config_v2.json`의 A.1·A.2 v2가 `[제안 — PI 승인 후 lock]`이다. v1 대비 변경은 **`[AI의 직전 답변]` 블록 추가**(focal AI1 원문)와 checker의 허용 정보 서술뿐이며 원칙 5항은 동일하다. `normalization_patterns_version` 키는 삭제된다.

**해소 경로**: PI 승인 → (수정 시) 문안 교체 + `prompt_hash` 재계산(`prompts.verify()`가 기동 시 검사) → 실모델 fixture 1회([확인 4]) → soft launch 종료 시 `study_version` 동결.

⛔ `prompt_config_v1.json`은 V2-0에서 삭제된다. 구 `study2_pipeline`의 `prompt_config_v4.0.json`은 계속 참조 금지.

---

## 6. IRB·문안

> **2026-08-24 문안 초안 착지 + 코드 반영**: PH-IRB-1~7의 문안 정본 초안이 `docs/IRB_문안_정본_초안_v1.md`에 있다(출처: 프로젝트 문서 『연구7_IRB_2-1_심의용연구계획서_초안_v0.9』 + 『연구7_IRB_첨부물_작성계획_v1』, 명세 §4.1·§4.12·§9.2·§9.3 구조 준수). 전 항목 ⬜→◐.
>
> PH-IRB-1·2는 **초안 문안이 코드에도 착지**했다(P1·P12 화면이 실제 문안을 띄운다 — 리허설 가능). **모집 게이트는 그대로 ⛔다**: `CONSENT_TODO`·`DEBRIEF_TODO` 상수가 화면에서 내려오되 `freeze.blockers()`가 읽는 미착지 표식으로 남아 있고, `CONSENT_VERSION = "irb_draft_v1_2026-08-24"`가 저장 기록·`assets_hash`에 초안임을 남긴다. `tests/assets/test_irb_copy_contract.py`가 ① 코드 문안 ↔ IRB 문서 글자 대조 ② 표식·버전 정합(둘 중 하나만 바꾸면 실패) ③ 필수 항목 6종·7항목을 건다.

### 승인 후 교체 절차 (PH-IRB-1·2 ◐ → ✅)

1. `docs/IRB_문안_정본_초안_v1.md`를 승인본으로 갱신하고 슬롯 3종(`[IRB 승인번호]`·`[연구팀 연락처]`·`[IRB 사무국 연락처]`)을 치환한다.
2. [확인 3] 재실측 → 동의서 ④의 보유 기간(현행 "최대 30일") 확정. 상담 기관 3곳 확정(PH-IRB-3, 안전 자원 안내문).
3. `screen_copy.py`: 승인본 문안으로 상수 교체 → `CONSENT_TODO`·`DEBRIEF_TODO` **삭제** → `CONSENT_VERSION = "irb_v1_<승인일>"`. `freeze.IRB_TAGS` 루프가 참조하는 상수를 지우므로 `core/freeze.py`의 해당 블록도 함께 제거한다.
4. `pytest` 전체 green — 계약 테스트가 슬롯 잔존·표식/버전 불일치를 잡는다.
5. `freeze_study_version.py --check`에서 PH-IRB-1·2 소멸 확인 → 이 표를 ✅ + 커밋 해시로 갱신.

### PH-IRB-1 동의서 ◐ **모집 게이트**

v1 대비 변경: ① 항목 6종(`alternative_exposure` 신설 — "같은 상황에 대해 서로 다른 AI 응답 여러 개를 보게 됩니다") ② 국외 이전 전송 항목 = **재구성된 대화(참가자 수정 반영본)·첫 AI 응답·참가자 답장**(비식별). sidecar·평정·pairwise·User2·연락처는 전송되지 않는다(§1.2가 방어 논리, NT-01이 증거) ③ 30일 보수 상한은 [확인 3] 재실측 후 갱신.

착지 형태: **실제 동의 취득은 자필 서명 서면**(초안 §1-A, 시스템 밖)이고 **P1은 재확인 화면**(§1-B 축약 라벨 6종 + §1-C 상단 안내 + PII 안내)이다. 화면 payload는 `notice`·`items`·`footnote` 3종.

### PH-IRB-2 디브리핑 ◐ **모집 게이트**

공개 7항목(§4.12). v1의 "네 branch 비교" 문장을 옮기면 안 된다 — v2는 "처음 경험한 응답 1개 + 나중에 본 응답 3개"이고 "어느 것도 정답이 아니다"가 추가된다. 착지본은 초안 §2-A 본문 전체(단락 7 + 연락처 4행)이며 SS90 중단 세션용 축약판(§2-B)은 **구두 + 이메일**이라 코드에 두지 않는다.

### PH-IRB-3~7 ◐

v1.0.1 내용 승계(안전 프로토콜·녹화·Study 1 연계·철회·보상). PH-IRB-5에 "checkpoint 수정본도 연구 데이터로 보관"을 추가. 다섯 항목 모두 **코드에 닿지 않는다** — 초안 문서가 IRB 첨부물의 원고다. PH-IRB-3만 상담 기관 3곳 목록이 미확정으로 남아 있다.

## 7. 운영·배포

### PH-04 — 실값 반입 ◐ **절차 확정 (2026-08-25)**

정본은 **`docs/배포_자산_반입_v1.md`**다. v1 권고 A(볼륨) 유지 — JSON 24건을 환경변수로 주입하면 크기 제한·이스케이프·회전 절차가 전부 문제가 되므로 볼륨을 택했다.

**절차 요약**: 볼륨 `/data` 마운트 → `DOSSIER_DIR=/data/dossiers` · `ASSIGNMENT_PATH=/data/assignments/assignment_v1.json` → lock된 파일을 호스트 CLI로 전송(중간 저장소 경유 금지) → `freeze_study_version.py --check`의 「자산 출처」 블록으로 확인.

**닫으면서 드러난 코드 구멍 2건을 같이 고쳤다.** 둘 다 "틀렸는데 떠 있는" 모양이었다.

| # | 구멍 | 고친 것 |
|---|---|---|
| 1 | `DOSSIER_DIR`를 볼륨으로 돌리면 **이미지의 P00과 스키마 더미가 탐색 범위 밖으로 나갔다** — 부분 착지(24명이 한 명씩 lock, §5.3) 상태에서 기동 게이트가 죽고, 배포 환경에서 QA 워크스루(§10.2)가 돌지 않았다 | `dossier_search_paths()` 신설 — **볼륨 오버레이** 3단(볼륨 실값 → 이미지 실값 → 더미). 볼륨에는 실값만 올린다 |
| 2 | 경로 오타가 **조용히** 수렴했다: `DOSSIER_DIR` 오타 → 참가자 루프가 `DossierNotFound`를 삼켜 **dossier 0건으로 기동 성공** / `ASSIGNMENT_PATH` 오타 → **더미 배정표를 실은 채 기동 성공** | `AssetLocationError` 신설(삼켜지는 계보 밖) · `assignment_path()`가 오버라이드 미존재 시 끊는다 |

**남은 것 2건**(§7절 「이 문서가 확정하지 않은 것」): 호스트 CLI 명령 문법 실측, 볼륨 백업 정책(PH-IRB-4 오프라인 백업으로 갈음할지). 둘 다 실제 반입 시점에 닫힌다 — **PH-03·PH-08이 먼저다**(올릴 파일이 아직 없다).

검증: `tests/assets/test_asset_import.py` 9건 — 부분 착지 폴백 · P00 생존 · 볼륨 자체 더미 우선 · 오설정 2종이 조용히 넘어가지 않음 · `asset_sources()` 보고.

### [확인 1~5]

| # | 확인 | v1 실측(2026-07~08) | v2 변경점 |
|---|---|---|---|
| 1 | 모델 슬러그·단가 | `anthropic/claude-opus-4.8`·`openai/gpt-5.4` 확인 | 재실측만 |
| 2 | provider 고정 문법 | 현행 확인, 이식 완료 | 없음 |
| 3 | OpenRouter 보존 | Anthropic 30일 → 보수 상한 | **전송 항목 변경**(AI1 원문 포함) — 동의서 문안 갱신 |
| 4 | checker 실모델 비용·RPM | 신규 계정 10 RPM 제한 주의 | fixture v2로 재실행 |
| 5 | Zoom | 선례 없음 | 없음 |

---

## 8. `[파일럿 확정]` 파라미터 — 조정 창은 soft launch 1회

| 파라미터 | 값 | 코드 위치 | 비고 |
|---|---|---|---|
| AI2 / checker 타임아웃 | 90,000 / 45,000ms | `core/config.py` | 승계 |
| AI2 temperature / max_tokens · checker temperature | 0.4 / 800 · 0.0 | `prompts/prompt_config_v2.json` | 승계 |
| R-4 길이 상한 · R-3 질문 휴리스틱 · 누출 대조 최소 길이 | 1,200자 · 의문부호+종결어미 · 8자 | `llm/integrity_rules.py`·`core/text_metrics.py` | 승계 |
| 재진입 타이머 | 최소 30초 / 60초 안내 | `screen_copy.py`·`Focal.tsx` | **신설** |
| 타이핑 인디케이터 | 1.5초(focal·대안 동일) | `components/Chat.tsx` | 승계(값 고정) |
| 종료 이유 필수 여부 | 필수 | `api/focal.py` | **신설**(PH-09와 연동) |
| 접속 코드 TTL / 실패 지연 | 24h / 5회·30초 | `core/access_code.py` | 승계 |
| R2 폴링 / 이벤트 창 / 5xx 임계 | 3s / 60건 / 3회 | 콘솔·`admin_views.py`·`notify/watch.py` | 승계 |

---

## 9. 논문 역반영 (PH-P-1~6, v2) — 시스템 밖

| ID | 내용 |
|---|---|
| PH-P-1 | 설계 명칭: "focal between-participants enactment + within-participant contrastive evaluation" 표기 통일 (§1.5-9) |
| PH-P-2 | §7.3: checkpoint 사실 오류를 **참가자가 직접 수정**하며 수정본이 AI2 입력에 쓰임을 서술(D-25) — 현행 "수정할 수 있다"와 정합, 방법 명시 |
| PH-P-3 | §7.7: AI2 이후 선택지 목록(User2 / 종료 + 이탈 유형 6종) 복원(결정로그 #2·#6) |
| PH-P-4 | limitations: User1 강제 작성으로 AI1 직후 즉시 이탈은 관찰 불가(D-27·D-32) |
| PH-P-5 | §7.8: sidecar 선택지 = **있음/없음 2종, 건너뛰기 없음**(PH-14 확정 2026-08-24) |
| PH-P-6 | §7.5: LLM 역할 문장을 "인간 코딩 후 sensitivity/audit용 third reading" 허용으로 개정(결정로그 #4 확정 시). 파이프라인 flowchart A3 박스도 동일 |

---

## 10. v1.0.1 대조 총괄

**가져오는 것(승계·개조)** — evidence firewall·NT-04 정적 검사 / dossier 3층 로더·기동 게이트·hash·lock 절차 / AI2 사다리(규칙+checker+재생성+fallback)·generations 기록 규약(fallback 별도 행·규칙 위반 시 checker 생략) / 게이트웨이·provider 고정·usage / Fernet·audit·복호화 지점 열거 테스트 / 접속 코드·idempotency·복구 / 콘솔 정적 HTML 1장·요청 단위 복호화 audit / fixture 러너·fake LLM 트리거 / 자산 착지 규율(문서 → 계약 테스트 → 착지 커밋 → hash 동결) / placeholder 레지스트리 테스트 / 화면 문안 서버 보관·[정본] 대조 테스트 / 국외 이전 문안·디브리핑 구조·핫라인 참고 자료.

**가져오면 안 되는 것(사용 금지)** — `core/williams.py`·번호 순환 매핑 / `llm/normalization.py`·패턴·referent_map / `assets/presurvey.py`·사전설문 자산 / `Disposition(reply·no_reply·end)`·`has_ai2`·no_reply 분기 / 12문항 2블록·overreach·premature_withdrawal·autonomy·clarity 단독 문항 / downstream 7메뉴 / `analysis/tagging_flags.py`·first_opportunity·carryover / cue form 분류 / D-08 표시 전용 checkpoint / P10 cross-branch review 4열 / `branch_index`·`Branch` 테이블 / CLAUDE.md v1의 "AI1 원문 금지" 규칙(v2는 **포함**이 정책이다).

---

## 11. 이 문서의 유지 규칙

- 명세서의 `<TODO>`에 대응하는 코드상 빈 자리는 전부 §1 표에 등록한다. 표에 없는 `PH-nn`이 코드에 남아 있으면 CI가 깨진다(`tests/unit/test_placeholder_registry.py`). ✂ 항목의 참조가 코드에 남아 있어도 깨진다.
- 해소되면 ✅로 바꾸고 교체 커밋 해시를 기록한다. 문안·자산이 존재하지만 코드 교체 전이면 ◐다.
- 새 미확정 항목은 **명세서 부록 E.4에 먼저** 등록하고 여기에 반영한다(반대 순서 금지).
- 전환 작업(Sprint V2-0~V2-4)은 완료됐고 기록은 `PROGRESS.md`에 있다 — 이 문서는 전환이 끝나고도 남은 것만 다룬다.
- 자산 파일은 `_v1`이 실값이고 `_v0`은 **지우지 않고 남긴다**. `_v1`이 사라지면 로더가 `_v0`으로 내려가면서 모집 게이트가 다시 울리는 것이 회귀 감지 장치다(`rating_items.ASSET_CANDIDATES` 주석).
