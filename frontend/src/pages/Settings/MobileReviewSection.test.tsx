import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
  vi.mocked(mobileReviewApi.devices).mockResolvedValue([] as never)
})

describe('MobileReviewSettings：运行状态与启停', () => {
  it('停止时显示「已停止」+ 端口 8767 + 启动按钮', async () => {
    vi.mocked(mobileReviewApi.runtime).mockResolvedValue(runtimeState('STOPPED'))
    render(<MobileReviewSection />)
    expect(await screen.findByText('已停止')).toBeInTheDocument()
    expect(screen.getByText(/电脑局域网IP/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /启动手机审核桥/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止' })).not.toBeInTheDocument()
  })

  it('点击启动 → mobileReviewApi.start() → 刷新 runtime', async () => {
    vi.mocked(mobileReviewApi.runtime)
      .mockResolvedValueOnce(runtimeState('STOPPED'))
      .mockResolvedValueOnce(runtimeState('RUNNING'))
    vi.mocked(mobileReviewApi.start).mockResolvedValue(runtimeState('RUNNING'))
    render(<MobileReviewSection />)
    await screen.findByText('已停止')

    fireEvent.click(screen.getByRole('button', { name: /启动手机审核桥/ }))
    await waitFor(() => expect(mobileReviewApi.start).toHaveBeenCalled())
    // 启动后 runtime 重载 → 显示运行中 + 停止按钮
    expect(await screen.findByText('运行中')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
  })

  it('运行中点击停止 → mobileReviewApi.stop()', async () => {
    vi.mocked(mobileReviewApi.runtime).mockResolvedValue(runtimeState('RUNNING'))
    render(<MobileReviewSection />)
    expect(await screen.findByText('运行中')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '停止' }))
    await waitFor(() => expect(mobileReviewApi.stop).toHaveBeenCalled())
  })
})

describe('MobileReviewSettings：已配对设备', () => {
  it('渲染设备列表；点击撤销 → revokeDevice 并刷新列表', async () => {
    vi.mocked(mobileReviewApi.runtime).mockResolvedValue(runtimeState('RUNNING'))
    vi.mocked(mobileReviewApi.devices)
      .mockResolvedValueOnce([
        { device_id: 'dev_1', installation_id: 'phone-a', name: 'Pixel', paired_at: '2026-10-12T01:00:00Z' },
      ] as never)
      .mockResolvedValueOnce([] as never)
    vi.mocked(mobileReviewApi.revokeDevice).mockResolvedValue({} as never)

    render(<MobileReviewSection />)
    expect(await screen.findByText('Pixel')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '撤销' }))
    await waitFor(() => expect(mobileReviewApi.revokeDevice).toHaveBeenCalledWith('dev_1'))
    // 撤销后重新拉取 → 列表变空
    await waitFor(() => expect(screen.getByText(/暂无已配对设备/)).toBeInTheDocument())
  })

  it('设备端点不可用时优雅降级为提示，不炸面板', async () => {
    vi.mocked(mobileReviewApi.runtime).mockResolvedValue(runtimeState('STOPPED'))
    vi.mocked(mobileReviewApi.devices).mockRejectedValue(new Error('HTTP 404'))
    render(<MobileReviewSection />)
    await screen.findByText('已停止')
    expect(await screen.findByText(/设备列表暂不可用/)).toBeInTheDocument()
    // 主操作（启动）仍可用
    expect(screen.getByRole('button', { name: /启动手机审核桥/ })).toBeInTheDocument()
  })
})
