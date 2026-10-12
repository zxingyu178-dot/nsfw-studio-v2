import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SettingsPage from './SettingsPage'
import { ThemeProvider } from '../../themes/ThemeProvider'
import type { SystemStatus } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  systemApi: { status: vi.fn() },
  engineRuntimeApi: { get: vi.fn(), start: vi.fn(), stop: vi.fn(), restart: vi.fn() },
  imageApi: { startBackfill: vi.fn(), backfillStatus: vi.fn(), stopBackfill: vi.fn() },
  mobileReviewApi: {
    runtime: vi.fn().mockResolvedValue({
      state: 'STOPPED', host: '0.0.0.0', port: 8767, owned: true, pid: null,
      parent_pid: null, started_at: null, detail: '', log_location: null, health: {},
    }),
    start: vi.fn(),
    stop: vi.fn(),
    restart: vi.fn(),
    createPairingCode: vi.fn(),
    devices: vi.fn().mockResolvedValue([]),
    revokeDevice: vi.fn(),
  },
}))

function makeStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    app_version: 'v0.11.0',
    data_root: 'D:\\NSFWStudio\\DataRoot',
    database_path: 'D:\\NSFWStudio\\DataRoot\\studio.db',
    database_size: 12 * 1024 * 1024,
    disk_total: 100 * 1024 * 1024 * 1024,
    disk_free: 40 * 1024 * 1024 * 1024,
    image_count: 120,
    thumbnail_count: 100,
    preview_count: 80,
    latest_migration: '0017',
    engine_runtime: {
      state: 'RUNNING_MANAGED',
      host: '127.0.0.1',
      port: 8188,
      owned: true,
      pid: 1234,
      started_at: null,
      detail: '',
      log_location: null,
      health: { online: true, engine_name: 'comfyui', engine_version: '0.3.0' },
    },
    ...overrides,
  }
}

function renderPage() {
  return render(
    <ThemeProvider>
      <SettingsPage />
    </ThemeProvider>,
  )
}

describe('SettingsPage 设置', () => {
  beforeEach(async () => {
    const { systemApi, imageApi } = await import('../../api/client')
    vi.mocked(systemApi.status).mockResolvedValue(makeStatus() as never)
    vi.mocked(imageApi.backfillStatus).mockResolvedValue({ running: false, done: 0, total: 0, failed: 0, kind: null } as never)
  })

  it('渲染外观主题选择与关于面板', () => {
    renderPage()
    expect(screen.getByText('外观')).toBeInTheDocument()
    expect(screen.getByText('关于')).toBeInTheDocument()
    expect(screen.getByLabelText('深色')).toBeInTheDocument()
    expect(screen.getByLabelText('浅色')).toBeInTheDocument()
  })

  it('点击浅色主题可切换选中', () => {
    renderPage()
    const light = screen.getByLabelText('浅色') as HTMLInputElement
    fireEvent.click(light)
    expect(light.checked).toBe(true)
  })

  it('展示系统状态：引擎/缓存计数/存储/版本与 migration', async () => {
    renderPage()
    // 引擎状态与地址
    expect(await screen.findByText('运行中（Studio 托管）')).toBeInTheDocument()
    expect(screen.getByText(/127\.0\.0\.1:8188/)).toBeInTheDocument()

    // 图片缓存计数
    expect(screen.getByText(/100 \/ 120 张已生成/)).toBeInTheDocument()
    expect(screen.getByText(/80 \/ 120 张已生成/)).toBeInTheDocument()

    // 存储
    expect(screen.getByText('D:\\NSFWStudio\\DataRoot')).toBeInTheDocument()

    // 关于：按 systemApi 返回值如实展示，不硬编码 v0.12
    expect(screen.getByText('v0.11.0')).toBeInTheDocument()
    expect(screen.getByText('0017')).toBeInTheDocument()
  })

  it('运行中（托管）引擎显示停止/重启按钮', async () => {
    const { engineRuntimeApi } = await import('../../api/client')
    renderPage()
    expect(await screen.findByRole('button', { name: '停止引擎' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重启' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '停止引擎' }))
    await waitFor(() => expect(engineRuntimeApi.stop).toHaveBeenCalled())
  })

  it('点击补齐缩略图调用 backfill 并显示进度与停止按钮', async () => {
    const { imageApi } = await import('../../api/client')
    vi.mocked(imageApi.startBackfill).mockResolvedValue({ running: true, done: 5, total: 100, failed: 0, kind: 'thumbnail' } as never)
    vi.mocked(imageApi.stopBackfill).mockResolvedValue({ running: false, done: 100, total: 100, failed: 0, kind: 'thumbnail' } as never)

    renderPage()
    await screen.findByText('运行中（Studio 托管）')

    fireEvent.click(screen.getByRole('button', { name: '补齐缩略图' }))
    await waitFor(() => expect(imageApi.startBackfill).toHaveBeenCalledWith({ kind: 'thumbnail' }))

    // 回填进度 + 停止
    expect(await screen.findByText(/回填中：5 \/ 100/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '停止' }))
    await waitFor(() => expect(imageApi.stopBackfill).toHaveBeenCalled())
  })
})
