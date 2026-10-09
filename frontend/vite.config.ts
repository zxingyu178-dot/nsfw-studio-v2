import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期将 /api 代理到本地 FastAPI（后端地址可通过环境变量 NSFW_STUDIO_API_URL 覆盖）。
// 前端只访问 Studio 后端（含 /api/v1/events/jobs SSE），绝不直连生成引擎（规范 §五十三）。
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
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
