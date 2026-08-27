/**
 * P1 동의 · P1S 사전 설문 · P2 checkpoint 확인·수정 (§4.1 · v1.0.1 §4.2 · §4.2 · D-25 · D-39 · D-44).
 *
 * 세 화면 모두 문안·항목이 **서버 payload**로 온다. P1S는 문항 ID·역채점 메타가 내려오지
 * 않고 **위치(position)**만 온다(v1.0.1 §4.2 · NT-05) — 그래서 이 파일에는 사전설문 문항
 * ID를 다루는 코드가 아예 없다.
 *
 * **P2가 v2에서 완전히 달라졌다**(D-25). v1.0.1의 P3는 표시 전용이었지만(D-08 폐기), 이제
 * 참가자가 segment를 **직접 고친다**. 고친 값은 누적 저장되고 이후 화면·AI2 입력이 전부
 * 그 수정본(effective checkpoint)을 쓴다(§3.4).
 *
 * 수정 UI에서 지키는 것 셋:
 * ① 편집창은 **원문이 채워진 채로** 열린다 — 처음부터 다시 쓰게 하면 사실 정정이 아니라
 *    재서술이 된다(§4.2는 "사실관계가 명백히 다른 부분"만 요구한다).
 * ② "그때 실제로 무엇을 원했나요?" 류의 선호 재활성화 질문을 **화면 어디에도** 두지
 *    않는다(§4.2 금지). [정본] 안내문 자체가 "속마음을 다시 설명하지 않으셔도 됩니다"다.
 * ③ **"수정됨" 배지는 P2에서만 뜬다.** 이후 화면(P4·P6·P7·P10)의 checkpoint 카드는 배지 없이
 *    그린다 — 자기가 고쳤다는 사실을 계속 상기시키면 그 자체가 자극의 일부가 된다(D-39).
 *    구조적으로 막아 둔다: 배지는 `edit` prop이 있을 때만 그려지고, 그 prop은 P2만 넘긴다.
 */

import { ReactNode, useEffect, useState } from 'react'
import { api } from '../api'
import { Bubble } from '../components/Chat'
import { DevAside, DevNote, DevScreenNote } from '../components/DevNote'
import { AutoTextArea, Cards, Checks, SubmitBar } from '../components/Inputs'
import { LikertRow } from '../components/Likert'
import { NEXT } from '../copy'
import { ScreenProps, ScreenTitle, useSubmit } from './common'

export function Consent({ state, onState }: ScreenProps) {
  const items: { field: string; label: string }[] = state.data.items ?? []
  const [values, setValues] = useState<Record<string, boolean>>({})
  const { busy, error, run } = useSubmit(onState)
  const allChecked = items.length > 0 && items.every((item) => values[item.field])

  useEffect(() => {
    api.event('screen_enter', { screen: 'P1' })
  }, [])

  return (
    <div className="screen">
      <DevScreenNote
        screen="P1"
        term="동의"
        detail="§4.1 — 항목별 복수 체크 6종(대안 노출 고지 포함). 문안은 IRB 초안 착지본이고 승인 대기다(PH-IRB-1)."
      />
      <ScreenTitle>연구 소개와 동의</ScreenTitle>
      <div className="callout whitespace-pre-wrap">{state.data.notice}</div>
      <div className="sec mt-6">
        <Checks
          items={items}
          values={values}
          onChange={(field, value) => setValues((prev) => ({ ...prev, [field]: value }))}
        />
      </div>
      {/* §4.1 하단 고정 — PII 입력 금지. 체크 대상이 아니라 안내다. */}
      {state.data.footnote && (
        <p className="mt-3 text-sm text-gray-500">{state.data.footnote}</p>
      )}
      <SubmitBar
        label={state.data.button ?? NEXT}
        busy={busy}
        disabled={!allChecked}
        error={error}
        onClick={() => run(() => api.consent(values))}
      />
    </div>
  )
}

// --------------------------------------------------------------------------- //
// P1S — 사전 설문 (v1.0.1 §4.2 · §7.1 · D-44)
// --------------------------------------------------------------------------- //

interface PresurveyItem {
  position: number
  type: string
  text: string
  options?: { value: string; label: string }[]
  scale_min?: number
  scale_max?: number
  scale_min_label?: string
  scale_max_label?: string
}

/**
 * 동의 직후·checkpoint 직전의 사전 설문.
 *
 * 여기 **없는 것**이 계약이다. ① 문항 ID·역채점·section — 서버가 내려주지 않는다(NT-05).
 * ② 진행 표시(스텝 인디케이터) — 화면 공통 규율이다(`Inputs.tsx` 상단). ③ Study 1 사건을
 * 떠올리게 하는 문장 — 이 화면은 checkpoint **앞**이라 사건을 건드리면 §4.2·§4.3의 선호
 * 재활성화 금지와 같은 문제가 된다. 문안은 서버가 준다.
 *
 * 응답은 **위치 → 값**으로만 올라간다. 값의 모양은 문항 유형이 정한다: 단일 선택은 문자열,
 * 복수 선택은 문자열 배열, 척도는 1–7 정수다.
 */
