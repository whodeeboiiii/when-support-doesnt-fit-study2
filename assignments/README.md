# assignments/ — 배정표 (구현명세서 §5.2 · D-30)

**시스템은 배정을 계산하지 않는다. 이 디렉터리의 표를 읽는다.**

| 파일 | 지위 | git |
|---|---|---|
| `assignment_v1.json` | **실값** — 본실험 24명의 배정 | 커밋하지 않는다(§2.9 `.gitignore`) |
| `assignment_v1.log` | 생성 로그(seed·시도 횟수·strata 분포표 — §5.2 ⑥) | 커밋하지 않는다 |
| `assignment_dummy.json` | CI·시연용 결정론 더미(P01–P24) | 커밋한다 |
| `assignment_dummy.log` | 〃 생성 로그 | 커밋한다 |

로더(`backend/app/core/assignment.py`)는 `ASSIGNMENT_PATH` → `assignment_v1.json` →
`assignment_dummy.json` 순으로 찾고, 더미로 내려가면 `is_dummy=True`를 R1과 기동 로그에
표시한다(NT-42). 더미 상태에서는 모집 게이트(PH-08)가 열리지 않는다.

## 한 행이 정하는 것

```json
{
  "participant_no": "P05",
  "a_level": "A2",
  "mismatch_locus": "content_depth",
  "focal_condition": "C3",
  "alt_order": ["C1", "C4", "C2"],
  "pair_order": ["sequence", "scope", "stopping"],
  "pair_sides": { "sequence": ["C4", "C2"], "scope": ["C1", "C3"], "stopping": ["C3", "C4"] }
}
```

- `focal_condition` — 이 참가자가 **완전한 상호작용으로 경험하는 1조건**(§0.4).
- `alt_order` — focal 측정(SS05) 완료 후 P9에서 순차 노출할 나머지 세 조건의 순서.
  **focal을 포함하면 기동이 실패한다**(§3.3 · NT-32).
- `pair_order` — P10에서 제시할 세 contrast의 순서. **전 행 정본 순서 고정**이다
  (sequence → scope → stopping — D-41, 2026-08-26 파일럿 조정). 열이 남아 있는 이유는
  런타임이 순서를 계산하지 않는다는 규율(§0.3) 때문이다 — 값의 출처는 여전히 이 표다.
- `pair_sides[contrast] = [left, right]` — 「응답 A」(좌)·「응답 B」(우)에 놓일 조건.

세 값 모두 **최초 진입 시 DB에 복사·고정**되고 이후 불변이다(NT-07·33). 표를 나중에 고쳐도
진행 중 세션은 바뀌지 않는다 — 그래서 §1.4가 "배정표는 생성 후 금지"라고 못박는다.

## 생성

```bash
# 실값 — strata(a_level)는 lock된 dossier의 evidence_code에서 읽는다(§5.2 마지막 항)
python scripts/make_assignment.py --from-dossiers --seed 20260820 --out assignments/assignment_v1.json

# CSV로 strata를 직접 주는 경우
python scripts/make_assignment.py --strata strata.csv --seed 20260820 --out assignments/assignment_v1.json

# 더미 재생성 (P01–P24, 고정 seed)
python scripts/make_assignment.py --dummy

# §10.1 — 임의 strata 분포 20종에 대해 제약 전수 통과 확인 (NT-32)
python scripts/make_assignment.py --self-test
```

## 제약 (§5.2 · NT-32 — 로더와 생성기가 같은 함수를 쓴다)

1. 24행, 참가자 번호 중복 없음
2. focal 6명/조건
3. focal group(6명) 내 `alt_order` 6순열 각 1회
4. `pair_order`가 전 행 정본 순서(`["sequence", "scope", "stopping"]` — D-41)
5. 좌우: contrast별 전체 12/12, focal group 내 3/3
6. `alt_order`에 focal 미포함
7. strata 편중: A-level별 조건 간 max−min ≤ 1 — **가능한 범위**

7번만 성격이 다르다. A0가 1–2건이면 네 조건 분산이 산술적으로 불가능하므로, 생성기는 이를
**오류가 아니라 로그의 경고**로 남기고 로더도 기동을 끊지 않는다(§5.2). 표본이 그렇게 생긴
것을 시스템이 판정할 일이 아니다.

## D-41 (2026-08-26) — 한 열 수정

파일럿 조정(§10.3)으로 `pair_order`를 정본 순서로 고정했다. **전원 재배정이 아니다**:
같은 seed(20260826)·같은 strata로 다시 생성했고 `pair_order`를 뺀 전 열이 이전 표와 동일하다
— 생성기가 pair 순서 draw를 소비만 하고 버려서 rng 스트림이 보존된다(`make_assignment.py` ③).
표 버전만 `assignment_v1` → `assignment_v1.1`로 올렸고, 이미 진행한 세션(P08·P23)은
`participants.assignment_version`으로 구분된다. **P08은 stopping 먼저로 진행했고**, 그 세션의
정본은 DB(`participants.pair_order`·`pairwise_views`)다.

⚠ `--dummy` 재생성은 이제 이 리포의 커밋된 더미 표를 재현하지 않는다 — `_dummy_strata()`가
`dossier_loader.load()`로 strata를 읽는데 실값 dossier(P08·P10·P23)가 착지한 뒤로 그 세 행의
a_level·locus가 schema_dummy와 달라졌기 때문이다. 커밋된 표는 생성 당시 값을 보존한다.

## 재생성

배정표 재생성 = **새 seed · 새 버전 · 전원 재배정**이며 **모집 전에만** 가능하다(§1.4).
모집이 시작된 뒤에는 금지다. 재생성하면 파일명을 `assignment_v2.json`으로 올리고 로그를
함께 보관한다 — `assignment_version`이 `participants` 행에 복사되므로(§8.1) 어느 표로 배정된
세션인지 사후에 구분된다.
