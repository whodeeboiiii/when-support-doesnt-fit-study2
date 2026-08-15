/**
 * 공통 입력 요소 (구 리포 `components/Inputs.tsx` 이식·개조 — 데스크톱 전용).
 *
 * 이식하며 뺀 것: 터치 타깃 44px 규칙, 하단 **고정**(sticky) 제출 막대. 둘 다 모바일 우선
 * 규칙이었고 이 연구는 데스크톱 전용이다(D-12·§2.10). 제출 버튼은 흐름 안에 둔다 —
 * Zoom 화면공유로 함께 보는 화면에서 고정 막대는 본문을 가린다.
 *
 * 남긴 것: 선택 상태를 **색으로만 말하지 않기**(좌측 바 + 체크), 비활성 버튼 대비,
 * 1차 버튼만 파랑 규약. 색 규약의 근거는 `tailwind.config.js` 주석에 있다.
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
 * 선택 카드 (P8 downstream 7선택 등).
 *
 * 선택 표시에 `ring`을 쓰는 이유는 레이아웃 때문이다 — 테두리를 2px로 굵히면 카드 안
 * 텍스트가 1px씩 움직여 목록 전체가 흔들린다. ring은 box-shadow라 자리를 차지하지 않는다.
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
            className={`relative w-full rounded-lg border bg-white p-4 pr-10 text-left ${
              selected ? 'border-ink ring-2 ring-ink' : 'border-edge'
            }`}
          >
            {selected && (
              <>
                <span aria-hidden className="absolute inset-y-0 left-0 w-1.5 rounded-l-lg bg-ink" />
                <span aria-hidden className="absolute right-3 top-3 font-bold">
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
        <label key={item.field} className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1 h-5 w-5 accent-ink"
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
}

/**
 * 자동 확장 textarea + 글자 수 표시 (P6 sidecar 자유기술 등).
 *
 * ⚠ keystroke·삭제 이력·수정 과정을 수집하지 않는다(§4.6 금지). 이 컴포넌트는 현재 값만
 * 상위로 올린다 — 입력 과정을 이벤트로 남기는 코드를 여기에 붙이지 말 것.
 */
export function AutoTextArea({
  value,
  onChange,
  minChars,
  maxChars,
  rows = 5,
  disabled,
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
      <textarea
        ref={ref}
        rows={rows}
        value={value}
        disabled={disabled}
        maxLength={maxChars}
        onChange={(event) => onChange(event.target.value)}
        className="w-full resize-none rounded-lg border border-edge p-3 text-base disabled:bg-gray-50"
      />
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

/**
 * 제출 영역 — 흐름 안에 둔다(데스크톱 전용 개조).
 *
 * 1차 버튼만 파랑(accent.deep — 흰 글자 7.56:1)이다. 화면에서 "다음으로 간다"는 뜻을 가진
 * 유일한 요소이고, 선택 상태를 검정으로 남긴 것이 이것과 짝이다.
 */
export function SubmitBar({ label, disabled, busy, onClick, secondary, error }: SubmitBarProps) {
  return (
    <div className="mt-8 border-t border-hair pt-4">
      {error && (
        <p role="alert" className="mb-2 text-sm text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        {secondary && (
          <button
            type="button"
            onClick={secondary.onClick}
            className="h-11 flex-1 rounded-lg border border-edge bg-white px-4"
          >
            {secondary.label}
          </button>
        )}
        <button
          type="button"
          disabled={disabled || busy}
          onClick={onClick}
          className="h-11 flex-1 rounded-lg bg-accent-deep px-4 font-medium text-white disabled:bg-gray-200 disabled:text-gray-500"
        >
          {label}
        </button>
      </div>
    </div>
  )
}

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const percent = total === 0 ? 0 : Math.round((done / total) * 100)
  return (
    <div className="mb-6 h-1 w-full rounded bg-gray-200">
      <div className="h-1 rounded bg-accent" style={{ width: `${percent}%` }} />
    </div>
  )
}
