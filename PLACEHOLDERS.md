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

**코드로 닫을 수 있는 항목이 다시 생겼다.** v1.0.1은 구현이 끝난 상태였지만, v2.0 전환(Sprint V2-0~V2-4, 명세 §11.1)이 시작 전이다. 전환 자체는 `PROGRESS.md`가 추적하고, 이 문서는 **전환이 끝나도 남는 자산·승인·외부 확인**만 등록한다.

```bash
DEV_MODE=true ./backend/.venv/bin/python scripts/freeze_study_version.py --check
#   (V2-4 이후) 모집 게이트: PH-03 · PH-08 · PH-06 · PH-07 · PH-IRB-1 · PH-IRB-2
```

| 분류 | 건수 | 성격 | 본 모집 게이트(§11.2) |
|---|---|---|---|
| 자산 — 연구팀 작성 (PH-03·03b·08) | 3 | dossier 24건(R/U/Q·evidence code)·locus 목록·배정표 | PH-03·PH-08 ⛔ |
| 자산 — 문항 문면 (PH-06·07) | 2 | focal 5 construct + MC 2 / pairwise 3 contrast | PH-06·PH-07 ⛔ |
| 설계 잔여 결정 — PI (PH-09·10·11·13·14) | 5 | 이탈 유형 라벨·안내 문안·개방 비교·수정 UI·sidecar 선택지 | — (placeholder로 개발 가능) |
| 프롬프트 lock (PH-12) | 1 | A.1·A.2 v2 PI 승인 | — (실모델 실행 선행 조건) |
| IRB·문안 (PH-IRB-1~7) | 7 | IRB 승인 | PH-IRB-1~7 ⛔ |
| 운영·배포 (PH-04, 확인 1–5) | 6 | 개발자·계정 실측 | — |
| `[파일럿 확정]` 파라미터 | 12 | soft launch 1회 조정 창 | — |
| `[제안]` 화면 문안 | 약 25 | PI 승인 (코드 변경 0 예상) | — |
| 논문 역반영 (PH-P-1~6) | 6 | 시스템 밖 | — |
| v1.0.1 소멸 항목 (✂) | 4 | 기록 | — |

착지 순서 권고: **V2-0~V2-4 전환 완료 → PH-IRB(제출) → PH-06·07(문항) → PH-03(dossier 실값·lock) → PH-08(배정표 생성·동결) → PH-04(반입) → PH-12(프롬프트 lock) → 실모델 fixture([확인 4]) → soft launch → 설계 동결(§10.5)**.

---

## 1. 요약 표

