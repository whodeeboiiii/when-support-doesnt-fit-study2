/**
 * AI2 로딩 화면 (구현명세서 §4.7 · §9.1 — 구 리포 `screens/Loading.tsx` 이식·개조).
 *
 * 참가자 화면에서는 정상 생성·재생성·fallback이 **구분되지 않는다**(§4.7). 그러니 "검증
 * 중"·"다시 만드는 중" 같은 진행 문구를 쓰지 않는다 — 파이프라인 내부 상태는 연구자 콘솔
 * R2에만 표시된다(§4.12).
 *
 * 지연 안내 문안은 §9.1 표의 것을 쓴다: "답변 준비가 지연되고 있습니다…".
 */

import { useEffect, useState } from 'react'

interface LoadingProps {
  /** §4.7 로딩 문안 [제안]: "AI가 답변을 작성하고 있습니다…" */
  text: string
  /** 이 시각(ms)을 넘기면 §9.1의 지연 안내로 바꾼다. */
  delayNoticeAtMs?: number
  delayNoticeText?: string
}

export default function Loading({
  text,
  delayNoticeAtMs = 20_000,
  delayNoticeText = '답변 준비가 지연되고 있습니다…',
}: LoadingProps) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    // Date.now() 차분 방식 — setInterval 누적을 신뢰하지 않는다.
    const start = Date.now()
    const timer = window.setInterval(() => setElapsed(Date.now() - start), 500)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="screen" aria-live="polite">
      <p>{elapsed >= delayNoticeAtMs ? delayNoticeText : text}</p>
      <div className="mt-6 h-1 w-full animate-pulse rounded bg-accent" />
    </div>
  )
}
