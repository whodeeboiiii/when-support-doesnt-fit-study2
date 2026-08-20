/**
 * 1–7 가로 버튼 행 (구 리포 `components/Likert.tsx` 이식·개조).
 *
 * 척도는 전 문항 1(전혀 그렇지 않다)–7(매우 그렇다)로 고정이다(§0.5·§7.3). 드롭다운을 쓰지
 * 않는다 — 12문항을 한 화면에서 비교하며 답하는 구성(§4.9)에서 선택 상태가 한눈에 보여야 한다.
 *
 * 문항 순서는 **서버가 정해서 내려준다**(블록 내 무작위, D-13·D-22). 이 컴포넌트는 받은
 * 순서를 그대로 그린다 — 클라이언트에서 섞으면 저장된 display_order와 화면이 어긋난다.
 *
 * 이식하며 뺀 것: 터치 타깃 44px 규칙(모바일 전용 — D-12로 폐기).
 */

export interface LikertItem {
  id: string
  text: string
}

interface RowProps {
  min: number
  max: number
  value: number | null
  onChange: (value: number) => void
  /** 양 끝 앵커 (P9는 화면 상단에 따로 그리고, P2는 문항마다 여기서 그린다). */
  minLabel?: string
  maxLabel?: string
}

/** 선택 표시는 **채움**이다 — 7칸에 체크 아이콘을 넣으면 숫자 가독성만 떨어진다. */
export function LikertRow({ min, max, value, onChange, minLabel, maxLabel }: RowProps) {
  const points = Array.from({ length: max - min + 1 }, (_, index) => min + index)
  return (
    <div className="mt-2">
      <div className="flex gap-1" role="radiogroup">
        {points.map((point) => (
          <button
            key={point}
            type="button"
            role="radio"
            aria-checked={value === point}
            aria-label={
              point === min && minLabel
                ? `${point} ${minLabel}`
                : point === max && maxLabel
                  ? `${point} ${maxLabel}`
                  : String(point)
            }
            onClick={() => onChange(point)}
            className={`h-11 flex-1 rounded-lg border text-base ${
              value === point
                ? 'border-ink bg-ink font-semibold text-white'
                : 'border-edge bg-white text-gray-700'
            }`}
          >
            {point}
          </button>
        ))}
      </div>
      {(minLabel || maxLabel) && (
        <div className="mt-1 flex justify-between text-xs text-gray-500">
          <span>{minLabel}</span>
          <span>{maxLabel}</span>
        </div>
      )}
    </div>
  )
}

interface ListProps {
  items: LikertItem[]
  values: Record<string, number>
  onChange: (id: string, value: number) => void
  min?: number
  max?: number
  /** 블록 지시문 (§4.9 블록 1·2의 안내 문안). */
  instruction?: string
}

export function LikertList({ items, values, onChange, min = 1, max = 7, instruction }: ListProps) {
  return (
    <div className="space-y-6">
      {instruction && <p className="text-sm text-gray-600">{instruction}</p>}
      {items.map((item) => (
        <div key={item.id}>
          <p>{item.text}</p>
          <LikertRow
            min={min}
            max={max}
            value={values[item.id] ?? null}
            onChange={(value) => onChange(item.id, value)}
          />
        </div>
      ))}
    </div>
  )
}