| ID | 유형 | 무엇이 비어 있나 | 코드 위치 (V2 전환 후 기준) | v1.0.1 대조 | 해소 주체 | 상태 |
|---|---|---|---|---|---|---|
| PH-03 | 자산 | dossier P01–P24(배정 참가자) 실값 — ai_visible(provenance 태그 포함)·researcher_only·evidence_code·**R/U/Q segment**·neutral_fallback·QC 기록·lock (§5.3) | `dossiers/schema_dummy/*` · `backend/app/assets/dossier_loader.py` · `scripts/lock_dossier.py` · `backend/app/core/freeze.py` | **개조** (3층 로더·계약 테스트 패턴 승계, 스키마 v2) | 연구팀 | ⬜ |
| PH-03b | 자산 | `evidence_code.mismatch_locus` 허용값 목록(broad locus) 확정 — 초판: content_depth · affective_tone_intensity · context_memory_use · interpretation · trajectory_timing | `dossier_loader.MISMATCH_LOCI` · `scripts/make_assignment.py`(편중 최소화 입력) | 승계(v1 5종) | 연구팀 | ◐ |
| PH-04 | 운영 | dossier·배정표 실값의 배포 반입 절차 (§2.9) — `DOSSIER_DIR`·`ASSIGNMENT_PATH` 볼륨 마운트 | `backend/app/assets/files.py` · `backend/app/core/config.py` | 승계(권고 A: Railway 볼륨) | 개발자 | ⬜ |
| PH-06 | 자산 | focal 5 construct + MC 2 **문항 문면** (§4.8·§7.1–7.2) — 초판은 v1.0.1 12문항 중 7개 차용 + RCI 1 신규 + MC referent 문구 | `fixtures/focal_items_v0.json` · `backend/app/assets/rating_items.py` | **개조** (문면 7개 재사용 가능, 2블록 구성은 변경) | 연구팀·PI | ◐ |
| PH-07 | 자산 | pairwise 3 contrast **문항 문면·응답 형식** (§4.10·§7.5) — 초판 8문항(부록 A.5), 7점 + 이유 구술(F4-ⓒ) | `fixtures/pairwise_items_v0.json` · `backend/app/assets/pairwise_items.py` | 선례 없음 | 연구팀·PI | ◐ |
| PH-08 | 자산 | **배정표 실값** `assignments/assignment_v1.json` — strata CSV(24명 a_level·locus) + seed → 생성·제약 검증·로그 (§5.2) | `scripts/make_assignment.py` · `backend/app/core/assignment.py` · `assignments/assignment_dummy.json` | 선례 없음 (Williams는 **사용 금지**) | 연구팀(seed 기록)·개발자 | ⬜ |
| PH-09 | 승인 | User2/종료 화면의 **이탈 유형 6코드 라벨** + 이유 필수 여부 (§4.7) | `backend/app/assets/screen_copy.py`(`END_TYPE_OPTIONS`) · `backend/app/api/focal.py` | **사용 금지** (구 7메뉴 복원 아님 — 3개 코드명만 우연히 겹침: new_chat·switch_ai·seek_human) | PI | ⬜ |
| PH-10 | 승인 | 대안 노출 첫 화면 안내 + pairwise 안내 문안 (§4.9·§4.10) — demand 직결 | `screen_copy.py`(`ALT_EXPOSURE_INTRO`·`PAIRWISE_INTRO`) | 선례 없음 | PI | ⬜ |
| PH-11 | 결정 | 대안 3종 노출 직후 **개방 비교 1문항**(F4-ⓔ)을 시스템 자유기술로 둘지 구술로만 받을지. 기본값: 구술(시스템 필드 없음) | (채택 시) `tables.OpenComparison` · P9 마지막 화면 | 선례 없음 | PI | ⬜ |
| PH-12 | 승인 | AI2·checker 프롬프트 v2(부록 A.1·A.2 — `[AI의 직전 답변]` 블록 신설) PI 승인·lock | `prompts/prompt_config_v2.json` · `backend/app/llm/context.py` | **개조** (원칙 5항 승계, 입력 블록 추가) | PI | ◐ |
| PH-13 | 승인 | checkpoint **참가자 직접 수정** UI 문안(수정 버튼·편집 보조문·확인 버튼) + trouble_cue 수정 시 연구자 대응 규칙(부록 D.3) | `screen_copy.py`(`CHECKPOINT_EDIT_*`) · `backend/app/api/participant.py` · `frontend/src/screens/Intro.tsx` | **사용 금지** (v1 D-08 표시 전용 폐기) | PI | ⬜ |
| PH-14 | 결정 | sidecar 1단 선택지에 「건너뛰기」를 둘지 (초안 신 §7.8에는 있음/없음만). 기본값: 두지 않는다 | `screen_copy.py`(`SIDECAR_Q1_CHOICES`) · `tables.SidecarEntry.has_more` | **개조** (v1은 없음/있음/건너뛰기) | PI | ⬜ |
| PH-IRB-1 | 문안 | 동의서 정본 — **항목 ⑥ 대안 노출 신설**, 국외 이전 전송 항목을 "재구성 대화(수정 반영)·첫 AI 응답·답장"으로 갱신 (§4.1·§9.3) | `screen_copy.CONSENT_TODO`·`CONSENT_ITEMS`(6키) · `core/freeze.py` | 승계(국외 이전 6항목·30일 상한) + 개조 | IRB | ⬜ |
| PH-IRB-2 | 문안 | 디브리핑 정본 — 공개 7항목(§4.12: 대안 응답·"정답 없음"·checkpoint 수정 이용 범위 추가) | `screen_copy.DEBRIEF_TODO` | 승계(구조) + 개조(내용) | IRB | ⬜ |
| PH-IRB-3 | 문안 | 연구자 안전 대응 프로토콜 (§9.2) | (코드 없음) | 승계 | IRB | ⬜ |
| PH-IRB-4 | 문안 | 녹화물 보관·파기 | (코드 없음) | 승계 | IRB | ⬜ |
| PH-IRB-5 | 문안 | Study 1 자료 이용·dossier 보관 | (코드 없음) | 승계 | IRB | ⬜ |
| PH-IRB-6 | 문안 | 철회 절차 | (코드 없음) | 승계 | IRB | ⬜ |
| PH-IRB-7 | 문안 | 보상 문안(수동 지급) | (코드 없음) | 승계 | IRB | ⬜ |
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

