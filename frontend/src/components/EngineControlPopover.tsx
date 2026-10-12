import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiRequestError, engineRuntimeApi, jobApi } from '../api/client'
import type { EngineRuntimeDTO, EngineRuntimeState } from '../types/workbench'
import { Button, ConfirmModal } from './ui'
import { useFocusGuard } from './ui/useOverlay'
import './EngineControlPopover.css'

interface EngineControlPopoverProps {
  onClose: () => void
}

/** 启动中 / 停止中属于"过渡态"，动作后需要轮询直到离开这两个状态 */
const BUSY_STATES: ReadonlySet<EngineRuntimeState> = new Set(['STARTING', 'STOPPING'])

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function refreshRuntime(): Promise<EngineRuntimeDTO | null> {
  try {
    return await engineRuntimeApi.get()
  } catch {
    return null
  }
}

/** 动作后轮询，直到状态离开 STARTING/STOPPING（最多 ~30s） */
async function settleAfterAction(
  onState: (rt: EngineRuntimeDTO) => void,
): Promise<void> {
  for (let i = 0; i < 30; i += 1) {
    const rt = await refreshRuntime()
    if (rt) {
      onState(rt)
      if (!BUSY_STATES.has(rt.state)) return
    }
    await delay(1000)
  }
}

/**
 * 生图引擎控制 Popover（计划 Task4）：
 * - 打开即 GET /engine/runtime，停留期间每 3s 轮询；
 * - 按 7 种 state 渲染启停控件；
 * - 停止/重启前先查队列：有 RUNNING Job 时弹确认，确认后【先 pauseQueue 再 stop/restart】；
 * - RUNNING_EXTERNAL 不提供停止/重启按钮（后端会 409 ENGINE_NOT_OWNED）；
 * - ESC / 点击外部关闭；焦点进入面板、关闭后回到触发元素。
 */