export function Presurvey({ state, onState }: ScreenProps) {
  const items: PresurveyItem[] = state.data.items ?? []
  const [values, setValues] = useState<Record<number, unknown>>({})
  const { busy, error, run } = useSubmit(onState)
  const answered = items.filter((item) => values[item.position] !== undefined).length

  useEffect(() => {
    api.event('screen_enter', { screen: 'P1S' })
  }, [])

  const setValue = (position: number, value: unknown) =>
    setValues((prev) => ({ ...prev, [position]: value }))

  // 복수 선택은 마지막 하나를 지우면 **미응답**으로 되돌린다 — 빈 배열을 응답으로 저장하면
  // 서버가 400을 주고(선택지 1개 이상), 화면은 왜 막혔는지 설명하지 못한다.
  const toggleMulti = (position: number, value: string) => {
    const current = (values[position] as string[]) ?? []
    const next = current.includes(value)
      ? current.filter((entry) => entry !== value)
      : [...current, value]
    setValues((prev) => ({ ...prev, [position]: next.length ? next : undefined }))
  }

  return (
    <div className="screen">
      <DevScreenNote
        screen="P1S"
        term="Participant Characterization"
        detail="§4.1S·§7.0 · 구 초안 §7.4 — 사용 빈도 5 · 빗나갔을 때 대응 1 · disclosure 2 · DDI 발췌 4. 표본 기술 전용이고 RQ3의 confirmatory moderator가 아니다. D-44로 복원, 문항 자산은 PI 확인·착지(PH-01 해소)."
      />
      <ScreenTitle>사전 설문</ScreenTitle>
      <p className="callout mb-6 whitespace-pre-wrap">{state.data.intro}</p>

      <div className="space-y-5">
        {items.map((item) => (
          <div key={item.position} className="sec">
            <p className="text-base">{item.text}</p>
            {item.type === 'single_choice' && (
              <div className="mt-3">
                <Cards
                  cards={item.options ?? []}
                  value={(values[item.position] as string) ?? null}
                  onChange={(value) => setValue(item.position, value)}
                />
              </div>
            )}
            {item.type === 'multi_choice' && (
              <div className="mt-3">
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
              </div>
            )}
            {item.type.startsWith('likert') && (
              <LikertRow
                min={item.scale_min ?? 1}
                max={item.scale_max ?? 7}
                minLabel={item.scale_min_label}
                maxLabel={item.scale_max_label}
                value={(values[item.position] as number) ?? null}
                onChange={(value) => setValue(item.position, value)}
              />
            )}
          </div>
        ))}
      </div>

      <SubmitBar
        label={state.data.submit_button ?? NEXT}
        busy={busy}
        disabled={items.length === 0 || answered !== items.length}
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

// --------------------------------------------------------------------------- //
// P2 — checkpoint 확인·수정 (§4.2 · D-25)
// --------------------------------------------------------------------------- //

interface CheckpointTurn {
  role: 'user' | 'ai'
  text: string
}

export interface Segment {
  segment: string
  label: string
  text: string
  edited: boolean
}

/** 수정 모드에 필요한 것 전부. **P2만** 이 객체를 넘긴다(다른 화면은 읽기 전용). */
interface EditContext {
  segments: Record<string, Segment>
  buttons: { edit: string; save: string; cancel: string }
  hint: string
  busy: boolean
  onSave: (segment: string, text: string) => Promise<void>
}

/**
 * `turns`는 §4.2가 정한 순서다 — [참가자 원요청] → [AI 문제 응답] → [참가자 trouble].
 * DEV 레이블과 편집 대상 segment가 그 순서에 기대므로
 * `state_payload.checkpoint_chat`과 함께 움직인다.
 */
const TURN_NOTES = [
  { segment: 'original_request', term: 'Original Request', detail: '§7.3 checkpoint packet' },
  {
    segment: 'problematic_ai_response',
    term: 'Problematic AI-response',
    detail: '§7.3 excerpt · §7.5 mismatch locus',
  },
  { segment: 'trouble_cue', term: 'AI-visible Trouble Turn', detail: '§6.2 trouble cue' },
]

/** 작은 "수정됨" 배지 — P2 전용이다(위 규칙 ③). */
function EditedBadge() {
  return (
    <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-deep">
      수정됨
    </span>
  )
}

/** hover 시 나타나는 "수정" 버튼. 키보드로도 닿아야 하므로 focus에서도 보인다. */
function EditButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="btn-secondary h-8 px-2.5 text-xs opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
    >
      ✎ {label}
    </button>
  )
}

/** 편집창 — 원문이 채워진 채로 열리고, 저장하면 닫힌다(§4.2). */
function SegmentDraft({
  segment,
  edit,
  onClose,
}: {
  segment: Segment
  edit: EditContext
  onClose: () => void
}) {
  const [draft, setDraft] = useState(segment.text)
  return (
    <div className="sec border-accent">
      <p className="mb-1 text-sm font-medium text-gray-600">{segment.label}</p>
      <p className="mb-3 text-sm text-gray-600">{edit.hint}</p>
      <AutoTextArea value={draft} onChange={setDraft} rows={3} disabled={edit.busy} autoFocus />
      <div className="mt-3 flex gap-2">
        <button type="button" className="btn-secondary" disabled={edit.busy} onClick={onClose}>
          {edit.buttons.cancel}
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={edit.busy || !draft.trim() || draft.trim() === segment.text.trim()}
          onClick={async () => {
            await edit.onSave(segment.segment, draft.trim())
            onClose()
          }}
        >
          {edit.buttons.save}
        </button>
      </div>
    </div>
  )
}

