import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { PowerControl } from '../PowerMenu'
import { engineRuntimeApi, jobApi, systemApi } from '../../api/client'
import type { EngineRuntimeDTO, EngineRuntimeState } from '../../types/workbench'

vi.mock('../../api/client', () => {
  class ApiRequestError extends Error {
    readonly code: string
    readonly status: number
    constructor(code: string, message: string, status: number) {
      super(message)
      this.code = code
      this.status = status
      this.name = 'ApiRequestError'
    }
  }
  return {
    ApiRequestError,
    engineRuntimeApi: {
      get: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      restart: vi.fn(),
    },
    jobApi: {
      queue: vi.fn(),
      pauseQueue: vi.fn(),
    },
    systemApi: {
      status: vi.fn(),
      requestShutdown: vi.fn(),
    },
  }
})

const getMock = engineRuntimeApi.get as Mock
const queueMock = jobApi.queue as Mock
const requestShutdownMock = systemApi.requestShutdown as Mock

function rt(state: EngineRuntimeState, overrides: Partial<EngineRuntimeDTO> = {}): EngineRuntimeDTO {
  return {
    state,
    host: '127.0.0.1',
    port: 8188,
    owned: state === 'RUNNING_MANAGED',
    pid: state === 'RUNNING_MANAGED' ? 1234 : null,
    started_at: null,
    detail: '',
    log_location: null,
    health: {
      online: state === 'RUNNING_MANAGED' || state === 'RUNNING_EXTERNAL',
      engine_name: 'comfyui',
      engine_version: '0.3.0',
    },
    ...overrides,
  }
}

const emptyQueue = {
  worker: { running: false },
  running: null,
  queued: [],
  paused: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  queueMock.mockResolvedValue(emptyQueue)
})

afterEach(() => {
  vi.clearAllMocks()
})

async function openPowerPanel(): Promise<void> {
  render(<PowerControl />)
  const powerBtn = screen.getByRole('button', { name: '电源' })
  await act(async () => {
    fireEvent.click(powerBtn)
  })
  await screen.findByRole('dialog', { name: '运行时电源' })
}

describe('PowerMenu 统一 Runtime 面板', () => {
  it('Power 按钮打开面板，渲染引擎区 + Studio 后台区', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    await openPowerPanel()
    // 两个分区标题
    expect(screen.getByText('生图引擎')).toBeInTheDocument()
    expect(screen.getByText('Studio 后台')).toBeInTheDocument()
    // 引擎区：本程序托管状态 + 停止/重启
    expect(screen.getByText(/运行中 · 本程序托管/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止引擎' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重启' })).toBeInTheDocument()
    // Studio 后台区：运行中 + 停止全部后台
    expect(screen.getByRole('button', { name: '停止全部后台' })).toBeInTheDocument()
  })

  it('RUNNING_EXTERNAL：引擎区无"停止引擎"/"重启"按钮（外部实例，Studio 不控制）', async () => {
    getMock.mockResolvedValue(rt('RUNNING_EXTERNAL'))
    await openPowerPanel()
    expect(screen.getByText(/运行中 · 外部实例/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止引擎' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重启' })).not.toBeInTheDocument()
    // Studio 后台区仍可停止全部
    expect(screen.getByRole('button', { name: '停止全部后台' })).toBeInTheDocument()
  })

  it('点"停止全部后台"弹确认；点取消：不调 requestShutdown', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    await openPowerPanel()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '停止全部后台' }))
    })
    // 确认框 + 明确文案
    const confirmTitle = await screen.findByRole('heading', { name: '停止全部后台？' })
    expect(confirmTitle).toBeInTheDocument()
    expect(
      screen.getByText(/将停止当前生成、Mobile Review、Studio Backend 和受管 ComfyUI/),
    ).toBeInTheDocument()
    expect(screen.getByText(/未完成任务将在下次启动时按恢复机制处理/)).toBeInTheDocument()
    // 取消
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '取消' }))
    })
    expect(requestShutdownMock).not.toHaveBeenCalled()
  })

  it('确认"停止全部"：调 requestShutdown 恰好一次', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    requestShutdownMock.mockResolvedValue({ accepted: true })
    await openPowerPanel()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '停止全部后台' }))
    })
    await screen.findByRole('heading', { name: '停止全部后台？' })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '停止全部' }))
    })
    expect(requestShutdownMock).toHaveBeenCalledTimes(1)
  })

  it('202 后显示"正在停止…"反馈并引导关闭/刷新', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    requestShutdownMock.mockResolvedValue({ accepted: true })
    await openPowerPanel()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '停止全部后台' }))
    })
    await screen.findByRole('heading', { name: '停止全部后台？' })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '停止全部' }))
    })
    // 反馈出现，且"停止全部后台"按钮被替换
    expect(await screen.findByText(/正在停止…/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止全部后台' })).not.toBeInTheDocument()
  })
})
