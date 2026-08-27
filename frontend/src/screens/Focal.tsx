/**
 * P3–P8 — 재진입 · focal 상호작용 1회 · focal 측정 (구현명세서 §4.3–§4.8 · §3.2).
 *
 * 인과 창은 **checkpoint → AI1 → User1 → sidecar → AI2 → User2/종료**이고 AI3는 없다
 * (§0.4 · D-33). branch 루프가 사라졌으므로 이 파일은 **한 번만** 돈다.
 *
 * v1.0.1 `Branch.tsx`에서 없어진 것들이 그대로 v2의 결정이다.
 * - "답장 보내지 않기"·"대화 종료" 버튼 → **User1 필수**(D-32). 보내기 하나뿐이다.
 * - sidecar 3선택(없음/있음/건너뛰기) + 관련성 7점 → **3단 조건부**(D-28)
 * - downstream 7메뉴 → User2 이어쓰기 / 종료 6유형 + 이유(D-26)
 * - 평정 12문항 2블록 → focal 5 construct(7문항) + MC 2, MC가 마지막(D-37)
 *
 * 화면 어디에도 조건명·R/U/Q·"focal/대안"이라는 구분 원리를 쓰지 않는다(§4 서두).
 */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Bubble, ChatInput, StimulusText, TypingIndicator } from '../components/Chat'
import { AutoTextArea, Cards, SubmitBar } from '../components/Inputs'
import { LikertList } from '../components/Likert'
import Loading from '../components/Loading'
import { NEXT, START, SUBMIT } from '../copy'
import { DevScreenNote } from '../components/DevNote'
import { CheckpointCard } from './Intro'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

// --------------------------------------------------------------------------- //
// P3 — interactional re-entry 타이머 (§4.3)
// --------------------------------------------------------------------------- //

