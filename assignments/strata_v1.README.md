# strata_v1.csv — 배정표 생성 입력 (PH-08, 2026-08-26)

`assignment_v1.json`을 만든 입력이다. `make_assignment.py`가 읽는 것은 이 세 열뿐이고
(`participant_no,a_level,mismatch_locus`), dossier 전문은 배정 계산에 들어가지 않는다.

    ./backend/.venv/bin/python scripts/make_assignment.py \
        --strata assignments/strata_v1.csv --seed 20260826 \
        --out assignments/assignment_v1.json --version assignment_v1

seed **20260826**, 1회 시도로 전 제약 통과(§5.2 ①~⑤). 로그: `assignment_v1.log`.

## a_level — 출처와 해소 규칙

`screening_deid.csv`의 `Actionability` 열. Study1 번호 → Study2 번호는 같은 파일의
`Study2 참가자 ID` 열을 따랐다(적합성 FAIL 6명 이탈 후 재번호 — P01–P24).

범위 표기(`A1-A2`·`A0-A1`) 4건은 **하한으로 해소**했다. 이 규칙은 임의로 정한 것이 아니라
같은 CSV의 「Actionability 분포」 요약 블록이 이미 쓰고 있는 것이다 — 그 블록은
Study1 P19(A1-A2)·P21(A1-A2)을 A1 그룹에, P20(A0-A1)을 A0 그룹에 넣었다.

| Study2 | Study1 | CSV 표기 | 해소 | 근거 |
|---|---|---|---|---|
| P16 | P19 | A1-A2 | **A1** | CSV 요약 블록이 A1 그룹에 넣었다 |
| P17 | P20 | A0-A1 | **A0** | CSV 요약 블록이 A0 계열에 넣었다 |
| P18 | P21 | A1-A2 | **A1** | CSV 요약 블록이 A1 그룹에 넣었다 |
| P22 | P25 | A0-A1 | **A0** | 요약 블록은 PASS 사례만 세므로 이 행(CAUTION)은 없다. **위 세 건의 선례(하한)를 확장 적용했다** |

P22만 선례 확장이다. 2차 코더가 A1로 확정하면 A0가 1건이 되고 배정표를 재생성해야 한다
(§1.4 — **첫 세션 전까지만 가능**).

분포: A2 15 · A1 7 · A0 2. dossier가 착지한 P08·P10·P23의 `a_level`은 이 표와 일치한다(교차 확인).

## mismatch_locus — 3건만 확정값

lock 대상 dossier에서 확정된 것만 실값으로 넣었다.

| 참가자 | locus | 출처 |
|---|---|---|
| P08 | `interpretation` | `dossiers/P08.json` |
| P10 | `context_memory_use` | `dossiers/P10.json` (2차 코더 대안 `interpretation` 미결 — `evidence_code.coders` 참조) |
| P23 | `interpretation` | `dossiers/P23.json` |
| 나머지 21명 | `interpretation` | **filler — 코딩 결과가 아니다** |

filler를 단일 값으로 둔 이유: locus는 §5.2 ①~④ 하드 제약에 들어가지 않고 focal 배정의
**동률 tie-break**로만 쓰인다(`make_assignment.py` `_assign_focal` ③). 21건을 한 버킷에 두면
"locus 정보 없음"과 같은 뜻이 되고, 서로 다른 값으로 흩뿌리면 없는 코딩 결과가 배정에
영향을 준 것이 된다.

⚠ **이 열을 코딩 결과로 읽지 마라.** 분석이 쓰는 locus는 dossier에서 나온다
(`analysis/export_trajectory.py`). 배정표·`participants.mismatch_locus`에 남는 값은
**생성 시점 입력 기록**이다. dossier가 착지하면 두 값이 갈라지는데, 시스템은 대조하지
않으므로 논문에는 dossier 값을 쓴다.
