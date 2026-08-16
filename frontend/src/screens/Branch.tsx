/**
 * P4–P9 — branch 1회분 (구현명세서 §4.4–§4.9 · §3.2).
 *
 * 인과 창은 AI1 → User1 → sidecar → [AI2] → [downstream] → 평정이고 AI3는 없다(§0.4).
 * no_reply/end branch는 sidecar 다음이 곧 평정이다 — 이 파일에 그 분기를 판단하는 코드가
 * 없다는 점이 중요하다. **다음 화면은 서버 상태가 정한다**(§3.2 · NT-17).
 *
 * 화면 어디에도 branch 번호·조건명을 쓰지 않는다(§4.4 · §4.10).
 */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Bubble, ChatInput, TypingIndicator } from '../components/Chat'
import { AutoTextArea, Cards, SubmitBar } from '../components/Inputs'
import { LikertList, LikertRow } from '../components/Likert'
import Loading from '../components/Loading'
import { NEXT, START, SUBMIT } from '../copy'
import { CheckpointCard } from './Intro'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

/** §4.5 [파일럿 확정] — AI1 표시 전 타이핑 인디케이터 1–2초. */
const TYPING_MS = 1500

export function Reentry({ state, onState }: ScreenProps) {
  const { busy, error, run } = useSubmit(onState)
  return (
    <div className="screen">
      <p className="whitespace-pre-wrap">{state.data.notice}</p>
      <SubmitBar label={START} busy={busy} error={error} onClick={() => run(() => api.advance('P4'))} />
    </div>
  )
}

