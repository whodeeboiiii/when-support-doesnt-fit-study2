/**
 * P1 동의 · P2 사전 설문 · P3 checkpoint 확인 (구현명세서 §4.1–§4.3).
 *
 * 세 화면 모두 문안·문항이 **서버 payload**로 온다. 특히 P2는 문항 ID·역채점 메타가 내려오지
 * 않고 **위치(position)**만 온다(§4.2 · NT-05) — 그래서 이 파일에는 문항 ID를 다루는 코드가
 * 아예 없다.
 *
 * P3에는 수정 기능이 없다(D-08). 그리고 "그때 실제로 무엇을 원했나요?" 류의 선호 재활성화
 * 질문을 **화면 어디에도 두지 않는다**(§4.3 금지).
 */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { Bubble } from '../components/Chat'
import { Cards, Checks, ProgressBar, SubmitBar } from '../components/Inputs'
import { LikertRow } from '../components/Likert'
import { NEXT, SUBMIT } from '../copy'
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

interface PresurveyItem {
  position: number
  type: string
  text: string
  options?: { value: string; label: string }[]
  scale_min?: number
  scale_max?: number
}

export function Presurvey({ state, onState }: ScreenProps) {
  const items: PresurveyItem[] = state.data.items ?? []
  const [values, setValues] = useState<Record<number, unknown>>({})
  const { busy, error, run } = useSubmit(onState)
  const answered = items.filter((item) => values[item.position] !== undefined).length

  const setValue = (position: number, value: unknown) =>
    setValues((prev) => ({ ...prev, [position]: value }))

  const toggleMulti = (position: number, value: string) => {
    const current = (values[position] as string[]) ?? []
    setValue(
      position,
      current.includes(value) ? current.filter((v) => v !== value) : [...current, value],
    )
  }

  return (
    <div className="screen">
      <ScreenTitle>사전 설문</ScreenTitle>
      <ProgressBar done={answered} total={items.length} />
      <div className="space-y-6">
        {items.map((item) => (
          <div key={item.position} className="sec">
            <p>{item.text}</p>
            <div className="mt-3">
              {item.type === 'single_choice' && (
                <Cards
                  cards={(item.options ?? []).map((option) => ({
                    value: option.value,
                    label: option.label,
                  }))}
                  value={(values[item.position] as string) ?? null}
                  onChange={(value) => setValue(item.position, value)}
                />
              )}
              {item.type === 'multi_choice' && (
                <Checks
                  items={(item.options ?? []).map((option) => ({
                    field: option.value,
                    label: option.label,
                  }))}
                  values={Object.fromEntries(
                    ((values[item.position] as string[]) ?? []).map((value) => [value, true]),
                  )}
                  onChange={(field) => toggleMulti(item.position, field)}
                />
              )}
              {item.type.startsWith('likert') && (
                <LikertRow
                  min={item.scale_min ?? 1}
                  max={item.scale_max ?? 7}
                  value={(values[item.position] as number) ?? null}
                  onChange={(value) => setValue(item.position, value)}
                />
              )}
            </div>
          </div>
        ))}
      </div>
      <SubmitBar
        label={SUBMIT}
        busy={busy}
        disabled={answered !== items.length}
        error={error}
        onClick={() =>
          run(() =>
            api.presurvey(
              items.map((item) => ({ position: item.position, value: values[item.position] })),
            ),
          )
        }
      />
    </div>
  )
}

interface CheckpointTurn {
  role: 'user' | 'ai'
  text: string
}

/** §4.3 — checkpoint를 채팅 기록 형태로 재표시. 표시 전용이다. */
export function CheckpointCard({ checkpoint }: { checkpoint: any }) {
  const turns: CheckpointTurn[] = checkpoint?.turns ?? []
  return (
    <div>
      <div className="sec bg-gray-50">{checkpoint?.situation_summary}</div>
      <div className="mt-4 space-y-3">
        {turns.map((turn, index) => (
          <Bubble key={index} role={turn.role} text={turn.text} />
        ))}
      </div>
    </div>
  )
}

export function Checkpoint({ state, onState }: ScreenProps) {
  const { busy, error, run } = useSubmit(onState)

  useEffect(() => {
    // §4.3 저장: checkpoint 체류시간 beacon (파생 지표는 분석 시점 계산 — §7.5).
    api.event('screen_enter', null, { screen: 'P3' })
  }, [])

  return (
    <div className="screen">
      <ScreenTitle>상황 확인</ScreenTitle>
      <p className="mb-6 whitespace-pre-wrap">{state.data.intro}</p>
      <CheckpointCard checkpoint={state.data.checkpoint} />
      <SubmitBar
        label={NEXT}
        busy={busy}
        error={error}
        onClick={() => run(() => api.checkpointConfirm())}
      />
    </div>
  )
}
