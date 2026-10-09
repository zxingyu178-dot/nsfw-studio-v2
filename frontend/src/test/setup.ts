import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个用例后自动卸载组件，避免状态泄漏。
afterEach(() => {
  cleanup()
})
