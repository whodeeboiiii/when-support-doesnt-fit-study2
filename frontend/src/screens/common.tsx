/**
 * 화면 공통 (구현명세서 §1.3 · §9.1).
 *
 * 모든 화면이 같은 계약을 따른다: 서버 상태(`state`)를 받아 그리고, 제출 결과로 받은 새 상태를
 * `onState`로 올린다. 화면이 스스로 다음 화면을 정하지 않는다 — 정하는 순간 §3.5의 복구가
 * 화면마다 달라진다.
 *
 * 오류는 **화면 안에서** 끝난다(§9.1 dead-end 금지): 실패하면 같은 화면에 사유를 띄우고 다시
 * 제출할 수 있게 둔다. 화면을 갈아치우거나 상태를 되돌리지 않는다.
 */

import { useState } from 'react'
import { ApiError, AppState } from '../api'
import { SAVE_FAILED } from '../copy'

export interface ScreenProps {
  state: AppState
  onState: (next: AppState) => void
}

export function useSubmit(onState: (next: AppState) => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (action: () => Promise<AppState>) => {
    setBusy(true)
    setError(null)
    try {
      onState(await action())
    } catch (reason) {
      // 서버가 준 사유가 있으면 그대로 보여준다(§9.1 표의 문안이 서버에 있다).
      const detail = reason instanceof ApiError ? reason.message : ''
      setError(detail || SAVE_FAILED)
    } finally {
      setBusy(false)
    }
  }

  return { busy, error, setError, run }
}

/** 화면 제목 — Zoom 화면공유에서 지금 어느 단계인지 보이게 한다(§0.2 운영 형태). */
export function ScreenTitle({ children }: { children: React.ReactNode }) {
  return <h1 className="screen-title">{children}</h1>
}
