/**
 * DEV_MODE 설명 레이블 — **명세서 범위 밖의 개발 도구**다(연구 화면 아님).
 *
 * 팀원에게 화면을 설명할 때 "이 박스가 초안의 무엇인가"를 화면 위에서 바로 가리키기 위한
 * 것이다. `DevBar`와 같은 두 가지 규율을 지킨다.
 *
 * 1. **존재 여부를 서버가 정한다.** `/api/dev/status`가 404면(= 배포 구성) 아무것도 그리지
 *    않는다. 프런트에 "지금이 개발이다"라고 믿는 플래그(`import.meta.env.DEV` 등)를 두지
 *    않는다 — 빌드 설정 하나가 참가자에게 연구 용어를 노출시키는 경로가 되면 안 된다.
 * 2. **참가자 화면의 자극을 건드리지 않는다.** 레이블은 보라 계열로 DevBar와 같은 색을
 *    쓴다. 연구 UI의 색 토큰(ink·accent·guide)을 쓰면 자극의 일부로 읽힌다.
 *
 * 레이블 문안은 `docs/연구 7 초안 - 섹션 6, 7.md`의 용어를 **그대로** 쓴다. 참가자에게는
 * 절대 보이지 않으므로 §4.10 construct label 비공개와 충돌하지 않는다.
 */

import { ReactNode, useEffect, useState } from 'react'
import { dev } from '../api'

/**
 * `/api/dev/status`를 창 수명당 **한 번만** 부른다.
 *
 * 레이블은 화면마다 여러 개가 붙는다 — 각자 fetch하면 화면 전환마다 요청이 수십 건이 된다.
 * 모듈 수준 promise를 공유하면 소비자 수와 무관하게 요청은 1건이다.
 */
let devModeProbe: Promise<boolean> | null = null

function probeDevMode(): Promise<boolean> {
  if (!devModeProbe) devModeProbe = dev.status().then((status) => status !== null)
  return devModeProbe
}

export function useDevMode(): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    let alive = true
    void probeDevMode().then((result) => {
      if (alive) setOn(result)
    })
    return () => {
      alive = false
    }
  }, [])
  return on
}

interface NoteProps {
  /** 초안의 용어를 그대로 (예: "AI-visible Layer"). */
  term: string
  /** 출처 절과 한 줄 설명 (예: "§7.3 최소 context"). */
  detail?: string
}

/** 작은 보라 알약 하나. DEV_MODE가 아니면 아무것도 그리지 않는다. */
export function DevNote({ term, detail }: NoteProps) {
  const on = useDevMode()
  if (!on) return null
  return (
    <span className="inline-flex shrink-0 flex-col items-start rounded-md border border-violet-400 bg-violet-50 px-2 py-1 text-[11px] leading-tight text-violet-900">
      <span className="font-semibold">{term}</span>
      {detail && <span className="text-violet-700">{detail}</span>}
    </span>
  )
}

/** 박스 **옆에** 레이블을 붙인다 — DEV_MODE가 아니면 자식만 그대로 그린다(레이아웃 무변화). */
export function DevAside({ term, detail, children }: NoteProps & { children: ReactNode }) {
  const on = useDevMode()
  if (!on) return <>{children}</>
  return (
    <div className="flex items-start gap-2">
      <div className="min-w-0 flex-1">{children}</div>
      <DevNote term={term} detail={detail} />
    </div>
  )
}

/** 화면 맨 위 한 줄 — 이 화면이 초안·명세의 어디인지. */
export function DevScreenNote({ screen, term, detail }: NoteProps & { screen: string }) {
  const on = useDevMode()
  if (!on) return null
  return (
    <div className="mb-4 rounded-md border border-dashed border-violet-400 bg-violet-50 px-3 py-2 text-xs text-violet-900">
      <span className="mr-2 rounded bg-violet-200 px-1.5 py-0.5 font-mono font-semibold">
        {screen}
      </span>
      <span className="font-semibold">{term}</span>
      {detail && <span className="text-violet-700"> — {detail}</span>}
    </div>
  )
}
