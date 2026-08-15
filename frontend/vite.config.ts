import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 배포 단위 1개 — FastAPI가 dist를 정적 서빙한다 (구현명세서 §2.0).
// dev에서는 /api만 백엔드로 프록시한다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