## 3. 자산 — 문항 문면

### PH-06 — focal 5 construct + MC 2 ◐

**현재 상태.** `fixtures/focal_items_v0.json`에 부록 A.4 초판(9문항)이 placeholder로 들어간다. 파일명 `_v0`인 동안 모집 게이트가 PH-06을 보고한다.

**v1.0.1 대조 — 개조.** 12문항 중 7개(gs_1·gs_2·ce_1·ce_2·ri_1·cn_1·mc 2종)는 구 초안 §7.10 [정본]이었고 문면 재사용 가능성이 높다. 다만 **신 초안은 문면을 싣지 않았으므로 더 이상 [정본]이 아니다** — 재승인 대상. 삭제된 것: overreach·premature_withdrawal(pairwise로 이동)·autonomy·support_purpose_clarity(소멸). 신규: Retrospective Continuation Intention 1문항.

**결정 필요**: construct당 문항 수(1 또는 2), RCI 문면, MC 2문항에 referent 문구("첫 번째 AI 응답")를 문면에 넣을지 블록 지시문으로만 둘지(명세 기본값: 지시문 + AI1 카드, 문면은 괄호 없이).

**해소 경로**: 문면 확정 → `focal_items_v1.json` 승격 + `rating_items.ASSET_PATH` 교체 → `tests/assets/test_focal_items_contract.py`(construct 5종 각 ≥1, mc 2, 규범 어휘 부재, `<TODO>` 0건) 통과 → 게이트 소멸.

### PH-07 — pairwise 3 contrast ◐

**현재 상태.** `fixtures/pairwise_items_v0.json`에 부록 A.5 초판(8문항) placeholder. 응답 형식은 7점 평정(시스템) + 이유 구술(연구자) — F4-ⓒ 디폴트.

**v1.0.1 대조 — 선례 없음.** 구 overreach·premature_withdrawal 문항의 **취지**가 Scope·Stopping 문항으로 이동했을 뿐, branch 평정 문항을 그대로 옮기면 안 된다(A/B 비교 문면이어야 한다).

**결정 필요**: contrast당 문항 수(2–3), 한쪽 응답을 지칭하는 문항의 처리(자산 `target` 필드로 서버가 "응답 A/B" 치환 — 명세 A.5), 이유를 시스템 자유기술로도 받을지(현재: 구술만).

**해소 경로**: PH-06과 동일 패턴. 계약 테스트: contrast 3종 각 ≥2, `target` 값 유효, 문면에 조건명·R/U/Q 어휘 0건.

---

## 4. 설계 잔여 결정 — PI (placeholder로 개발 진행 가능)