export function Reentry({ state, onState }: ScreenProps) {
  const { busy, error, run } = useSubmit(onState)
  const minSeconds: number = state.data.min_seconds ?? 30
  const hintSeconds: number = state.data.hint_seconds ?? 60
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    // §4.3 [파일럿 확정] — 30초 동안 버튼 비활성, 60초에 보조문.
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="screen">
      <DevScreenNote
        screen="P3"
        term="Incident-Grounded Interactional Re-entry"
        detail="§7.3 — verification 이후 30–60초 회상. DEV_MODE에서는 대기 없이 바로 진행된다(실세션은 30초 비활성·60초 보조문). 특정 감정·선호·전략은 묻지 않는다."
      />
      <ScreenTitle>잠시 떠올려 주세요</ScreenTitle>
      {/* 감정·선호·correction 전략을 묻는 문구를 두지 않는다(§4.3 · 초안 §7.3). */}
      <p className="whitespace-pre-wrap">{state.data.notice}</p>
      {elapsed >= hintSeconds && (
        <p className="mt-4 text-sm text-gray-600">{state.data.ready_notice}</p>
      )}
      <SubmitBar
        label={START}
        busy={busy}
        disabled={elapsed < minSeconds}
        error={error}
        onClick={() => run(() => api.advance('P3'))}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P4 — 채팅: focal AI1 + User1 (§4.4 · F0–F1)
// --------------------------------------------------------------------------- //

export function Chat({ state, onState }: ScreenProps) {
  const typingMs: number = state.data.typing_ms ?? 1500
  const [shown, setShown] = useState(state.f_state === 'F1')
  const [text, setText] = useState('')
  const { busy, error, run } = useSubmit(onState)
  const beaconed = useRef(false)

  useEffect(() => {
    if (shown) return
    const timer = window.setTimeout(() => setShown(true), typingMs)
    return () => window.clearTimeout(timer)
  }, [shown, typingMs])

  useEffect(() => {
    // §2.11 렌더 완료 beacon — 이 beacon이 F0 → F1을 연다(유실돼도 제출이 같은 전이를 한다).
    if (shown && !beaconed.current) {
      beaconed.current = true
      api.event('render_complete', { screen: 'P4' })
    }
  }, [shown])

  const send = () =>
    run(async () => {
      await api.event('submit', { screen: 'P4' })
      return api.user1(text)
    })

  return (
    <div className="screen">
      <DevScreenNote
        screen="P4"
        term="Focal Enactment — AI1 + User1"
        detail="§4.4·초안 §7.7 — locked focal AI1(R/U/Q 조립문) 표시 후 실제 보낼 답장을 작성한다. 조건은 참가자당 하나다(between). User1은 필수(D-32)."
      />
      <CheckpointCard checkpoint={state.data.checkpoint} />
      <div className="chat mt-4">
        {/* focal AI1 — 이 화면의 새 응답. 대안 AI1·AI2와 **같은** `isNew`를 쓴다(D-39). */}
        {shown ? (
          <Bubble role="ai" text={state.data.ai1} note={state.data.ai1_note} isNew />
        ) : (
          <TypingIndicator />
        )}
      </div>
      {shown && (
        <div className="mt-8 border-t border-hair pt-5">
          {/* [정본, 초안 §7.7] — 입력창 위 고정 표시. 윤문 금지. */}
          <p className="callout mb-4 whitespace-pre-wrap">{state.data.instruction}</p>
          {/* **보내기 하나뿐이다** — no_reply·end 버튼은 v2에 없다(D-32). */}
          <ChatInput
            value={text}
            onChange={setText}
            disabled={busy}
            send={{
              label: state.data.send_button,
              disabled: busy || !text.trim(),
              onClick: send,
            }}
          />
          {error && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P5 — private sidecar 3단 (§4.5 · F2 · D-28)
// --------------------------------------------------------------------------- //

export function Sidecar({ state, onState }: ScreenProps) {
  const [hasMore, setHasMore] = useState<string | null>(null)
  const [freeText, setFreeText] = useState('')
  const [provenance, setProvenance] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const { busy, error, run } = useSubmit(onState)

  const yes = hasMore === 'true'
  // 3단은 `preexisting`에서만 뜬다 — 그 규칙을 서버가 payload로 알려준다(§4.5).
  const showReason = yes && provenance === state.data.q3_when_provenance
  const ready =
    hasMore !== null && (!yes || (freeText.trim().length > 0 && provenance !== null))

  const submit = () =>
    run(() =>
      api.sidecar(
        yes
          ? {
              has_more: true,
              free_text: freeText.trim(),
              provenance: provenance ?? undefined,
              // 3단은 선택이다 — 빈칸이면 아예 보내지 않는다(§4.5).
              reason: showReason && reason.trim() ? reason.trim() : undefined,
            }
          : { has_more: false },
      ),
    )

  return (
    <div className="screen">
      <DevScreenNote
        screen="P5"
        term="Private Sidecar"
        detail="§4.5·초안 §7.8 — AI에 전달되지 않는 3단 질문. withholding과 prompt-evoked reflection을 구분한다. 어떤 값도 AI2 payload에 들어가지 않는다(NT-01)."
      />
      <div className="callout">{state.data.transition}</div>

      {/* 1단 [정본, 초안 §7.8] */}
      <p className="mt-6 whitespace-pre-wrap">{state.data.q1}</p>
      <div className="mt-4">
        <Cards
          cards={(state.data.q1_choices ?? []).map((option: any) => ({
            value: String(option.value),
            label: option.label,
          }))}
          value={hasMore}
          onChange={setHasMore}
        />
      </div>

      {yes && (
        <div className="mt-8 space-y-6">
          <div className="sec">
            <p className="mb-3 text-sm text-gray-600">{state.data.has_notice}</p>
            {/* ⚠ 현재 값만 상위로 올린다 — keystroke·삭제 이력은 수집하지 않는다(§4.5). */}
            <AutoTextArea value={freeText} onChange={setFreeText} />
          </div>

          {/* 2단 [정본] — 자유기술 입력 후 */}
          {freeText.trim().length > 0 && (
            <div className="sec">
              <p className="mb-3 whitespace-pre-wrap">{state.data.q2}</p>
              <Cards
                cards={(state.data.q2_choices ?? []).map((option: any) => ({
                  value: option.value,
                  label: option.label,
                }))}
                value={provenance}
                onChange={setProvenance}
              />
            </div>
          )}

          {/* 3단 [정본] — `preexisting`인 경우에만. 자유기술 **선택**. */}
          {showReason && (
            <div className="sec">
              <p className="mb-1 whitespace-pre-wrap">{state.data.q3}</p>
              <p className="mb-3 text-sm text-gray-600">{state.data.q3_optional_notice}</p>
              <AutoTextArea value={reason} onChange={setReason} rows={3} />
            </div>
          )}
        </div>
      )}

      <SubmitBar label={SUBMIT} busy={busy} disabled={!ready} error={error} onClick={submit} />
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P6 — AI2 로딩·표시 (§4.6 · F3)
// --------------------------------------------------------------------------- //

/**
 * focal 채팅 맥락 — effective checkpoint → AI1 → User1 → AI2 (→ User2).
 *
 * P6와 P7이 **같은 것을** 그린다(§4.6·§4.7). P7에서 AI2 말풍선만 남기면 참가자가 "실제
 * 상황이라면 어떻게 하겠는가"를 판단할 근거가 화면에서 사라진다 — 직전 화면과 이어져 보여야
 * 한다. 조건명·branch 번호 같은 배지는 여기에도 붙이지 않는다(§4.10).
 */
function FocalTranscript({
  data,
  ai2,
}: {
  data: Record<string, any>
  ai2: string | null
}) {
  return (
    <>
      <CheckpointCard checkpoint={data.checkpoint} />
      <div className="chat mt-4">
        {data.ai1 && <Bubble role="ai" text={data.ai1} note={data.ai1_note} />}
        {data.user1 && <Bubble role="user" text={data.user1} />}
        {/* 이 화면의 **새 응답**은 AI2다. AI1은 이미 P4에서 본 것이라 표시하지 않는다 —
            화면마다 하이라이트는 지금 판단 대상인 AI 응답 하나뿐이다(D-39). */}
        {ai2 && <Bubble role="ai" text={ai2} isNew />}
        {data.user2 && <Bubble role="user" text={data.user2} />}
      </div>
    </>
  )
}

export function Ai2({ state, onState }: ScreenProps) {
  const text: string | null = state.data.ai2 ?? null
  const { busy, error, run } = useSubmit(onState)
  const requested = useRef(false)

  useEffect(() => {
    // 이미 확정된 산출물이 있으면 다시 부르지 않는다 — 재생성 0건(§8.3 · NT-08).
    if (text || requested.current) return
    requested.current = true
    run(() => api.ai2())
  }, [text])

  useEffect(() => {
    if (text) api.event('render_complete', { screen: 'P6' })
  }, [text])

  if (!text) {
    return <Loading text={state.data.loading} delayNoticeText={state.data.delayed} />
  }

  return (
    <div className="screen">
      <DevScreenNote
        screen="P6"
        term="Common-Policy AI2"
        detail="§4.6·초안 §7.9 — 실시간 생성. 입력은 effective checkpoint + focal AI1 + User1 3종뿐(§1.2). 정상·재생성·fallback은 참가자에게 구분되지 않는다."
      />
      {/* 채팅 맥락(effective checkpoint → AI1 → User1) 위에 AI2를 얹는다(§4.6). */}
      <FocalTranscript data={state.data} ai2={text} />
      {/* AI3는 없다 — 추가 입력창을 두지 않는다(§4.6 · D-33). */}
      <SubmitBar
        label={NEXT}
        busy={busy}
        error={error}
        onClick={() => run(() => api.advance('P6'))}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P7 — User2 / 종료 (§4.7 · F4 · D-26)
// --------------------------------------------------------------------------- //

export function Downstream({ state, onState }: ScreenProps) {
  const [branch, setBranch] = useState<'reply' | 'end' | null>(null)
  const [text, setText] = useState('')
  const [endType, setEndType] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const { busy, error, run } = useSubmit(onState)

  // F5 — 제출이 끝났다. 종료 안내를 읽고 진행한다(AI 응답 없음 — D-33).
  if (state.data.submitted) {
    return (
      <div className="screen">
        <DevScreenNote
          screen="P7"
          term="Downstream Action — 제출 후(F5)"
          detail="§4.7 — 종료 안내를 읽고 진행한다. AI3는 없다(D-33)."
        />
        <FocalTranscript data={state.data} ai2={state.data.ai2 ?? null} />
        {state.data.closed_notice && (
          <div className="callout mt-6 whitespace-pre-wrap">{state.data.closed_notice}</div>
        )}
        <SubmitBar
          label={NEXT}
          busy={busy}
          error={error}
          onClick={() => run(() => api.advance('P7'))}
        />
      </div>
    )
  }

  const reasonRequired: boolean = state.data.reason_required ?? true
  const ready =
    branch === 'reply'
      ? text.trim().length > 0
      : branch === 'end' && endType !== null && (!reasonRequired || reason.trim().length > 0)

  const submit = () =>
    run(() =>
      branch === 'reply'
        ? api.downstream({ disposition: 'reply', text: text.trim() })
        : api.downstream({
            disposition: 'end',
            end_type: endType ?? undefined,
            reason: reason.trim() || undefined,
          }),
    )

  return (
    <div className="screen">
      <DevScreenNote
        screen="P7"
        term="Downstream Action"
        detail="§4.7·D-26 — 답장 이어쓰기 또는 종료(이탈 유형 6코드 + 이유). User2에 대한 AI 응답은 없다(D-33)."
      />
      {/* 직전 화면(P6)과 같은 채팅 맥락을 그대로 두고, 그 아래에서 묻는다(§4.7). */}
      <FocalTranscript data={state.data} ai2={state.data.ai2 ?? null} />
      <p className="callout mb-6 mt-8 whitespace-pre-wrap">{state.data.instruction}</p>

      {/* 두 갈래는 좌우 고정이다(§4.7). */}
      <div className="flex gap-3">
        {(
          [
            ['reply', state.data.reply_label],
            ['end', state.data.end_label],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={branch === value}
            onClick={() => setBranch(value)}
            className={`h-12 flex-1 rounded-xl border px-4 transition-colors ${
              branch === value
                ? 'is-selected font-medium ring-1 ring-accent'
                : 'border-hair bg-white hover:border-edge hover:bg-gray-50'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {branch === 'reply' && (
        <div className="mt-6">
          <ChatInput value={text} onChange={setText} disabled={busy} />
        </div>
      )}

      {branch === 'end' && (
        <div className="mt-6 space-y-6">
          {/* 이탈 유형 6개는 표 순서 고정 — 무작위가 아니다(§4.7). */}
          <Cards
            cards={(state.data.end_types ?? []).map((option: any) => ({
              value: option.code,
              label: option.label,
            }))}
            value={endType}
            onChange={setEndType}
          />
          {endType && (
            <div className="sec">
              <p className="mb-3">{state.data.reason_prompt}</p>
              <AutoTextArea value={reason} onChange={setReason} rows={3} />
            </div>
          )}
        </div>
      )}

      <SubmitBar
        label={branch === 'reply' ? (state.data.send_button ?? SUBMIT) : SUBMIT}
        busy={busy}
        disabled={!ready}
        error={error}
        onClick={submit}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P8 — focal measures + manipulation check (§4.8)
// --------------------------------------------------------------------------- //

interface RatingBlock {
  scope: string
  instruction: string
  ai1_card: string | null
  items: { position: number; text: string }[]
}

export function Ratings({ state, onState }: ScreenProps) {
  const blocks: RatingBlock[] = state.data.blocks ?? []
  const scale = state.data.scale ?? { min: 1, max: 7 }
  const [values, setValues] = useState<Record<string, number>>({})
  const { busy, error, run } = useSubmit(onState)

  const total = blocks.reduce((sum, block) => sum + block.items.length, 0)
  const answered = Object.keys(values).length

  return (
    <div className="screen">
      <DevScreenNote
        screen="P8"
        term="Focal Measures + Manipulation Check"
        detail="§4.8·초안 §7.11 — 블록1 focal experiential 5 construct → 블록2 MC 2문항. MC가 battery 마지막이고 referent는 첫 번째 AI 응답이다(D-37). 합산 금지."
      />
      <ScreenTitle>방금 경험한 대화에 대한 평정</ScreenTitle>
      <div className="space-y-12">
        {/* 블록 순서는 서버가 정한다 — MC가 **마지막**이다(§0.4 D-37). */}
        {blocks.map((block) => (
          <section key={block.scope}>
            {/* §4.8 — MC 블록 상단에 focal AI1 원문을 카드로 재표시(앵커).
                자극의 재표시이므로 채팅과 같은 무채색이다 — 색조를 넣지 않는다. */}
            {block.ai1_card && (
              <div className="bubble bubble-ai mb-5 max-w-none">
                <StimulusText text={block.ai1_card} note={state.data.ai1_note} />
              </div>
            )}
            <LikertList
              instruction={block.instruction}
              min={scale.min}
              max={scale.max}
              minLabel={scale.min_label}
              maxLabel={scale.max_label}
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
