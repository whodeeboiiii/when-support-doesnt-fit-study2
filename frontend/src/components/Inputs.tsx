/**
 * 공통 입력 요소 (§2.10 · D-39 — 구 리포 이식·개조, 데스크톱 전용).
 *
 * 이식하며 뺀 것: 터치 타깃 44px 규칙, 하단 **고정**(sticky) 제출 막대. 둘 다 모바일 우선
 * 규칙이었고 이 연구는 데스크톱 전용이다(D-12·§2.10). 제출 버튼은 흐름 안에 둔다 —
 * Zoom 화면공유로 함께 보는 화면에서 고정 막대는 본문을 가린다.
 *
 * 버튼 위계는 세 가지뿐이다(D-39, `index.css`에 정의).
 * - `.btn-primary` 파랑 **채움** — 진행·보내기. 화면당 하나.
 * - `.btn-secondary` 흰 배경 + 테두리 — 취소·수정.
 * - `.is-selected` 파랑 테두리 + 연파랑 배경 — 내가 고른 것(카드·Likert).
 * 노랑은 버튼에 쓰지 않는다 — 노랑 위 흰 글자는 대비가 안 나온다.
 *
 * 진행 표시(스텝 인디케이터)는 두지 않는다. "3/7" 같은 수치는 남은 분량을 알려주는 대신
 * 대안 노출 수·조건 수를 추론할 실마리가 된다(§4.10 construct label 비공개).
 */

import { useEffect, useRef } from 'react'

export interface Choice {
  value: string
  label: string
  example?: string
}

interface CardsProps {
  cards: Choice[]
  value: string | null
  onChange: (value: string) => void
}

/**
 * 선택 카드 (P7 이탈 유형 6종 등).
 *
 * 선택 표시에 `ring`을 쓰는 이유는 레이아웃 때문이다 — 테두리를 2px로 굵히면 카드 안
 * 텍스트가 1px씩 움직여 목록 전체가 흔들린다. ring은 box-shadow라 자리를 차지하지 않는다.
 * 색에만 기대지 않도록 좌측 바와 체크를 함께 둔다.
 */
export function Cards({ cards, value, onChange }: CardsProps) {
  return (
    <div className="space-y-3">
      {cards.map((card) => {
        const selected = value === card.value
        return (
          <button
            key={card.value}
            type="button"
            onClick={() => onChange(card.value)}
            aria-pressed={selected}
            className={`relative w-full rounded-xl border p-4 pr-10 text-left transition-colors ${
              selected
                ? 'is-selected ring-1 ring-accent'
                : 'border-hair bg-white hover:border-edge hover:bg-gray-50'
            }`}
          >
            {selected && (
              <>
                <span
                  aria-hidden
                  className="absolute inset-y-0 left-0 w-1.5 rounded-l-xl bg-accent"
                />
                <span aria-hidden className="absolute right-3 top-3 font-bold text-accent-deep">
                  ✓
                </span>
              </>
            )}
            <span className="block font-medium">{card.label}</span>
            {card.example && (
              <span className="mt-1 block text-sm text-gray-600">{card.example}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

interface ChecksProps {
  items: { field: string; label: string; detail?: string }[]
  values: Record<string, boolean>
  onChange: (field: string, value: boolean) => void
}

/** 복수 체크 (P1 동의 항목별 체크 — §4.1). */
export function Checks({ items, values, onChange }: ChecksProps) {
  return (
    <div className="space-y-4">
      {items.map((item) => (
        <label
          key={item.field}
          className="flex cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 hover:bg-gray-50"
        >
          <input
            type="checkbox"
            className="mt-1 h-5 w-5 accent-accent"
            checked={values[item.field] ?? false}
            onChange={(event) => onChange(item.field, event.target.checked)}
          />
          <span>
            {item.label}
            {item.detail && <span className="mt-1 block text-sm text-gray-600">{item.detail}</span>}
          </span>
        </label>
      ))}
    </div>
  )
}

interface TextAreaProps {
  value: string
  onChange: (value: string) => void
  minChars?: number
  maxChars?: number
  rows?: number
  disabled?: boolean
  autoFocus?: boolean
}

/**
 * 자동 확장 textarea + 글자 수 표시 (P5 sidecar 자유기술 등).
 *
 * ⚠ keystroke·삭제 이력·수정 과정을 수집하지 않는다(§4.5 금지). 이 컴포넌트는 현재 값만
 * 상위로 올린다 — 입력 과정을 이벤트로 남기는 코드를 여기에 붙이지 말 것.
 */
export function AutoTextArea({
  value,
  onChange,
  minChars,
  maxChars,
  rows = 5,
  disabled,
  autoFocus,
}: TextAreaProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${node.scrollHeight}px`
  }, [value])

  return (
    <div>
      <div className="composer">
        <textarea
          ref={ref}
          rows={rows}
          value={value}
          disabled={disabled}
          maxLength={maxChars}
          autoFocus={autoFocus}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {(minChars || maxChars) && (
        <p className="mt-1 text-right text-sm text-gray-500">
          {value.length}
          {maxChars ? ` / ${maxChars}` : ''}
          {minChars && value.length < minChars ? ` (최소 ${minChars})` : ''}
        </p>
      )}
    </div>
  )
}

interface SubmitBarProps {
  label: string
  disabled?: boolean
  busy?: boolean
  onClick: () => void
  secondary?: { label: string; onClick: () => void }
  error?: string | null
}

/** 제출 영역 — 흐름 안에 둔다(데스크톱 전용 개조). 1차 버튼은 화면에 하나뿐이다. */
export function SubmitBar({ label, disabled, busy, onClick, secondary, error }: SubmitBarProps) {
  return (
    <div className="mt-8 border-t border-hair pt-5">
      {error && (
        <p role="alert" className="mb-2 text-sm text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        {secondary && (
          <button type="button" onClick={secondary.onClick} className="btn-secondary flex-1">
            {secondary.label}
          </button>
        )}
        <button type="button" disabled={disabled || busy} onClick={onClick} className="btn-primary flex-1">
          {label}
        </button>
      </div>
    </div>
  )
}
