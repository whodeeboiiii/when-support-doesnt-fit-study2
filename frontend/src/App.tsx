/**
 * 앱 셸 — 서버 상태 → 화면 (구현명세서 §1.3 · §3.5 · §2.10).
 *
 * **클라이언트 라우터가 없다.** URL은 하나이고, 어느 화면을 그릴지는 `GET /state`가 알려준 SS·B
 * 상태가 정한다. 새로고침·뒤로가기가 연구 상태를 흔들 수 없는 구조다(§3.5 · NT-08).
 *
 * 데스크톱 가드(§2.10 · NT-19): 뷰포트 폭이 1024px 미만이면 어떤 화면도 그리지 않는다. 모바일
 * 대응 CSS를 쓰지 않기로 한 이상(D-12), 좁은 화면에서 "어떻게든 보이게" 두면 자극 표시 조건이
 * 참가자마다 달라진다.
 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError, AppState, api } from './api'
import { DESKTOP_ONLY, MIN_VIEWPORT_WIDTH, RESTORING } from './copy'
import { Chat, Ai2, Downstream, Ratings, Reentry, Sidecar } from './screens/Branch'
import { Checkpoint, Consent, Presurvey } from './screens/Intro'
import Join from './screens/Join'
import { CrossReview, Debrief, Ended } from './screens/Wrap'

function DesktopGuard() {
  return (
    <div className="screen">
      <p role="alert">{DESKTOP_ONLY}</p>
    </div>
  )
}

function useViewportGuard(): boolean {
  const [tooNarrow, setTooNarrow] = useState(() => window.innerWidth < MIN_VIEWPORT_WIDTH)
  useEffect(() => {
    const onResize = () => setTooNarrow(window.innerWidth < MIN_VIEWPORT_WIDTH)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return tooNarrow
}

export default function App() {
  const [state, setState] = useState<AppState | null>(null)
  const [loading, setLoading] = useState(true)
  const tooNarrow = useViewportGuard()

  const restore = useCallback(async () => {
    try {
      setState(await api.state())
    } catch (reason) {
      // 세션이 없으면 P0으로 — 401은 오류 화면이 아니라 접속 화면이다(§9.1).
      if (!(reason instanceof ApiError) || reason.status !== 401) {
        console.warn('상태 복구 실패', reason)
      }
      setState(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void restore()
  }, [restore])

  useEffect(() => {
    if (state) api.event('screen_enter', state.branch_index, { screen: state.screen })
  }, [state?.screen, state?.branch_index])

  if (tooNarrow) return <DesktopGuard />
  if (loading) return <div className="screen">{RESTORING}</div>
  if (!state) return <Join onState={setState} />

  const props = { state, onState: setState }
  switch (state.screen) {
    case 'P1':
      return <Consent {...props} />
    case 'P2':
      return <Presurvey {...props} />
    case 'P3':
      return <Checkpoint {...props} />
    case 'P4':
      return <Reentry {...props} />
    case 'P5':
      // branch가 바뀌면 채팅 화면 상태를 새로 만든다 — 이전 branch의 입력이 남지 않는다(§3.4 reset).
      return <Chat key={`p5-${state.branch_index}`} {...props} />
    case 'P6':
      return <Sidecar key={`p6-${state.branch_index}`} {...props} />
    case 'P7':
      return <Ai2 key={`p7-${state.branch_index}`} {...props} />
    case 'P8':
      return <Downstream key={`p8-${state.branch_index}`} {...props} />
    case 'P9':
      return <Ratings key={`p9-${state.branch_index}`} {...props} />
    case 'P10':
      return <CrossReview {...props} />
    case 'P11':
      return <Debrief {...props} />
    default:
      return <Ended state={state} />
  }
}
