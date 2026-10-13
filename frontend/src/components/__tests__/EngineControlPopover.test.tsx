import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { EngineControlPopover } from '../EngineControlPopover'
import { EngineStatus } from '../EngineStatus'
import { engineRuntimeApi, jobApi, getHealth } from '../../api/client'
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
    getHealth: vi.fn(),
    subscribeJobEvents: vi.fn(() => () => {}),
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
  }
})

const getMock = engineRuntimeApi.get as Mock
const startMock = engineRuntimeApi.start as Mock
const stopMock = engineRuntimeApi.stop as Mock
const queueMock = jobApi.queue as Mock
const pauseQueueMock = jobApi.pauseQueue as Mock
const healthMock = getHealth as Mock

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

const runningQueue = {
  worker: { running: true, current_job_id: 'job_1' },
  running: { id: 'job_1', status: 'RUNNING' },
  queued: [],
  paused: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  healthMock.mockResolvedValue({ status: 'ok' })
})

afterEach(() => {
  vi.clearAllMocks()
})

function renderPopover() {
  const onClose = vi.fn()
  render(<EngineControlPopover onClose={onClose} />)
  return { onClose }
}

describe('EngineControlPopover 生图引擎控制', () => {
  it('点击顶部 Engine 指示打开 popover（EngineStatus 集成）', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    render(<EngineStatus />)
    const trigger = screen.getByRole('button', { name: /Engine/ })
    await act(async () => {
      fireEvent.click(trigger)
    })
    expect(await screen.findByRole('dialog', { name: '生图引擎控制' })).toBeInTheDocument()
  })

  it('RUNNING_MANAGED 显示"运行中·本程序托管"与停止/重启按钮', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    renderPopover()
    expect(await screen.findByText(/运行中 · 本程序托管/)).toBeInTheDocument()
    expect(screen.getByText('ComfyUI · 8188')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止引擎' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重启' })).toBeInTheDocument()
  })

  it('STOPPED 显示启动按钮，点击调用 engineRuntimeApi.start', async () => {
    getMock
      .mockResolvedValueOnce(rt('STOPPED'))
      .mockResolvedValue(rt('RUNNING_MANAGED'))
    startMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    renderPopover()
    const startBtn = await screen.findByRole('button', { name: '启动生图引擎' })
    await act(async () => {
      fireEvent.click(startBtn)
    })
    expect(startMock).toHaveBeenCalledTimes(1)
  })

  it('停止且无 RUNNING Job：直接调用 stop，不调 pauseQueue', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    queueMock.mockResolvedValue(emptyQueue)
    stopMock.mockResolvedValue(rt('STOPPED'))
    renderPopover()
    const stopBtn = await screen.findByRole('button', { name: '停止引擎' })
    await act(async () => {
      fireEvent.click(stopBtn)
    })
    expect(pauseQueueMock).not.toHaveBeenCalled()
    expect(stopMock).toHaveBeenCalledTimes(1)
  })

  it('停止且有 RUNNING Job：弹确认；确认后先 pauseQueue 再 stop', async () => {
    const callOrder: string[] = []
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    queueMock.mockResolvedValue(runningQueue)
    pauseQueueMock.mockImplementation(async () => {
      callOrder.push('pause')
      return {}
    })
    stopMock.mockImplementation(async () => {
      callOrder.push('stop')
      return rt('STOPPED')
    })
    renderPopover()
    const stopBtn = await screen.findByRole('button', { name: '停止引擎' })
    await act(async () => {
      fireEvent.click(stopBtn)
    })
    // 出现确认对话框
    const confirmBtn = await screen.findByRole('button', { name: '仍然停止' })
    expect(screen.getByText(/当前图片仍在生成/)).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(confirmBtn)
    })
    expect(pauseQueueMock).toHaveBeenCalledTimes(1)
    expect(stopMock).toHaveBeenCalledTimes(1)
    // 严格顺序：先暂停队列，再停引擎
    expect(callOrder).toEqual(['pause', 'stop'])
  })

  it('停止确认对话框中点取消：不调 pauseQueue 也不调 stop', async () => {
    getMock.mockResolvedValue(rt('RUNNING_MANAGED'))
    queueMock.mockResolvedValue(runningQueue)
    renderPopover()
    const stopBtn = await screen.findByRole('button', { name: '停止引擎' })
    await act(async () => {
      fireEvent.click(stopBtn)
    })
    const cancelBtn = await screen.findByRole('button', { name: '取消' })
    await act(async () => {
      fireEvent.click(cancelBtn)
    })
    expect(pauseQueueMock).not.toHaveBeenCalled()
    expect(stopMock).not.toHaveBeenCalled()
  })

  it('RUNNING_EXTERNAL：不显示停止/重启，显示外部实例说明与 tooltip', async () => {
    getMock.mockResolvedValue(rt('RUNNING_EXTERNAL'))
    renderPopover()
    expect(await screen.findByText(/运行中 · 外部实例/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止引擎' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重启' })).not.toBeInTheDocument()
    const note = screen.getByText(/Studio 不控制其停止\/重启，也不会重复拉起/)
    expect(note).toBeInTheDocument()
    // §十一：外部实例带 tooltip 说明 Studio 不控制启停
    expect(note).toHaveAttribute('title', '外部启动的 ComfyUI，Studio 不控制其启停')
  })

  it('PORT_CONFLICT：明确中文提示端口被非 ComfyUI 程序占用，请释放', async () => {
    getMock.mockResolvedValue(rt('PORT_CONFLICT'))
    renderPopover()
    expect(await screen.findByText('端口被占用')).toBeInTheDocument()
    expect(screen.getByText(/8188 已被非 ComfyUI 程序占用，请释放该端口后再启动引擎/)).toBeInTheDocument()
    expect(screen.queryByText(/8189/)).not.toBeInTheDocument()
  })

  it('STARTING：中性"引擎启动中"文案 + 冷启提示，不显示"启动失败"', async () => {
    getMock.mockResolvedValue(rt('STARTING', { detail: '受管 ComfyUI 启动中（冷启约数分钟，可后台等待）' }))
    renderPopover()
    expect(await screen.findByText('引擎启动中')).toBeInTheDocument()
    expect(screen.getByText(/冷启约数分钟/)).toBeInTheDocument()
    expect(screen.queryByText('启动失败')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '启动生图引擎' })).toBeDisabled()
  })

  it('STOPPING：停止/重启按钮均禁用', async () => {
    getMock.mockResolvedValue(rt('STOPPING'))
    renderPopover()
    expect(await screen.findByText('正在停止…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止引擎' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '重启' })).toBeDisabled()
  })
})