/**
 * 편집 가능한 영역 하나.
 *
 * `edit`가 없으면(= P2 밖) 자식을 그대로 그린다 — 수정 버튼도 배지도 없다. 읽기 전용
 * 화면에서 이 컴포넌트는 아무 일도 하지 않는 껍데기다.
 */
function Editable({
  name,
  edit,
  children,
}: {
  name: string
  edit?: EditContext
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const segment = edit?.segments[name]

  if (!edit || !segment) return <>{children}</>
  if (open) return <SegmentDraft segment={segment} edit={edit} onClose={() => setOpen(false)} />

  return (
    <div className="group relative">
      {children}
      <div className="mt-1.5 flex items-center gap-2">
        <EditButton label={edit.buttons.edit} onClick={() => setOpen(true)} />
        {segment.edited && <EditedBadge />}
      </div>
    </div>
  )
}

export function CheckpointCard({
  checkpoint,
  devLabels = false,
  edit,
}: {
  checkpoint: any
  /** DEV_MODE component 레이블 — **P2에서만** 켠다. 다른 화면에서는 배너만 쓴다. */
  devLabels?: boolean
  /** 수정 모드 — **P2에서만** 넘긴다. 없으면 배지도 수정 버튼도 없다. */
  edit?: EditContext
}) {
  const turns: CheckpointTurn[] = checkpoint?.turns ?? []
  const evidence: string[] = checkpoint?.prior_evidence ?? []
  const aside = (term: string, detail: string, node: JSX.Element) =>
    devLabels ? (
      <DevAside term={term} detail={detail}>
        {node}
      </DevAside>
    ) : (
      node
    )

  return (
    <div>
      {/* 상황 카드는 채팅 기록과 다른 층이다 — accent.soft 배경으로 분리한다(§4.2 [제안]). */}
      {aside(
        'AI-visible Layer',
        '§7.4 · 최소 context',
        <div className="sec border-accent bg-accent-soft">
          <Editable name="situation_summary" edit={edit}>
            <p className="whitespace-pre-wrap">{checkpoint?.situation_summary}</p>
          </Editable>
          {evidence.length > 0 && (
            <div className={devLabels ? 'mt-3 flex items-start gap-2' : 'mt-3'}>
              <div className="min-w-0 flex-1">
                <Editable name="prior_evidence" edit={edit}>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-gray-700">
                    {evidence.map((line, index) => (
                      <li key={index}>{line}</li>
                    ))}
                  </ul>
                </Editable>
              </div>
              {devLabels && <DevNote term="Prior Evidence" detail="§7.4 AI 접근 가능 정보" />}
            </div>
          )}
        </div>,
      )}
      <div className="chat mt-4">
        {turns.map((turn, index) => {
          const note = TURN_NOTES[index]
          const bubble = (
            <Editable name={note?.segment ?? ''} edit={edit}>
              <Bubble role={turn.role} text={turn.text} />
            </Editable>
          )
          return (
            <div key={index}>{note ? aside(note.term, note.detail, bubble) : bubble}</div>
          )
        })}
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

  const edit: EditContext = {
    segments: Object.fromEntries(segments.map((item) => [item.segment, item])),
    buttons: {
      edit: state.data.edit_button,
      save: state.data.save_button,
      cancel: state.data.cancel_button,
    },
    hint: state.data.edit_hint,
    busy,
    onSave: async (segment, text) => {
      await run(() => api.checkpointEdit(segment, text))
    },
  }

  return (
    <div className="screen">
      <DevScreenNote
        screen="P2"
        term="Interactional Re-entry"
        detail="§4.2·초안 §7.3 — 재구성한 AI-visible layer를 chat history 형태로 보이고 factual verification만 받는다. 수정본이 effective checkpoint가 되어 AI2 입력으로 간다. 속마음·원했던 답은 묻지 않는다."
      />
      <ScreenTitle>상황 확인</ScreenTitle>
      {/* [정본, 초안 §7.3] — 윤문 금지. 서버가 내려준 문자열을 그대로 그린다. */}
      <p className="callout mb-6 whitespace-pre-wrap">{state.data.intro}</p>

      <DevNote
        term="Editable Segments (5종)"
        detail="§4.2 — 아래 5개 블록이 참가자가 고칠 수 있는 단위다. 수정본이 effective checkpoint가 되어 AI2 입력으로 간다(§7.9)."
      />
      <CheckpointCard checkpoint={state.data.checkpoint} devLabels edit={edit} />

      <SubmitBar
        label={state.data.confirm_button ?? NEXT}
        busy={busy}
        error={error}
        onClick={() => run(() => api.checkpointConfirm())}
      />
    </div>
  )
}
