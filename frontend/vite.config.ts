import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期将 /api 代理到本地 FastAPI（后端地址可通过环境变量 NSFW_STUDIO_API_URL 覆盖）。
// 这里只涉及后端 API 地址，不涉及任何生成引擎（Phase 0 不绑定 ComfyUI）。
const apiTarget = process.env.NSFW_STUDIO_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
