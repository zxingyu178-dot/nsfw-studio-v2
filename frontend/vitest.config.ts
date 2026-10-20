/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: false,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    // 单 fork 全量时偶发慢用例；放宽单测超时，避免负载导致的假失败。
    testTimeout: 15000,
    hookTimeout: 15000,
  },
})