export function Chat({ state, onState }: ScreenProps) {
  const branch = state.branch_index ?? 0
  const [shown, setShown] = useState(state.b_state === 'B2')
  const [text, setText] = useState('')
  const { busy, error, run } = useSubmit(onState)
  const beaconed = useRef(false)

  useEffect(() => {
    if (shown) return
    const timer = window.setTimeout(() => setShown(true), TYPING_MS)
    return () => window.clearTimeout(timer)
  }, [shown])

  useEffect(() => {
    // §2.11 렌더 완료 beacon — `response_latency`의 시작점이다(D-05 · NT-29).
    if (shown && !beaconed.current) {
      beaconed.current = true
      api.event('render_complete', branch, { screen: 'P5' })
    }
  }, [shown, branch])

  const send = (disposition: string, body?: string) =>
    run(async () => {
      await api.event('submit', branch, { screen: 'P5', disposition })
      return api.user1(branch, disposition, body)
    })

  return (
    <div className="screen">
      <CheckpointCard checkpoint={state.data.checkpoint} />
      <div className="mt-3">{shown ? <Bubble role="ai" text={state.data.ai1} /> : <TypingIndicator />}</div>
      {shown && (
        <div className="mt-8 border-t border-hair pt-4">
          <ChatInput value={text} onChange={setText} disabled={busy} />
          {error && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => send('no_reply')}
              className="h-11 flex-1 rounded-lg border border-edge bg-white px-4"
            >
              {state.data.buttons?.no_reply}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => send('end')}
              className="h-11 flex-1 rounded-lg border border-edge bg-white px-4"
            >
              {state.data.buttons?.end}
            </button>
            <button
              type="button"
              disabled={busy || !text.trim()}
              onClick={() => send('reply', text)}
              className="h-11 flex-1 rounded-lg bg-accent-deep px-4 font-medium text-white disabled:bg-gray-200 disabled:text-gray-500"
            >
              {state.data.buttons?.send}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function Sidecar({ state, onState }: ScreenProps) {
  const branch = state.branch_index ?? 0
  const [choice, setChoice] = useState<string | null>(null)
  const [freeText, setFreeText] = useState('')
  const [relevance, setRelevance] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const { busy, error, run } = useSubmit(onState)

  const ready =
    choice !== null && (choice !== 'has' || (freeText.trim().length > 0 && relevance !== null))

  const submit = () =>
    run(() =>
      api.sidecar(
        branch,
        choice === 'has'
          ? {
              choice,
              free_text: freeText.trim(),
              relevance: relevance ?? undefined,
              reason: reason.trim() || undefined,
            }
          : { choice: choice as string },
      ),
    )

  return (
    <div className="screen">
      <div className="callout">{state.data.transition}</div>
      <p className="mt-6 whitespace-pre-wrap">{state.data.question}</p>
      <div className="mt-4">
        <Cards
          cards={(state.data.choices ?? []).map((option: any) => ({
            value: option.value,
            label: option.label,
          }))}
          value={choice}
          onChange={setChoice}
        />
      </div>

      {choice === 'has' && (
        <div className="mt-6 space-y-6">
          <div className="sec">
            <p className="mb-3 text-sm text-gray-600">{state.data.has_notice}</p>
            {/* ⚠ 현재 값만 상위로 올린다 — keystroke·삭제 이력은 수집하지 않는다(§4.6). */}
            <AutoTextArea value={freeText} onChange={setFreeText} />
          </div>
          <div className="sec">
            <p>{state.data.relevance_question}</p>
            <LikertRow
              min={state.data.relevance_min ?? 1}
              max={state.data.relevance_max ?? 7}
              value={relevance}
              onChange={setRelevance}
            />
          </div>
          <div className="sec">
            <p className="mb-3">{state.data.reason_prompt}</p>
            <AutoTextArea value={reason} onChange={setReason} rows={3} />
          </div>
        </div>
      )}

      <SubmitBar label={SUBMIT} busy={busy} disabled={!ready} error={error} onClick={submit} />
    </div>
  )
}

export function Ai2({ state, onState }: ScreenProps) {
  const branch = state.branch_index ?? 0
  const text: string | null = state.data.ai2 ?? null
  const { busy, error, run } = useSubmit(onState)
  const requested = useRef(false)

  useEffect(() => {
    // 이미 확정된 산출물이 있으면 다시 부르지 않는다 — 재생성 0건(§8.3-4 · NT-08).
    if (text || requested.current) return
    requested.current = true
    run(() => api.ai2(branch))
  }, [text, branch])

  useEffect(() => {
    if (text) api.event('render_complete', branch, { screen: 'P7' })
  }, [text, branch])

  if (!text) {
    return <Loading text={state.data.loading} delayNoticeText={state.data.delayed} />
  }

  return (
    <div className="screen">
      <Bubble role="ai" text={text} />
      {/* AI3는 없다 — 추가 입력창을 두지 않는다(§4.7). */}
      <SubmitBar label={NEXT} busy={busy} error={error} onClick={() => run(() => api.advance('P7'))} />
    </div>
  )
}

export function Downstream({ state, onState }: ScreenProps) {
  const branch = state.branch_index ?? 0
  const [code, setCode] = useState<string | null>(null)
  const { busy, error, run } = useSubmit(onState)

  return (
    <div className="screen">
      <p className="mb-6 whitespace-pre-wrap">{state.data.instruction}</p>
      <Cards
        cards={(state.data.options ?? []).map((option: any) => ({
          value: option.code,
          label: option.label,
        }))}
        value={code}
        onChange={setCode}
      />
      <SubmitBar
        label={SUBMIT}
        busy={busy}
        disabled={!code}
        error={error}
        onClick={() => run(() => api.downstream(branch, code as string))}
      />
    </div>
  )
}

interface RatingBlock {
  block: number
  instruction: string
  ai1_card: string | null
  items: { position: number; text: string }[]
}

export function Ratings({ state, onState }: ScreenProps) {
  const branch = state.branch_index ?? 0
  const blocks: RatingBlock[] = state.data.blocks ?? []
  const scale = state.data.scale ?? { min: 1, max: 7 }
  const [values, setValues] = useState<Record<string, number>>({})
  const { busy, error, run } = useSubmit(onState)

  const total = blocks.reduce((sum, block) => sum + block.items.length, 0)
  const answered = Object.keys(values).length

  return (
    <div className="screen">
      <ScreenTitle>방금 대화에 대한 평정</ScreenTitle>
      <p className="mb-6 text-sm text-gray-600">
        {scale.min}({scale.min_label}) – {scale.max}({scale.max_label})
      </p>
      <div className="space-y-10">
        {blocks.map((block) => (
          <section key={block.block}>
            {/* §4.9 블록 1 — 해당 branch의 AI1 원문을 회색 카드로 재표시(앵커). */}
            {block.ai1_card && (
              <div className="sec mb-4 whitespace-pre-wrap bg-gray-50">{block.ai1_card}</div>
            )}
            <LikertList
              instruction={block.instruction}
              min={scale.min}
              max={scale.max}
              items={block.items.map((item) => ({ id: String(item.position), text: item.text }))}
              values={values}
              onChange={(id, value) => setValues((prev) => ({ ...prev, [id]: value }))}
            />
          </section>
        ))}
      </div>
      <SubmitBar
        label={SUBMIT}
        busy={busy}
        disabled={answered !== total}
        error={error}
        onClick={() =>
          run(() =>
            api.ratings(
              branch,
              Object.entries(values).map(([position, value]) => ({
                position: Number(position),
                value,
              })),
            ),
          )
        }
      />
    </div>
  )
}
