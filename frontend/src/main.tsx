import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

// §2.7 연구자 콘솔은 `/admin` 한 경로뿐이다. 라우터를 들이지 않고 여기서 한 번 가른다.
// AdminApp은 NS4에서 붙는다 — 그때까지 모든 경로가 참가자 셸로 간다.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
