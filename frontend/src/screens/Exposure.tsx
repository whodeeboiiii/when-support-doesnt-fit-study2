/**
 * P9 대안 노출 ×3 · P10 pairwise ×3 (구현명세서 §4.9 · §4.10 · D-29).
 *
 * v2.0 신설. 이 두 화면은 **focal 측정(SS05)이 끝난 뒤에만** 존재한다 — 그 전에는 서버
 * payload에 대안 자극이 아예 없다(NT-31). 클라이언트가 "아직 보여주면 안 된다"를 판단하지
 * 않는다는 것이 요점이다.
 *
 * 화면 규율 셋.
 * ① **조건명을 쓰지 않는다.** P9의 라벨은 "다른 응답 1/2/3", P10은 「응답 A」/「응답 B」다.
 *    어느 쪽이 focal이었는지도 라벨링하지 않는다(§4.10).
 * ② **P9에는 입력창이 없다.** 대안에 대한 User1·sidecar·AI2·개별 평정을 받지 않는다
 *    (§0.3 · 초안 §7.10 — 대안은 contrastive referent다).
 * ③ **순서·좌우는 서버가 준 그대로** 그린다. 배정표가 정한 값이고 클라이언트는 모른다.
 */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Bubble, TypingIndicator } from '../components/Chat'
import { SubmitBar } from '../components/Inputs'
import { LikertList } from '../components/Likert'
import { SUBMIT } from '../copy'
import { DevScreenNote } from '../components/DevNote'
import { CheckpointCard } from './Intro'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

// --------------------------------------------------------------------------- //
// P9 — 대안 노출 (§4.9)
// --------------------------------------------------------------------------- //

export function AltExposure({ state, onState }: ScreenProps) {
  const typingMs: number = state.data.typing_ms ?? 1500
  const [shown, setShown] = useState(false)
  const { busy, error, run } = useSubmit(onState)
  const beaconed = useRef(false)

  useEffect(() => {
    // focal과 **동일한** 채팅 화면·동일한 타이핑 인디케이터다(§4.9 — 형식 차이가 조건 차이로
    // 오인되면 안 된다).
    const timer = window.setTimeout(() => setShown(true), typingMs)
    return () => window.clearTimeout(timer)
  }, [typingMs])

  useEffect(() => {
    if (shown && !beaconed.current) {
      beaconed.current = true
      api.event('render_complete', { screen: 'P9', position: state.alt_index ?? 0 })
    }
  }, [shown, state.alt_index])

  return (
    <div className="screen">
      <DevScreenNote
        screen="P9"
        term="Alternative Exposure ×3"
        detail="§4.9·초안 §7.10 — 나머지 세 AI1을 차례로 본다(focal은 재노출 없음). 입력창 없음. 대안은 focal 측정(SS05) 완료 전에는 어떤 payload에도 실리지 않는다(NT-31)."
      />
      {/* 첫 대안 진입 시 1회 안내(§4.9). */}
      {state.data.intro && (
        <div className="callout mb-6 whitespace-pre-wrap">{state.data.intro}</div>
      )}
      <ScreenTitle>{state.data.label}</ScreenTitle>

      <CheckpointCard checkpoint={state.data.checkpoint} />
      <div className="chat mt-4">
        {/* 대안 AI1 — focal AI1(P4)·AI2(P6)와 **완전히 같은** `isNew`다(D-39).
            하이라이트가 조건마다 다르면 그 자체가 조작이 된다. */}
        {shown ? <Bubble role="ai" text={state.data.ai1} isNew /> : <TypingIndicator />}
      </div>

      {/* 입력창 없음 — 답장을 작성하지 않는다(§4.9). */}
      <SubmitBar
        label={state.data.button}
        busy={busy}
        disabled={!shown}
        error={error}
        onClick={() => run(() => api.advance('P9'))}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P10 — pairwise (§4.10)
// --------------------------------------------------------------------------- //

interface Side {
  label: string
  ai1: string
}

export function Pairwise({ state, onState }: ScreenProps) {
  const position: number = state.data.position ?? state.pair_index ?? 1
  const sides: Side[] = state.data.sides ?? []
  const items: { position: number; text: string }[] = state.data.items ?? []
  const scale = state.data.scale ?? { min: 1, max: 7 }
  const [values, setValues] = useState<Record<string, number>>({})
  const [openCheckpoint, setOpenCheckpoint] = useState(false)
  const { busy, error, run } = useSubmit(onState)

  return (
    <div className="screen" style={{ maxWidth: '1100px' }}>
      <DevScreenNote
        screen="P10"
        term="Contrastive Evaluation ×3"
        detail="§4.10·초안 §7.11 — 「응답 A」/「응답 B」 좌우 비교(좌우는 배정표가 정한다). 어느 쪽이 focal이었는지 라벨링하지 않는다."
      />
      <ScreenTitle>
        두 응답 비교 ({position}/{state.data.total ?? 3})
      </ScreenTitle>
      <p className="callout mb-6 whitespace-pre-wrap">{state.data.intro}</p>

      {/* 상단 effective checkpoint 접이식 카드 — **기본 접힘**(§4.10). */}
      <div className="mb-6">
        <button
          type="button"
          onClick={() => setOpenCheckpoint((open) => !open)}
          aria-expanded={openCheckpoint}
          className="btn-secondary h-10 text-sm"
        >
          {state.data.checkpoint_toggle} {openCheckpoint ? '▲' : '▼'}
        </button>
        {openCheckpoint && (
          <div className="mt-4">
            <CheckpointCard checkpoint={state.data.checkpoint} />
          </div>
        )}
      </div>

      {/* 두 열 — 좌우는 배정표가 정한다. focal 여부는 표시하지 않는다(§4.10).
          `grid-cols-2`는 폭이 정확히 같고, 기본 `items-stretch`라 두 열 높이가 맞는다.
          **열 안에 스크롤을 두지 않는다** — 긴 응답은 페이지가 통째로 늘어나야 두 응답을
          같은 조건에서 읽는다(한쪽만 스크롤되면 비교 자체가 비대칭이 된다). */}
      <div className="grid grid-cols-2 gap-5">
        {sides.map((side) => (
          <section key={side.label} className="sec flex flex-col">
            {/* 헤더 고정 — 긴 응답을 스크롤하는 동안에도 A/B가 어느 쪽인지 남아야 한다. */}
            <h2 className="sticky top-0 z-10 -mx-4 -mt-4 mb-4 rounded-t-xl border-b border-hair bg-white px-4 py-3 text-sm font-semibold text-gray-600">
              {side.label}
            </h2>
            <div className="chat">
              <Bubble role="ai" text={side.ai1} wide />
            </div>
          </section>
        ))}
      </div>

      <div className="mt-10">
        <LikertList
          instruction=""
          min={scale.min}
          max={scale.max}
          items={items.map((item) => ({ id: String(item.position), text: item.text }))}
          values={values}
          onChange={(id, value) => setValues((prev) => ({ ...prev, [id]: value }))}
        />
      </div>

      {/* §4.10 — pair마다 이 화면에서 인터뷰한다. 버튼 문안이 "연구자 안내 후"를 지시하므로
          공용 SUBMIT을 쓰지 않는다(문안은 서버가 준다). */}
      <SubmitBar
        label={state.data.button ?? SUBMIT}
        busy={busy}
        disabled={Object.keys(values).length !== items.length}
        error={error}
        onClick={() =>
          run(() =>
            api.pairwise(
              position,
              Object.entries(values).map(([itemPosition, value]) => ({
                position: Number(itemPosition),
                value,
              })),
            ),
          )
        }
      />
    </div>
  )
}
