/**
 * P11 contrastive interview 대기 · P12 디브리핑 · 종료·중단 화면 (§4.11–§4.12 · §9.1).
 *
 * **P11이 v1.0.1의 P10(cross-branch review)을 대체한다.** 네 trajectory를 나란히 보여 주던
 * 화면은 사라졌고(4-branch 설계와 함께), 대신 **세 pair를 제시된 순서·좌우 그대로** 읽기
 * 전용으로 세로 배치한다. 참가자가 인터뷰 중 참조하는 화면이다.
 *
 * 여기 없는 것이 중요하다(NT-39): 문항·응답값 재표시 없음, sidecar 없음, 조건 라벨 없음,
 * researcher_only 없음. 그것들은 연구자 R3에만 있다.
 *
 * 인터뷰는 Zoom 구두 진행이고(부록 D.3) 종료 버튼은 참가자가 누른다(§4.11).
 */

import { api } from '../api'
import { Bubble } from '../components/Chat'
import { SubmitBar } from '../components/Inputs'
import { DONE_NOTICE, NEXT } from '../copy'
import { DevScreenNote } from '../components/DevNote'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

interface PairView {
  position: number
  label: string
  sides: { label: string; ai1: string }[]
}

export function InterviewHold({ state, onState }: ScreenProps) {
  const pairs: PairView[] = state.data.pairs ?? []
  const { busy, error, run } = useSubmit(onState)

  return (
    <div className="screen" style={{ maxWidth: '1100px' }}>
      <DevScreenNote
        screen="P11"
        term="Contrastive Interview 대기"
        detail="§4.11 — 세 pair를 제시 순서·좌우 그대로 읽기 전용 재배치. 문항·응답값은 재표시하지 않는다. 인터뷰는 Zoom 구두(부록 D.3)."
      />
      <ScreenTitle>비교한 응답들</ScreenTitle>
      <div className="space-y-10">
        {pairs.map((pair) => (
          <section key={pair.position}>
            <h2 className="mb-3 text-sm font-semibold text-gray-600">{pair.label}</h2>
            {/* P10과 같은 열 규칙 — 폭 동일, 높이 맞춤, 열 내부 스크롤 없음(§4.11). */}
            <div className="grid grid-cols-2 gap-5">
              {pair.sides.map((side) => (
                <div key={side.label} className="sec flex flex-col">
                  <p className="mb-3 text-sm font-semibold text-gray-600">{side.label}</p>
                  <div className="chat">
                    <Bubble role="ai" text={side.ai1} wide />
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      <SubmitBar
        label={state.data.button}
        busy={busy}
        error={error}
        onClick={() => run(() => api.advance('P11'))}
      />
    </div>
  )
}

export function Debrief({ state, onState }: ScreenProps) {
  const { busy, error, run } = useSubmit(onState)
  return (
    <div className="screen">
      <DevScreenNote
        screen="P12"
        term="디브리핑"
        detail="§4.12 — 필수 공개 7항목. 문안은 IRB 초안 착지본이고 승인 대기다(PH-IRB-2)."
      />
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
      <DevScreenNote
        screen="—"
        term="세션 종료"
        detail="§9.1 — 정상 종료·중단의 종착 화면. 모든 오류 경로가 여기로 수렴한다."
      />
      <p>{message}</p>
    </div>
  )
}
