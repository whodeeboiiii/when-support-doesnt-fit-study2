/**
 * 서버 API 클라이언트 (구현명세서 §8.2 · §1.3).
 *
 * 이 파일에는 **연구 상태가 없다**. 화면 선택도 다음 단계도 서버가 정하고(`GET /state`),
 * 클라이언트는 응답으로 받은 상태를 그대로 그린다(§1.3 · §3.5). 그래서 여기 함수들은 전부
 * `AppState`를 돌려주고, 그 값을 상위 컴포넌트가 통째로 교체한다.
 *
 * 자산·문안도 서버가 내려준다 — 번들에 자극·문항·조건 라벨을 넣지 않는다(NT-13).
 */

export interface AppState {
  /** P0 · P1 · P1S · P2–P12 · DONE · ABORTED */
  screen: string
  ss_state: string
  f_state: string | null
  /** §3.3 진행 위치 — 제출 경로용이다. 화면에 숫자로 표시하지 않는다. */
  alt_index: number | null
  pair_index: number | null
  participant_no: string
  status: string
  data: Record<string, any>
  /** `POST /join` 응답에만 있다 — 저장 지점 복원 여부(§3.5). */
  restored?: boolean
  /** 중복 제출이 기존 레코드로 응답됐는가(§9.1 · NT-09). */
  replayed?: boolean
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!response.ok) {
    let detail = ''
    try {
      detail = (await response.json())?.detail ?? ''
    } catch {
      detail = ''
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  state: () => request<AppState>('/api/state'),

  join: (participantNo: string, accessCode: string) =>
    post<AppState>('/api/join', {
      participant_no: participantNo,
      access_code: accessCode,
      // §4.0 저장 항목 — 뷰포트는 데스크톱 가드(§2.10)의 근거 기록이기도 하다.
      viewport: { width: window.innerWidth, height: window.innerHeight },
    }),

  consent: (items: Record<string, boolean>) => post<AppState>('/api/consent', { items }),

  /** v1.0.1 §4.2 · D-44 — 위치로만 오간다(문항 ID 미노출 — NT-05). */
  presurvey: (responses: { position: number; value: unknown }[]) =>
    post<AppState>('/api/presurvey', { responses }),

  /** §4.2 · D-25 — segment 단위 수정. 누적 저장되고 확인 후에는 409다. */
  checkpointEdit: (segment: string, text: string) =>
    post<AppState>('/api/checkpoint/edit', { segment, text }),

  checkpointConfirm: () => post<AppState>('/api/checkpoint/confirm'),

  /** 자체 제출물이 없는 전이 — P3·P6·P7·P9·P11 (§8.2 `POST /advance`). */
  advance: (fromScreen: string) => post<AppState>('/api/advance', { from_screen: fromScreen }),

  /** §4.4 · D-32 — User1은 **필수**다. disposition 인자가 없다. */
  user1: (text: string) => post<AppState>('/api/focal/user1', { text }),

  /** §4.5 · D-28 — 3단 조건부. 분기 규칙은 서버가 검증한다(NT-36). */
  sidecar: (body: {
    has_more: boolean
    free_text?: string
    provenance?: string
    reason?: string
  }) => post<AppState>('/api/focal/sidecar', body),

  ai2: () => post<AppState>('/api/focal/ai2'),

  /** §4.7 · D-26 — reply(User2) 또는 end(이탈 유형 + 이유). */
  downstream: (body: {
    disposition: 'reply' | 'end'
    text?: string
    end_type?: string
    reason?: string
  }) => post<AppState>('/api/focal/downstream', body),

  /** §4.8 — focal 5 construct + MC 2. 위치로만 오간다(문항 ID 미노출). */
  ratings: (items: { position: number; value: number }[]) =>
    post<AppState>('/api/ratings', { items }),

  /** §4.10 — position = `pair_index`. */
  pairwise: (position: number, items: { position: number; value: number }[]) =>
    post<AppState>(`/api/pairwise/${position}`, { items }),

  debriefConfirm: () => post<AppState>('/api/debrief/confirm'),

  /**
   * beacon (§2.11 · NT-29). 실패해도 무시한다 — 이벤트 유실이 참가자 진행을 막지 않는다.
   * ⚠ keystroke·삭제 이력·수정 과정은 보내지 않는다(§4.5 금지).
   */
  event: (type: string, payload?: Record<string, unknown>) =>
    post('/api/events', {
      type,
      client_ts: new Date().toISOString(),
      payload,
    }).catch(() => undefined),
}

/**
 * 개발용 API (서버가 DEV_MODE + 로컬 DB일 때만 존재한다 — `backend/app/api/dev.py`).
 *
 * 배포 빌드에도 이 코드는 들어가지만, 서버에 경로가 없으면 `status()`가 null을 돌려주고
 * 개발 바는 아무것도 그리지 않는다. **존재 여부를 클라이언트가 판단하지 않는다** — 빌드
 * 플래그로 가르면 "배포인데 개발 빌드"라는 조합이 생긴다.
 */
export interface DevSessionRow {
  participant_no: string
  ss_state: string
  f_state: string | null
  status: string
}

export interface DevStatus {
  participants: string[]
  default_participant: string
  sessions: DevSessionRow[]
}

export const dev = {
  status: async (): Promise<DevStatus | null> => {
    try {
      return await request<DevStatus>('/api/dev/status')
    } catch {
      return null
    }
  },

  /** 참가자 산출물을 지우고 새 접속 코드를 발급한다. 접속은 P0에서 사람이 한다. */
  reset: (participantNo: string) =>
    post<{ participant_no: string; access_code: string; deleted: Record<string, number> }>(
      '/api/dev/reset',
      { participant_no: participantNo },
    ),
}
