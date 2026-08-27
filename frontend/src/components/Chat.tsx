/**
 * 채팅 UI (구현명세서 §2.10 · §4.5 · D-39 — 구 리포 이식·개조).
 *
 * 참가자 우측·AI 좌측 말풍선. 조건명·branch 번호·"실험용 자극" 같은 배지를 **절대** 붙이지
 * 않는다(§4.10 construct label 비공개, §4.4 branch 번호 비표시).
 *
 * **AI 버블에는 색조를 쓰지 않는다** — AI 버블의 색조는 따뜻함 지각을 건드리고, 그건
 * recognition·uptake 평정(초안 §7.11)과 교락한다. 흰 배경 + 실선 테두리로 고정이고,
 * `test_ai_bubbles_have_no_color_tint`가 이 규칙을 지킨다.
 *
 * `isNew`는 **표시 조작이 아니라 표시 규약**이다. focal AI1 · 대안 AI1 3종 · AI2에 같은
 * 클래스(`.bubble-new`)가 붙고, 그 정의는 `index.css` 한 곳뿐이다. 조건마다 하이라이트가
 * 달라지면 그 자체가 조작이 되므로 호출부가 스타일을 넘기지 못하게 막아 둔다 —
 * `isNew`는 boolean이지 className이 아니다.
 *
 * 이식하며 뺀 것: visualViewport 기반 키보드 회피(모바일 전용 — D-12로 폐기).
 */

import { ReactNode } from 'react'

/**
 * 자극 본문 + **무대지시**(D-40).
 *
 * 어떤 AI1은 "…해 보겠습니다"로 끝나는 문장 뒤에 괄호 한 줄이 붙는다. 그 줄은 AI 발화가
 * 아니라 "실제 지원이 이어졌다고 가정한다"는 표시이므로 회색으로 구분해서 그린다.
 *
 * ⚠ 무대지시 문면을 **여기에 적지 않는다** — 서버가 `ai1_note`로 내려준다(NT-13: 자산 원문은
 * 번들에 사전 로드하지 않는다). 그리고 그 필드는 조건과 무관하게 **항상** 내려온다: 조건에
 * 따라 있고 없으면 필드의 유무 자체가 조건 단서가 된다(§1.2 · NT-31). 그래서 이 함수는
 * "받은 문면이 본문 안에 있으면 그 자리를 회색으로"만 하고, 없으면 그냥 본문을 그린다.
 */
export function StimulusText({ text, note }: { text: string; note?: string | null }) {
  const at = note ? text.indexOf(note) : -1
  if (at < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <span className="stim-note">{note}</span>
      {text.slice(at + (note as string).length)}
    </>
  )
}

interface BubbleProps {
  role: 'ai' | 'user'
  text: string
  /** 자극 안의 무대지시 문면(서버 `ai1_note`). 본문에 있으면 그 자리만 회색이 된다(D-40). */
  note?: string | null
  /** 이 화면에서 **새로 도착한** 응답인가. 하이라이트 스타일·타이밍은 전 조건 동일하다. */
  isNew?: boolean
  /** 말풍선 위에 얹을 것(P2 수정 아이콘 등). 자극 화면에서는 쓰지 않는다. */
  overlay?: ReactNode
  /** 좁은 열(P10 pairwise) — 85% 제한을 풀어 열 폭을 다 쓴다. */
  wide?: boolean
}

export function Bubble({ role, text, note, isNew = false, overlay, wide = false }: BubbleProps) {
  const mine = role === 'user'
  return (
    <div className={`chat-row ${mine ? 'justify-end' : 'justify-start'}`}>
      <div className={`group relative ${wide ? 'w-full' : 'w-fit max-w-[85%]'}`}>
        {/* ⚠ `animate-*` 유틸리티를 여기에 붙이지 마라 — utilities 레이어가 `.bubble-new`의
            `animation`을 덮어써서 새 응답 링이 사라진다(index.css 주석 참조). */}
        <p
          className={`bubble ${mine ? 'bubble-user' : 'bubble-ai'} ${isNew ? 'bubble-new' : ''}`}
        >
          <StimulusText text={text} note={note} />
        </p>
        {overlay}
      </div>
    </div>
  )
}

/** §4.5 AI1 표시 전 타이핑 인디케이터 [파일럿 확정: 1–2초]. */
export function TypingIndicator() {
  return (
    <div className="chat-row justify-start" aria-label="AI가 입력 중입니다">
      <div className="bubble bubble-ai flex gap-1.5 py-4">
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
  /** composer 안에 들어가는 보내기 버튼. 없으면 입력창만 그린다. */
  send?: { label: string; disabled?: boolean; onClick: () => void }
}

/**
 * 입력 composer — 테두리 하나가 입력창과 보내기 버튼을 함께 감싼다.
 *
 * ⚠ keystroke·삭제 이력·수정 과정을 수집하지 않는다(§4.5 금지). 이 컴포넌트는 현재 값만
 * 상위로 올린다 — 입력 과정을 이벤트로 남기는 코드를 여기에 붙이지 말 것.
 */
export function ChatInput({ value, onChange, maxChars, disabled, send }: ChatInputProps) {
  return (
    <div>
      <div className="composer">
        <textarea
          rows={4}
          value={value}
          disabled={disabled}
          maxLength={maxChars}
          onChange={(event) => onChange(event.target.value)}
        />
        {send && (
          <div className="mt-1 flex justify-end">
            <button
              type="button"
              disabled={send.disabled}
              onClick={send.onClick}
              className="btn-primary"
            >
              {send.label}
            </button>
          </div>
        )}
      </div>
      {maxChars && (
        <p className="mt-1 text-right text-sm text-gray-500">
          {value.length} / {maxChars}
        </p>
      )}
    </div>
  )
}
