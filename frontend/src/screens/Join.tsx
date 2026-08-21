/**
 * P0 — 접속 (구현명세서 §4.0 · §2.5).
 *
 * 참가자 번호 + 6자리 일회용 접속 코드. 검증 실패 문안은 **서버가** 내려준다 — 번호가 틀렸는지
 * 코드가 틀렸는지 구분하지 않는 문장이 §4.0의 [제안]이고, 그 판단은 서버에만 있어야 한다.
 *
 * 실패 5회 시 30초 지연도 서버가 건다(429 + Retry-After). 클라이언트에서 세는 카운터를 두지
 * 않는다 — 새로고침 한 번으로 초기화되는 방어는 방어가 아니다.
 */

import { useState } from 'react'
import { ApiError, AppState, api } from '../api'
import { DevPrefill } from '../components/DevBar'
import { DevScreenNote } from '../components/DevNote'
import { SubmitBar } from '../components/Inputs'
import { JOIN_CODE_LABEL, JOIN_PARTICIPANT_LABEL, JOIN_SUBMIT, JOIN_TITLE } from '../copy'
import { ScreenTitle } from './common'

export default function Join({
  onState,
  prefill,
}: {
  onState: (next: AppState) => void
  /** DEV_MODE 초기화가 방금 발급한 번호·코드. 채워만 두고 접속은 사람이 누른다. */
  prefill?: DevPrefill | null
}) {
  const [participantNo, setParticipantNo] = useState(prefill?.participantNo ?? '')
  const [code, setCode] = useState(prefill?.accessCode ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      onState(await api.join(participantNo.trim().toUpperCase(), code.trim()))
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '접속에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="screen">
      <DevScreenNote
        screen="P0"
        term="접속"
        detail="§4.0 — 참가자 번호 + 6자리 일회용 코드(TTL 24h). 데스크톱 가드(768×600)가 이 화면보다 앞에 선다."
      />
      <ScreenTitle>{JOIN_TITLE}</ScreenTitle>
      <div className="sec space-y-4">
        <label className="block">
          <span className="text-sm text-gray-600">{JOIN_PARTICIPANT_LABEL}</span>
          <input
            value={participantNo}
            onChange={(event) => setParticipantNo(event.target.value)}
            autoComplete="off"
            className="mt-1 h-11 w-full rounded-lg border border-edge px-3 text-base focus:border-accent"
          />
        </label>
        <label className="block">
          <span className="text-sm text-gray-600">{JOIN_CODE_LABEL}</span>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            autoComplete="off"
            maxLength={8}
            className="mt-1 h-11 w-full rounded-lg border border-edge px-3 text-base tracking-widest focus:border-accent"
          />
        </label>
      </div>
      <SubmitBar
        label={JOIN_SUBMIT}
        busy={busy}
        disabled={!participantNo.trim() || !code.trim()}
        onClick={submit}
        error={error}
      />
    </div>
  )
}
