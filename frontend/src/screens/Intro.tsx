/**
 * P1 동의 · P2 checkpoint 확인·수정 (구현명세서 §4.1 · §4.2 · D-25).
 *
 * 두 화면 모두 문안·항목이 **서버 payload**로 온다.
 *
 * **P2가 v2에서 완전히 달라졌다**(D-25). v1.0.1의 P3는 표시 전용이었지만(D-08 폐기), 이제
 * 참가자가 segment를 **직접 고친다**. 고친 값은 누적 저장되고 이후 화면·AI2 입력이 전부
 * 그 수정본(effective checkpoint)을 쓴다(§3.4).
 *
 * 수정 UI에서 지키는 것 둘:
 * ① 편집창은 **원문이 채워진 채로** 열린다 — 처음부터 다시 쓰게 하면 사실 정정이 아니라
 *    재서술이 된다(§4.2는 "사실관계가 명백히 다른 부분"만 요구한다).
 * ② "그때 실제로 무엇을 원했나요?" 류의 선호 재활성화 질문을 **화면 어디에도** 두지
 *    않는다(§4.2 금지). [정본] 안내문 자체가 "속마음을 다시 설명하지 않으셔도 됩니다"다.
 */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { Bubble } from '../components/Chat'
import { AutoTextArea, Checks, SubmitBar } from '../components/Inputs'
import { NEXT } from '../copy'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

export function Consent({ state, onState }: ScreenProps) {
  const items: { field: string; label: string }[] = state.data.items ?? []
  const [values, setValues] = useState<Record<string, boolean>>({})
  const { busy, error, run } = useSubmit(onState)
  const allChecked = items.length > 0 && items.every((item) => values[item.field])

  return (
    <div className="screen">
      <ScreenTitle>연구 소개와 동의</ScreenTitle>
      <div className="callout">{state.data.notice}</div>
      <div className="sec mt-6">
        <Checks
          items={items}
          values={values}
          onChange={(field, value) => setValues((prev) => ({ ...prev, [field]: value }))}
        />
      </div>
      <SubmitBar
        label={NEXT}
        busy={busy}
        disabled={!allChecked}
        error={error}
        onClick={() => run(() => api.consent(Object.fromEntries(items.map((i) => [i.field, true]))))}
      />
    </div>
  )
}

interface CheckpointTurn {
  role: 'user' | 'ai'
  text: string
}

/**
 * checkpoint를 채팅 기록 형태로 표시 (§4.2 · §4.4 · §4.9 · §4.10 공용).
 *
 * P2 이후의 화면에서는 **수정본**이 온다 — 이 컴포넌트는 그 사실을 모르고 받은 대로 그린다.
 */
export function CheckpointCard({ checkpoint }: { checkpoint: any }) {
  const turns: CheckpointTurn[] = checkpoint?.turns ?? []
  const evidence: string[] = checkpoint?.prior_evidence ?? []
  return (
    <div>
      <div className="sec bg-gray-50">
        <p className="whitespace-pre-wrap">{checkpoint?.situation_summary}</p>
        {evidence.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-gray-600">
            {evidence.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="mt-4 space-y-3">
        {turns.map((turn, index) => (
          <Bubble key={index} role={turn.role} text={turn.text} />
        ))}
      </div>
    </div>
  )
}

interface Segment {
  segment: string
  label: string
  text: string
  edited: boolean
}

/** §4.2 — segment 1건의 수정 UI. 열려 있는 동안만 편집창이고, 저장하면 다시 닫힌다. */
function SegmentEditor({
  segment,
  buttons,
  hint,
  busy,
  onSave,
}: {
  segment: Segment
  buttons: { edit: string; save: string; cancel: string }
  hint: string
  busy: boolean
  onSave: (text: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  // 편집창은 **원문이 채워진 채로** 열린다(§4.2 — 사실 정정용이지 재서술이 아니다).
  const [draft, setDraft] = useState(segment.text)

  useEffect(() => {
    if (!open) setDraft(segment.text)
  }, [segment.text, open])

  if (!open) {
    return (
      <div className="sec flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-600">
            {segment.label}
            {segment.edited && <span className="ml-2 text-xs text-accent-deep">수정됨</span>}
          </p>
          <p className="mt-1 whitespace-pre-wrap">{segment.text}</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="h-9 shrink-0 rounded-lg border border-edge bg-white px-3 text-sm"
        >
          {buttons.edit}
        </button>
      </div>
    )
  }

  return (
    <div className="sec">
      <p className="text-sm font-medium text-gray-600">{segment.label}</p>
      <p className="mb-2 mt-1 text-sm text-gray-600">{hint}</p>
      <AutoTextArea value={draft} onChange={setDraft} rows={3} disabled={busy} />
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setDraft(segment.text)
            setOpen(false)
          }}
          className="h-10 rounded-lg border border-edge bg-white px-4"
        >
          {buttons.cancel}
        </button>
        <button
          type="button"
          disabled={busy || !draft.trim() || draft.trim() === segment.text.trim()}
          onClick={async () => {
            await onSave(draft.trim())
            setOpen(false)
          }}
          className="h-10 rounded-lg bg-accent-deep px-4 font-medium text-white disabled:bg-gray-200 disabled:text-gray-500"
        >
          {buttons.save}
        </button>
      </div>
    </div>
  )
}

export function Checkpoint({ state, onState }: ScreenProps) {
  const segments: Segment[] = state.data.segments ?? []
  const { busy, error, run } = useSubmit(onState)

  useEffect(() => {
    api.event('screen_enter', { screen: 'P2' })
  }, [])

  return (
    <div className="screen">
      <ScreenTitle>상황 확인</ScreenTitle>
      {/* [정본, 초안 §7.3] — 윤문 금지. 서버가 내려준 문자열을 그대로 그린다. */}
      <p className="mb-6 whitespace-pre-wrap">{state.data.intro}</p>

      <CheckpointCard checkpoint={state.data.checkpoint} />

      <div className="mt-8 space-y-3">
        {segments.map((segment) => (
          <SegmentEditor
            key={segment.segment}
            segment={segment}
            hint={state.data.edit_hint}
            buttons={{
              edit: state.data.edit_button,
              save: state.data.save_button,
              cancel: state.data.cancel_button,
            }}
            busy={busy}
            onSave={(text) => run(() => api.checkpointEdit(segment.segment, text))}
          />
        ))}
      </div>

      <SubmitBar
        label={state.data.confirm_button ?? NEXT}
        busy={busy}
        error={error}
        onClick={() => run(() => api.checkpointConfirm())}
      />
    </div>
  )
}