| ID | 기본값(명세) | 반려 시 비용 |
|---|---|---|
| PH-09 이탈 유형 라벨·이유 필수 | 6코드(stop_here·new_chat·switch_ai·seek_human·no_further_need·other) 표 순서 고정, 이유 필수 `[파일럿 확정]` | 낮음 — `screen_copy` 상수 + 검증 1줄. 코드 **추가·삭제**는 export 열과 codebook에 영향(중간) |
| PH-10 안내 문안 | §4.9·§4.10 [제안] 문안 | 낮음 |
| PH-11 개방 비교 문항 | 구술만(시스템 없음) | 시스템 입력 채택 시: 테이블 1·화면 1·export 열 1 (중간) |
| PH-13 checkpoint 수정 UI | segment별 "수정" → 편집창 → 저장/취소, 보조문 "기억하시는 사실과 다른 부분만 고쳐주세요.", trouble_cue 수정 시 경보 + 연구자 구두 확인 | 낮음 (문안) / 수정 범위를 segment 일부로 제한하려면 UI 재설계(높음) |
| PH-14 sidecar 건너뛰기 | 두지 않는다(있어요/없어요) | 낮음 — 선택지 1 + `has_more` nullable |

---

## 5. 프롬프트 lock (PH-12) ◐

`prompts/prompt_config_v2.json`의 A.1·A.2 v2가 `[제안 — PI 승인 후 lock]`이다. v1 대비 변경은 **`[AI의 직전 답변]` 블록 추가**(focal AI1 원문)와 checker의 허용 정보 서술뿐이며 원칙 5항은 동일하다. `normalization_patterns_version` 키는 삭제된다.

**해소 경로**: PI 승인 → (수정 시) 문안 교체 + `prompt_hash` 재계산(`prompts.verify()`가 기동 시 검사) → 실모델 fixture 1회([확인 4]) → soft launch 종료 시 `study_version` 동결.

⛔ `prompt_config_v1.json`은 V2-0에서 삭제된다. 구 `study2_pipeline`의 `prompt_config_v4.0.json`은 계속 참조 금지.

---

## 6. IRB·문안

### PH-IRB-1 동의서 ⬜ **모집 게이트**

v1 대비 변경: ① 항목 6종(`alternative_exposure` 신설 — "같은 상황에 대해 서로 다른 AI 응답 여러 개를 보게 됩니다") ② 국외 이전 전송 항목 = **재구성된 대화(참가자 수정 반영본)·첫 AI 응답·참가자 답장**(비식별). sidecar·평정·pairwise·User2·연락처는 전송되지 않는다(§1.2가 방어 논리, NT-01이 증거) ③ 30일 보수 상한은 [확인 3] 재실측 후 갱신.

### PH-IRB-2 디브리핑 ⬜ **모집 게이트**

공개 7항목(§4.12). v1의 "네 branch 비교" 문장을 옮기면 안 된다 — v2는 "처음 경험한 응답 1개 + 나중에 본 응답 3개"이고 "어느 것도 정답이 아니다"가 추가된다.

### PH-IRB-3~7 ⬜

v1.0.1 내용 승계(안전 프로토콜·녹화·Study 1 연계·철회·보상). PH-IRB-5에 "checkpoint 수정본도 연구 데이터로 보관"을 추가.

---

## 7. 운영·배포

### PH-04 — 실값 반입 ⬜

v1 권고 A(Railway 볼륨) 유지. v2는 반입 대상이 **dossier 24 + 배정표 1**로 늘어 `DOSSIER_DIR`·`ASSIGNMENT_PATH` 환경변수가 §2.4에 정식 편입되었다(v1에서 "명세 개정 대상"이던 것이 해소됨).

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
| PH-P-5 | §7.8: sidecar 선택지(있음/없음, 건너뛰기 없음 — PH-14 결과에 따라) |
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
- 전환 작업(Sprint V2-0~V2-4)의 진행은 `PROGRESS.md`가 담당한다 — 이 문서는 전환이 끝나도 남는 것만 다룬다.
