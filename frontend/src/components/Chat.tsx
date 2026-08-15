/**
 * 채팅 UI (구현명세서 §2.10 · §4.5 — 구 리포 `components/Chat.tsx` 이식·개조).
 *
 * 참가자 우측·AI 좌측 말풍선. 조건명·branch 번호·"실험용 자극" 같은 배지를 **절대** 붙이지
 * 않는다(§4.10 construct label 비공개, §4.4 branch 번호 비표시).
 *
 * 버블에는 액센트 색을 쓰지 않는다 — AI 버블의 색조는 따뜻함 지각을 건드리고, 그건
 * recognition·uptake 평정(§7.3 문항 1·2)과 교락한다. 무채색이 방어적이다.
 *
 * 이식하며 뺀 것: visualViewport 기반 키보드 회피(모바일 전용 — D-12로 폐기).
 */

interface BubbleProps {
  role: 'ai' | 'user'
  text: string
}

export function Bubble({ role, text }: BubbleProps) {
  const mine = role === 'user'
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <p
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 ${
          mine ? 'bg-ink text-white' : 'bg-gray-100 text-ink'
        }`}
      >
        {text}
      </p>
    </div>
  )
}

/** §4.5 AI1 표시 전 타이핑 인디케이터 [파일럿 확정: 1–2초]. */
export function TypingIndicator() {
  return (
    <div className="flex justify-start" aria-label="AI가 입력 중입니다">
      <div className="flex gap-1 rounded-2xl bg-gray-100 px-4 py-3">
        <span className="h-2 w-2 animate-pulse rounded-full bg-edge" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-edge [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-edge [animation-delay:300ms]" />
      </div>
    </div>
  )
}

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  maxChars?: number
  /** §2.10 — 로딩 중(AI2 생성) 입력 비활성. */
  disabled?: boolean
}

export function ChatInput({ value, onChange, maxChars, disabled }: ChatInputProps) {
  return (
    <div>
      <textarea
        rows={5}
        value={value}
        disabled={disabled}
        maxLength={maxChars}
        onChange={(event) => onChange(event.target.value)}
        className="w-full resize-none rounded-lg border border-edge p-3 text-base disabled:bg-gray-50"
      />
      {maxChars && (
        <p className="mt-1 text-right text-sm text-gray-500">
          {value.length} / {maxChars}
        </p>
      )}
    </div>
  )
}
