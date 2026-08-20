/**
 * 서버 API 클라이언트 (구현명세서 §8.2 · §1.3).
 *
 * 이 파일에는 **연구 상태가 없다**. 화면 선택도 다음 단계도 서버가 정하고(`GET /state`),
 * 클라이언트는 응답으로 받은 상태를 그대로 그린다(§1.3 · §3.5). 그래서 여기 함수들은 전부
 * `AppState`를 돌려주고, 그 값을 상위 컴포넌트가 통째로 교체한다.
 *
 * 자산·문안도 서버가 내려준다 — 번들에 자극·문항을 넣지 않는다(NT-13).
 */

export interface AppState {
  screen: string
  ss_state: string
  b_state: string | null
  /** 제출 경로용 값이다 — **화면에 표시하지 않는다**(§4.4). */
  branch_index: number | null
  participant_no: string
  status: string
  has_ai2: boolean | null
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

  presurvey: (responses: { position: number; value: unknown }[]) =>
    post<AppState>('/api/presurvey', { responses }),

  checkpointConfirm: () => post<AppState>('/api/checkpoint/confirm'),

  /** 자체 제출물이 없는 전이 — P4·P7·P10 (§8.2 `POST /advance`). */
  advance: (fromScreen: string) => post<AppState>('/api/advance', { from_screen: fromScreen }),

  user1: (branch: number, disposition: string, text?: string) =>
    post<AppState>(`/api/branch/${branch}/user1`, { disposition, text }),

  sidecar: (
    branch: number,
    body: { choice: string; free_text?: string; relevance?: number; reason?: string },
  ) => post<AppState>(`/api/branch/${branch}/sidecar`, body),

  ai2: (branch: number) => post<AppState>(`/api/branch/${branch}/ai2`),

  downstream: (branch: number, code: string) =>
    post<AppState>(`/api/branch/${branch}/downstream`, { code }),

  ratings: (branch: number, items: { position: number; value: number }[]) =>
    post<AppState>(`/api/branch/${branch}/ratings`, { items }),

  debriefConfirm: () => post<AppState>('/api/debrief/confirm'),

  /**
   * beacon (§2.11 · NT-29). 실패해도 무시한다 — 이벤트 유실이 참가자 진행을 막지 않는다.
   * ⚠ keystroke·삭제 이력·수정 과정은 보내지 않는다(§4.6 금지).
   */
  event: (type: string, branchIndex?: number | null, payload?: Record<string, unknown>) =>
    post('/api/events', {
      type,
      branch_index: branchIndex ?? null,
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
  branch_index: number | null
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
