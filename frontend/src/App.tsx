/**
 * 앱 셸 — 서버 상태 → 화면 (구현명세서 §1.3 · §3.5 · §2.10).
 *
 * **클라이언트 라우터가 없다.** URL은 하나이고, 어느 화면을 그릴지는 `GET /state`가 알려준
 * SS·F 상태가 정한다. 새로고침·뒤로가기가 연구 상태를 흔들 수 없는 구조다(§3.5 · NT-08).
 *
 * 데스크톱 가드(§2.10 · NT-19): 뷰포트 폭이 1024px 미만이면 어떤 화면도 그리지 않는다. 모바일
 * 대응 CSS를 쓰지 않기로 한 이상(D-12), 좁은 화면에서 "어떻게든 보이게" 두면 자극 표시 조건이
 * 참가자마다 달라진다.
 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError, AppState, api } from './api'
import { DESKTOP_ONLY, MIN_VIEWPORT_WIDTH, RESTORING } from './copy'
import DevBar, { DevPrefill } from './components/DevBar'
import { AltExposure, Pairwise } from './screens/Exposure'
import { Ai2, Chat, Downstream, Ratings, Reentry, Sidecar } from './screens/Focal'
import { Checkpoint, Consent } from './screens/Intro'
import Join from './screens/Join'
import { Debrief, Ended, InterviewHold } from './screens/Wrap'

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
  // DEV_MODE 초기화가 발급한 접속 코드 — P0 입력칸을 채우는 용도뿐이다(자동 접속 아님).
  const [devPrefill, setDevPrefill] = useState<DevPrefill | null>(null)
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
    if (state) api.event('screen_enter', { screen: state.screen })
  }, [state?.screen, state?.alt_index, state?.pair_index])

  if (tooNarrow) return <DesktopGuard />
  if (loading) return <div className="screen">{RESTORING}</div>

  // 배포 구성에서는 `/api/dev/status`가 404라서 이 컴포넌트가 아무것도 그리지 않는다.
  const devBar = (
    <DevBar
      onReset={(prefill) => {
        setDevPrefill(prefill)
        // 세션이 지워졌으므로 P0으로 — 다음 회차도 접속부터 정상 경로를 밟는다.
        setState(null)
      }}
    />
  )

  if (!state)
    return (
      <>
        {/* 코드가 바뀌면 입력칸을 새로 만든다(이미 P0에 있을 때도 채워지도록). */}
        <Join key={devPrefill?.accessCode ?? 'join'} onState={setState} prefill={devPrefill} />
        {devBar}
      </>
    )

  return (
    <>
      <Screen state={state} onState={setState} />
      {devBar}
    </>
  )
}

/** 상태 → 화면 (P0–P12). 전이는 서버가 정하고 여기서는 받은 화면 ID를 그리기만 한다(§1.3). */
function Screen({ state, onState }: { state: AppState; onState: (next: AppState) => void }) {
  const props = { state, onState }
  switch (state.screen) {
    case 'P1':
      return <Consent {...props} />
    case 'P2':
      return <Checkpoint {...props} />
    case 'P3':
      return <Reentry {...props} />
    case 'P4':
      return <Chat {...props} />
    case 'P5':
      return <Sidecar {...props} />
    case 'P6':
      return <Ai2 {...props} />
    case 'P7':
      return <Downstream {...props} />
    case 'P8':
      return <Ratings {...props} />
    case 'P9':
      // 대안이 바뀌면 타이핑 인디케이터부터 다시 — 앞 대안의 표시 상태가 남지 않는다(§4.9).
      return <AltExposure key={`p9-${state.alt_index}`} {...props} />
    case 'P10':
      return <Pairwise key={`p10-${state.pair_index}`} {...props} />
    case 'P11':
      return <InterviewHold {...props} />
    case 'P12':
      return <Debrief {...props} />
    default:
      return <Ended state={state} />
  }
}
