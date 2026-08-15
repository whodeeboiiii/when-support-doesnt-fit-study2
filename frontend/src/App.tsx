/**
 * 앱 셸 (NS1 스캐폴드).
 *
 * 클라이언트 라우터를 두지 않는다: 상태는 서버가 소유하고(§1.3·§3.5), 화면 선택은 `GET /state`가
 * 알려준 SS·B 상태로 한다. 그 셸은 NS2에서 P0–P11과 함께 붙는다.
 *
 * 지금은 기동 확인용 화면만 있다 — 백엔드 `/api/health`를 한 번 부르고 결과를 보여준다.
 */

import { useEffect, useState } from 'react'

interface Health {
  status: string
  study_version: string
  dev_mode: boolean
  dossiers: { loaded: number; schema_dummy: string[]; locked: string[] }
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then(setHealth)
      .catch((reason) => setError(String(reason)))
  }, [])

  return (
    <div className="screen">
      <h1 className="screen-title">NOT QUITE YES — Study 2</h1>
      <div className="sec">
        <p className="text-sm text-gray-600">
          NS1 스캐폴드 화면입니다. 참가자 화면(P0–P11)은 NS2에서 붙습니다.
        </p>
        {error && <p className="mt-3 text-sm">서버 상태를 불러오지 못했습니다 ({error}).</p>}
        {health && (
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-gray-500">study_version</dt>
            <dd>{health.study_version}</dd>
            <dt className="text-gray-500">DEV_MODE</dt>
            <dd>{String(health.dev_mode)}</dd>
            <dt className="text-gray-500">dossier</dt>
            <dd>
              {health.dossiers.loaded}건 (스키마 더미 {health.dossiers.schema_dummy.length}건)
            </dd>
          </dl>
        )}
      </div>
    </div>
  )
}
