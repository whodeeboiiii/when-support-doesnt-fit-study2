/**
 * P11 사후 인터뷰 화면 · P12 디브리핑 · 종료·중단 화면 (§4.11–§4.12 · §9.1).
 *
 * **[파일럿 확정 2026-08-26] P11이 다시 쓰였다.** 구판은 세 pair를 좌우 그대로 재배치한
 * 화면이었는데, pair별 인터뷰가 P10에서 끝나게 되면서(§4.10) 그 배치가 할 일이 없어졌다.
 * 지금 P11은 **전체를 한 번에 놓고 보는 자리**다 — 처음 상황 → 그때의 대화 → 나머지 세 응답.
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
import { CheckpointCard } from './Intro'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

interface FocalTurn {
  role: 'user' | 'ai'
  text: string
}

interface Alternative {
  label: string
  ai1: string
}

export function InterviewHold({ state, onState }: ScreenProps) {
  const focalTurns: FocalTurn[] = state.data.focal_turns ?? []
  const alternatives: Alternative[] = state.data.alternatives ?? []
  const { busy, error, run } = useSubmit(onState)

  return (
    <div className="screen">
      <DevScreenNote
        screen="P11"
        term="사후 인터뷰"
        detail="§4.11 [파일럿 확정 2026-08-26] — 시나리오 · focal 대화 · 나머지 세 응답을 읽기 전용으로. 문항·평정값·조건 라벨은 없다(NT-39). 인터뷰는 Zoom 구두(부록 D.3)."
      />
      <ScreenTitle>{state.data.scenario_title}</ScreenTitle>
      <CheckpointCard checkpoint={state.data.scenario} />

      {focalTurns.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-3 text-sm font-semibold text-gray-600">{state.data.focal_title}</h2>
          <div className="chat">
            {focalTurns.map((turn, index) => (
              <Bubble
                key={index}
                role={turn.role}
                text={turn.text}
                note={turn.role === 'ai' ? state.data.ai1_note : null}
              />
            ))}
          </div>
        </section>
      )}

      {alternatives.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-3 text-sm font-semibold text-gray-600">
            {state.data.alternatives_title}
          </h2>
          {/* pairwise 배치가 아니라 **나열**이다 — 여기서는 비교를 시키지 않는다(§4.11). */}
          <div className="space-y-6">
            {alternatives.map((alternative) => (
              <div key={alternative.label} className="sec">
                <p className="mb-3 text-sm font-semibold text-gray-600">{alternative.label}</p>
                <div className="chat">
                  <Bubble role="ai" text={alternative.ai1} note={state.data.ai1_note} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

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
