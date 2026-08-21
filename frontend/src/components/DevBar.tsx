/**
 * DEV_MODE 개발 바 — **명세서 범위 밖의 개발 도구**다(연구 화면 아님).
 *
 * 시연을 반복해서 돌리려면 "종료된 세션"에서 처음으로 되돌아갈 방법이 있어야 한다. 그
 * 되돌리기를 참가자 화면 안에 두되, 두 가지를 지킨다.
 *
 * 1. **존재 여부를 서버가 정한다.** `/api/dev/status`가 404면(= 배포 구성) 아무것도 그리지
 *    않는다. 프런트에 "지금이 개발이다"라고 믿는 플래그를 두지 않는다.
 * 2. **자동 접속하지 않는다.** 초기화는 데이터 삭제 + 새 접속 코드 발급까지이고, P0(§4.0)은
 *    사람이 다시 밟는다. 발급된 코드를 P0 입력칸에 채워 주는 것까지가 편의의 한계다.
 */

import { useCallback, useEffect, useState } from 'react'
import { DevStatus, dev } from '../api'

export interface DevPrefill {
  participantNo: string
  accessCode: string
}

export default function DevBar({ onReset }: { onReset: (prefill: DevPrefill) => void }) {
  const [status, setStatus] = useState<DevStatus | null>(null)
  const [target, setTarget] = useState<string>('')
  const [issued, setIssued] = useState<DevPrefill | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const next = await dev.status()
    setStatus(next)
    if (next) setTarget((current) => current || next.default_participant)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // 배포 구성에서는 여기서 끝난다 — 바가 존재하지 않는다.
  if (!status) return null

  const current = status.sessions.find((row) => row.participant_no === target)

  const reset = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await dev.reset(target)
      const prefill = { participantNo: result.participant_no, accessCode: result.access_code }
      setIssued(prefill)
      onReset(prefill)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '초기화에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-72 rounded-lg border border-violet-400 bg-violet-50 p-3 text-xs text-violet-900 shadow-lg">
      <div className="flex items-center justify-between font-semibold">
        <span>DEV_MODE</span>
        <span className="font-normal">개발 전용 · 배포에는 없음</span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <select
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          className="h-8 flex-1 rounded border border-violet-300 bg-white px-2"
        >
          {status.participants.map((participant) => (
            <option key={participant} value={participant}>
              {participant}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={reset}
          disabled={busy || !target}
          className="h-8 rounded bg-violet-600 px-3 font-semibold text-white disabled:opacity-50"
        >
          {busy ? '초기화 중…' : '세션 초기화'}
        </button>
      </div>
      <p className="mt-2">
        현재: {current ? `${current.ss_state} · ${current.status}` : '세션 없음'}
      </p>
      {issued && (
        <p className="mt-1">
          새 접속 코드 <span className="font-mono font-semibold">{issued.accessCode}</span> —
          접속 화면에 채워 두었습니다.
        </p>
      )}
      {error && <p className="mt-1 text-red-700">{error}</p>}
    </div>
  )
}
