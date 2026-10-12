import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MobileReviewSection from './MobileReviewSection'
import { mobileReviewApi } from '../../api/client'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  mobileReviewApi: {
    runtime: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    restart: vi.fn(),
    createPairingCode: vi.fn(),
    devices: vi.fn(),
    revokeDevice: vi.fn(),
  },
}))

function runtimeState(state: string) {
  return {
    state,
    host: '0.0.0.0',
    port: 8767,
    owned: true,
    pid: 123,
    parent_pid: 1,
    started_at: null,
    detail: '',
    log_location: null,
    health: {},
  } as never
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(mobileReviewApi.runtime).mockResolvedValue(runtimeState('RUNNING'))
  vi.mocked(mobileReviewApi.devices).mockResolvedValue([] as never)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('MobileReviewPairing：配对码 + 倒计时', () => {
  it('生成配对码后显示 6 位码、10:00 倒计时与一次性提示', async () => {
    vi.mocked(mobileReviewApi.createPairingCode).mockResolvedValue({
      code: '483920',
      expires_in_seconds: 600,
    } as never)
    render(<MobileReviewSection />)
    await screen.findByText('运行中')

    fireEvent.click(screen.getByRole('button', { name: /生成配对码/ }))
    expect(await screen.findByTestId('pairing-code')).toHaveTextContent('483920')
    // 10 分钟倒计时 mm:ss
    expect(screen.getByTestId('pairing-countdown').textContent).toMatch(/^\d{2}:\d{2}$/)
    // 一次性提示
    expect(screen.getByText(/一次性，绑定成功即失效/)).toBeInTheDocument()
  })

  it('倒计时随时间递减', async () => {
    vi.useFakeTimers()
    vi.mocked(mobileReviewApi.createPairingCode).mockResolvedValue({
      code: '111222',
      expires_in_seconds: 600,
    } as never)
    render(<MobileReviewSection />)
    await vi.advanceTimersByTimeAsync(0) // flush mount（runtime/devices）promises
    fireEvent.click(screen.getByRole('button', { name: /生成配对码/ }))
    await vi.advanceTimersByTimeAsync(0) // flush createPairingCode promise
    expect(screen.getByTestId('pairing-code')).toHaveTextContent('111222')
    expect(screen.getByTestId('pairing-countdown').textContent).toBe('10:00')

    // 过 61 秒 → 08:59
    await vi.advanceTimersByTimeAsync(61_000)
    expect(screen.getByTestId('pairing-countdown').textContent).toBe('08:59')
  })

  it('配对码过期后自动隐藏', async () => {
    vi.useFakeTimers()
    vi.mocked(mobileReviewApi.createPairingCode).mockResolvedValue({
      code: '654321',
      expires_in_seconds: 600,
    } as never)
    render(<MobileReviewSection />)
    await vi.advanceTimersByTimeAsync(0)
    fireEvent.click(screen.getByRole('button', { name: /生成配对码/ }))
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.getByTestId('pairing-code')).toHaveTextContent('654321')

    // 过 10 分钟 + 1 秒 → 码自动消失
    await vi.advanceTimersByTimeAsync(601_000)
    expect(screen.queryByTestId('pairing-code-box')).not.toBeInTheDocument()
  })
})
