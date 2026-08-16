/**
 * P10 cross-branch review · P11 디브리핑 · 종료·중단 화면 (구현명세서 §4.10–§4.11 · §9.1).
 *
 * P10은 네 trajectory를 나란히 재표시한다. 라벨은 **번호로만** — 조건명·구성 원리는 표시하지
 * 않는다(§4.10 construct label 비공개). sidecar 내용도 재표시하지 않는다 `<TODO: PH-02>`.
 *
 * 인터뷰는 Zoom 구두 진행이고 이 화면은 참조용이다. 종료 버튼은 참가자가 누른다(§3.1).
 */

import { api } from '../api'
import { Bubble } from '../components/Chat'
import { SubmitBar } from '../components/Inputs'
import { DONE_NOTICE, NEXT } from '../copy'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

interface Trajectory {
  index: number
  label: string
  ai1: string | null
  user1: string | null
  disposition: string | null
  ai2: string | null
  downstream: string | null
}

export function CrossReview({ state, onState }: ScreenProps) {
  const branches: Trajectory[] = state.data.branches ?? []
  const { busy, error, run } = useSubmit(onState)

  return (
    <div className="screen" style={{ maxWidth: '1200px' }}>
      <ScreenTitle>네 번의 대화 되돌아보기</ScreenTitle>
      <div className="grid grid-cols-4 gap-4">
        {branches.map((branch) => (
          <section key={branch.index} className="sec space-y-3">
            <h2 className="text-sm font-semibold text-gray-600">{branch.label}</h2>
            {branch.ai1 && <Bubble role="ai" text={branch.ai1} />}
            {branch.user1 && <Bubble role="user" text={branch.user1} />}
            {/* no_reply/end는 빈칸이 아니라 그 자체가 하나의 trajectory다(§3.2). */}
            {!branch.user1 && (
              <p className="text-sm text-gray-500">
                {branch.disposition === 'end' ? '대화를 끝냈습니다' : '답장을 보내지 않았습니다'}
              </p>
            )}
            {branch.ai2 && <Bubble role="ai" text={branch.ai2} />}
            {branch.downstream && (
              <p className="text-sm text-gray-600">선택: {branch.downstream}</p>
            )}
          </section>
        ))}
      </div>
      <SubmitBar
        label={state.data.end_button}
        busy={busy}
        error={error}
        onClick={() => run(() => api.advance('P10'))}
      />
    </div>
  )
}

export function Debrief({ state, onState }: ScreenProps) {
  const { busy, error, run } = useSubmit(onState)
  return (
    <div className="screen">
      <ScreenTitle>디브리핑</ScreenTitle>
      <div className="callout whitespace-pre-wrap">{state.data.notice}</div>
      <SubmitBar
        label={state.data.button ?? NEXT}
        busy={busy}
        error={error}
        onClick={() => run(() => api.debriefConfirm())}
      />
    </div>
  )
}

export function Ended({ state }: { state: { screen: string; data: Record<string, any> } }) {
  // §9.1 — abort는 안내 화면으로 수렴한다. 어느 쪽도 막다른 흰 화면이 아니다.
  const message = state.screen === 'ABORTED' ? state.data.message : DONE_NOTICE
  return (
    <div className="screen">
      <p>{message}</p>
    </div>
  )
}
