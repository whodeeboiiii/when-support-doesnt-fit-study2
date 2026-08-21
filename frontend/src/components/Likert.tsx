/**
 * 1–7 가로 숫자 버튼 (§4.8 · D-39 — 구 리포 이식·개조).
 *
 * 척도는 전 문항 1(전혀 그렇지 않다)–7(매우 그렇다)로 고정이다(§0.5·초안 §7.11). 드롭다운도
 * 라디오 원도 쓰지 않는다 — 여러 문항을 한 화면에서 비교하며 답하는 구성에서 선택 상태가
 * 한눈에 보여야 하고, 원은 Zoom 공유 화면에서 축소되면 채워졌는지 아닌지가 사라진다.
 * 그래서 **누를 수 있는 숫자 버튼**이고, 숫자는 16px 밑으로 내려가지 않는다.
 *
 * 양 끝 앵커는 문항마다 반복해서 고정 표시한다. 블록 상단에 한 번만 두면 스크롤 뒤에는
 * "7이 긍정이었나 부정이었나"를 기억에 의존하게 된다.
 *
 * 선택 상태는 **파랑 테두리 + 연파랑 배경**이다(`.is-selected`). 1차 버튼은 파랑 **채움**
 * 이므로 "내가 고른 것"과 "눌러야 할 것"이 채움/윤곽으로 갈린다(D-39).
 *
 * 문항 순서는 **서버가 정해서 내려준다**(블록 내 무작위, D-37). 이 컴포넌트는 받은 순서를
 * 그대로 그린다 — 클라이언트에서 섞으면 저장된 display_order와 화면이 어긋난다.
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
  minLabel?: string
  maxLabel?: string
}

export function LikertRow({ min, max, value, onChange, minLabel, maxLabel }: RowProps) {
  const points = Array.from({ length: max - min + 1 }, (_, index) => min + index)
  return (
    <div className="mt-3">
      <div className="flex gap-2" role="radiogroup">
        {points.map((point) => {
          const selected = value === point
          return (
            <button
              key={point}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={
                point === min && minLabel
                  ? `${point} ${minLabel}`
                  : point === max && maxLabel
                    ? `${point} ${maxLabel}`
                    : String(point)
              }
              onClick={() => onChange(point)}
              className={`h-12 flex-1 rounded-xl border text-base transition-colors ${
                selected
                  ? 'is-selected font-semibold'
                  : 'border-hair bg-gray-50 text-gray-700 hover:border-edge hover:bg-gray-100'
              }`}
            >
              {point}
            </button>
          )
        })}
      </div>
      {(minLabel || maxLabel) && (
        <div className="mt-1.5 flex justify-between text-sm text-gray-500">
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
  minLabel?: string
  maxLabel?: string
  /** 블록 지시문 (§4.8 블록 1·2의 안내 문안). */
  instruction?: string
}

export function LikertList({
  items,
  values,
  onChange,
  min = 1,
  max = 7,
  minLabel,
  maxLabel,
  instruction,
}: ListProps) {
  return (
    <div className="space-y-5">
      {instruction && <p className="callout whitespace-pre-wrap">{instruction}</p>}
      {items.map((item) => (
        <div key={item.id} className="sec">
          <p className="text-base">{item.text}</p>
          <LikertRow
            min={min}
            max={max}
            minLabel={minLabel}
            maxLabel={maxLabel}
            value={values[item.id] ?? null}
            onChange={(value) => onChange(item.id, value)}
          />
        </div>
      ))}
    </div>
  )
}
