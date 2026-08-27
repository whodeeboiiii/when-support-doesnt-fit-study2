# CLAUDE.md — study2-enactment (v2.0, focal-between)

NOT QUITE YES Study 2: **24명 focal between-participants enactment + within-participant contrastive evaluation** 실험 시스템 (참가자 화면 + 연구자 콘솔).
**유일한 정본은 `docs/구현명세서_v2.0.md`다.** 이 파일과 명세서가 충돌하면 명세서가 우선한다. `docs/구현명세서_v1.0.1.md`(within 설계)는 **읽기 전용 상속 원본**이다 — 설계 근거를 찾을 때만 열고, 거기 있는 규칙을 코드에 되살리지 마라.

## 절대 규칙

1. **명세서에 없는 설계 결정을 임의로 내리지 마라.** 결정이 필요하면 구현을 멈추고 질문하거나, `<TODO: PH-nn>` 태그를 남기고 `PLACEHOLDERS.md`에 등록하라. **[정본]** 문안 7건(§4.2 checkpoint 안내 · §4.4 User1 지시 · §4.5 sidecar 3단 · §5.5 P00 R/U/Q)은 **한 글자도 윤문 금지**.
2. **Evidence boundary(명세 §1.2)는 불변식이다.** AI2 payload = {effective checkpoint(참가자 수정 반영), **focal AI1 원문**, User1 원문} 3종뿐. 조건 라벨·R/U/Q 구분·**대안 AI1 3종**·sidecar·researcher_only·배정표·평정·pairwise·User2·수정 전 원문은 어떤 LLM 호출에도 넣지 않는다. `llm/`은 `dossier_private`·`assignment`·`pairwise_items`를 import할 수 없다(NT-04).
   - ⚠ v1.0.1은 "AI1 원문 금지"였다. **v2.0은 focal AI1을 포함하는 것이 정책**이다(D-34). normalization은 존재하지 않는다.
3. **순서 불변식**: 대안 AI1은 focal 측정(SS05) 완료 전에 어떤 참가자 payload에도 실리지 않는다(NT-31). AI2 호출은 sidecar 제출 후에만(NT-16).
4. **배정은 읽기만**: focal condition·대안 노출 순서·pair 순서·좌우는 `assignments/assignment_v1.json`(없으면 dummy)에서 읽어 최초 진입 시 저장 후 불변이다(NT-07·32·33). 코드에 배정 계산·Williams·순환 매핑을 만들지 마라.
5. **자극은 조립**: AI1 = `r` / `r␣q` / `r␣u` / `r␣u␣q` (단일 공백). 네 전문을 자산에 따로 두지 않는다(D-35). AI1은 checkpoint 수정과 무관하게 locked 그대로 표시된다.
6. **User1은 필수, AI3는 없다.** no_reply/end 분기·enacted-choice 문항·User2에 대한 AI 응답을 만들지 마라(D-27·D-32·D-33).
7. **dead-end 금지**: 모든 오류 경로는 §9.1의 유효한 다음 상태로 수렴한다. AI2 실패의 종착지는 참가자별 `neutral_fallback`이다.
8. **판정 코드 금지**: 비수용 판정·라우팅·eligible 분류·actionability 기반 분기·checkpoint 수정 내용의 "선호 유입" 판정은 존재하지 않는다. A-level은 descriptor다.
9. **ID 예약**: C1–C4 = 조건, D-nn = 결정(D-23부터 v2), NT-nn = 테스트(신규 NT-31~), SS##/F# = 상태, P0–P12/R1–R4 = 화면. 변수명에 `acceptance`·`branch` 계열 금지. **예외 1건**: 사전설문 복원(D-44)은 `SS01S`/`P1S`를 쓴다 — 화면 하나를 끼우자고 SS02–SS10·P2–P12를 재번호하면 명세서·콘솔·rewind 대상·문서가 전부 갈라진다.

## Legacy 참조 규칙

- **사전설문은 예외다(D-44, 2026-08-27)**: 연구자 지시로 v1.0.1 §4.2·§7.1의 사전 설문이 복원됐다 — 자산·로더·`presurvey_responses`·화면 **P1S**(동의 직후·checkpoint 직전). 되살린 범위는 `PLACEHOLDERS.md` §3b의 표가 정본이고, 그 밖의 v1.0.1 폐기 항목은 아래 금지 목록 그대로다. 명세서 v2.0은 아직 D-31(사전설문 삭제)로 되어 있다 — **개정 전까지 이 줄이 우선한다**.
- **v1.0.1 코드(태그 `v1.0.1-within`)에서 되살리면 안 되는 것**: `core/williams.py` · `llm/normalization.py` · `Disposition`/`has_ai2`/no_reply 분기 · `Branch` 테이블·`branch_index` 루프·reset 의미론 · 12문항 2블록·downstream 7메뉴 · `analysis/tagging_flags.py` · cue form · D-08 표시 전용 checkpoint · P10 cross-branch review. 처분 근거는 명세 부록 G, 파일 단위 지시는 **부록 H**.
- 구 `../study2_pipeline`(v5.0 계보)은 v1.0.1 CLAUDE.md의 참조 금지 목록이 그대로 유효하다 — 열지 마라.

## 자산 원칙

- dossier(P01–P24)·배정표·focal/pairwise 문항은 **스키마 준수 placeholder**(schema_dummy·assignment_dummy·`_v0.json`)로 개발한다. P00만 실값(초안 신 §7.6). 실값 착지를 기다리며 개발을 막지 마라.
- 자산 착지·변경 커밋은 자산 계약 테스트(NT-20~23·32)를 동반한다.
- `dossiers/P01–P30.json`·`assignments/assignment_v1.json`은 git에 커밋하지 않는다(§2.9).

## 스택·명령

- backend: FastAPI(Python 3.12+), SQLAlchemy, Supabase Postgres(배포)/SQLite(`DEV_MODE=true`). schema `proto_v2` → `main_v2`.
- frontend: React 18 + Vite + TS + Tailwind — **데스크톱 전용**.
- LLM: OpenRouter — MAIN(AI2)/VALIDATOR(checker) 이원화. `DEV_MODE=true`면 fake_llm.
- 테스트: `pytest`(부록 C). **커밋마다 전체 green, 기준선 불감소**(V2-0 삭제 직후의 green을 새 기준선으로 잡는다).
- 로컬: `uvicorn app.main:app` + `npm run build`. 배정표 생성: `python scripts/make_assignment.py`. dossier lock: `python scripts/lock_dossier.py Pnn`.

## 작업 규율

- 스프린트 순서는 명세 §11.1(V2-0 정리 → V2-1 자산·배정 → V2-2 상태머신·화면 → V2-3 AI2 → V2-4 콘솔·export). **V2-0은 부록 H의 목록만 적용한다** — 목록 밖 파일을 "김에" 고치지 마라.
- 스프린트 종료 시 `PROGRESS.md`에 완료 기준 대비 결과·"명세에 없어 내가 정한 것"·다음 단계를 기록하라. 명세에 없는 결정은 되돌리기 쉬운 형태로 두고 표로 남겨라.
- free session, 모바일, 보상 코드, 안전 자동 종료, LLM derivation/audit 도구, N 미달 fallback은 **범위 밖**이다.