export function EngineControlPopover({ onClose }: EngineControlPopoverProps) {
  const [runtime, setRuntime] = useState<EngineRuntimeDTO | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)
  const [confirmAction, setConfirmAction] = useState<'stop' | 'restart' | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // 焦点管理：打开时进入面板，关闭时回到触发元素
  useFocusGuard(true, panelRef)

  // 打开即拉取 + 每 3s 轮询
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const rt = await refreshRuntime()
      if (!cancelled && rt) setRuntime(rt)
    }
    void load()
    const timer = window.setInterval(load, 3000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  // ESC 关闭
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])

  // 点击外部关闭（忽略触发按钮与面板自身）
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null
      if (!target) return
      if (panelRef.current?.contains(target)) return
      if (target.closest('[data-engine-trigger]')) return
      onClose()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [onClose])

  const failMessage = useCallback((e: unknown): string => {
    return e instanceof ApiRequestError ? e.message : '操作失败'
  }, [])

  const handleStart = useCallback(async () => {
    setActing(true)
    setError(null)
    try {
      await engineRuntimeApi.start()
      await settleAfterAction(setRuntime)
    } catch (e) {
      setError(failMessage(e))
    } finally {
      setActing(false)
    }
  }, [failMessage])

  const runStop = useCallback(
    async (withPause: boolean) => {
      setActing(true)
      setError(null)
      try {
        // 严格顺序：先暂停队列，再停引擎
        if (withPause) await jobApi.pauseQueue()
        await engineRuntimeApi.stop()
        await settleAfterAction(setRuntime)
      } catch (e) {
        setError(failMessage(e))
      } finally {
        setActing(false)
        setConfirmAction(null)
      }
    },
    [failMessage],
  )

  const runRestart = useCallback(
    async (withPause: boolean) => {
      setActing(true)
      setError(null)
      try {
        if (withPause) await jobApi.pauseQueue()
        await engineRuntimeApi.stop()
        // 等 owned 引擎消失（health 不再在线 / 离开 STOPPING）
        for (let i = 0; i < 60; i += 1) {
          const rt = await refreshRuntime()
          if (rt) {
            setRuntime(rt)
            if (!BUSY_STATES.has(rt.state)) break
          }
          await delay(1000)
        }
        await engineRuntimeApi.start()
        await settleAfterAction(setRuntime)
      } catch (e) {
        setError(failMessage(e))
      } finally {
        setActing(false)
        setConfirmAction(null)
      }
    },
    [failMessage],
  )

  /** 停止/重启入口：先查队列是否有 RUNNING Job，有则弹确认 */
  const requestStopOrRestart = useCallback(
    async (action: 'stop' | 'restart') => {
      if (acting) return
      setError(null)
      try {
        const queue = await jobApi.queue()
        if (queue.running) {
          setConfirmAction(action)
          return
        }
      } catch {
        // 队列查询失败：按无 RUNNING Job 处理，直接动作
      }
      if (action === 'stop') void runStop(false)
      else void runRestart(false)
    },
    [acting, runRestart, runStop],
  )

  const handleConfirm = useCallback(() => {
    const action = confirmAction
    setConfirmAction(null)
    if (action === 'restart') void runRestart(true)
    else void runStop(true)
  }, [confirmAction, runRestart, runStop])

  const handleCancelConfirm = useCallback(() => {
    setConfirmAction(null)
  }, [])

  const state = runtime?.state
  const port = runtime?.port ?? 8188

  let header: ReactNode = null
  let actions: ReactNode = null
  let note: ReactNode = null

  if (state === 'RUNNING_MANAGED') {
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--ok" aria-hidden="true" />
        已运行
      </div>
    )
    note = <div className="ep__sub">ComfyUI · {port}</div>
    actions = (
      <div className="ep__actions">
        <Button
          variant="danger"
          size="sm"
          loading={acting}
          onClick={() => void requestStopOrRestart('stop')}
        >
          停止引擎
        </Button>
        <Button
          variant="secondary"
          size="sm"
          loading={acting}
          onClick={() => void requestStopOrRestart('restart')}
        >
          重启
        </Button>
      </div>
    )
  } else if (state === 'STOPPED') {
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--off" aria-hidden="true" />
        已停止
      </div>
    )
    actions = (
      <div className="ep__actions">
        <Button variant="primary" size="sm" loading={acting} onClick={() => void handleStart()}>
          启动生图引擎
        </Button>
      </div>
    )
  } else if (state === 'STARTING') {
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--busy" aria-hidden="true" />
        正在启动…
      </div>
    )
    actions = (
      <div className="ep__actions">
        <Button variant="primary" size="sm" disabled>
          启动生图引擎
        </Button>
      </div>
    )
  } else if (state === 'STOPPING') {
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--busy" aria-hidden="true" />
        正在停止…
      </div>
    )
    actions = (
      <div className="ep__actions">
        <Button variant="danger" size="sm" disabled>
          停止引擎
        </Button>
        <Button variant="secondary" size="sm" disabled>
          重启
        </Button>
      </div>
    )
  } else if (state === 'RUNNING_EXTERNAL') {
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--ok" aria-hidden="true" />
        外部 ComfyUI · {port}
      </div>
    )
    note = (
      <div className="ep__note">
        当前 ComfyUI 不是由 Studio 启动，不能从这里停止或重启。
      </div>
    )
  } else if (state === 'PORT_CONFLICT') {
    header = (
      <div className="ep__title ep__title--warn">
        <span className="ep__dot ep__dot--warn" aria-hidden="true" />
        端口冲突
      </div>
    )
    note = <div className="ep__sub">{port} 已被其他程序占用</div>
  } else if (state === 'ERROR') {
    header = (
      <div className="ep__title ep__title--warn">
        <span className="ep__dot ep__dot--warn" aria-hidden="true" />
        启动失败
      </div>
    )
    note = runtime?.detail ? <div className="ep__note">{runtime.detail}</div> : null
    actions = (
      <div className="ep__actions">
        <Button variant="primary" size="sm" loading={acting} onClick={() => void handleStart()}>
          启动生图引擎
        </Button>
      </div>
    )
  } else {
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--busy" aria-hidden="true" />
        检测引擎状态…
      </div>
    )
  }

  return (
    <>
      <div
        ref={panelRef}
        className="ep"
        role="dialog"
        aria-label="生图引擎控制"
        tabIndex={-1}
      >
        <div className="ep__header">{header}</div>
        {note}
        {actions}
        {error && <div className="ep__error" role="alert">{error}</div>}
      </div>
      <ConfirmModal
        open={confirmAction !== null}
        title="停止生图引擎？"
        message="当前图片仍在生成。停止引擎会中断当前图片，并暂停后续队列。"
        confirmText="仍然停止"
        cancelText="取消"
        danger
        onConfirm={handleConfirm}
        onCancel={handleCancelConfirm}
      />
    </>
  )
}
