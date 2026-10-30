import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react'
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

export interface EngineRuntimeBodyProps {
  /** 面板容器 ref（焦点进入 + 点击外部判定都基于它） */
  panelRef: RefObject<HTMLDivElement>
  /** 触发元素的选择器：点击外部关闭时忽略它（避免点触发按钮立刻关掉面板） */
  triggerSelector: string
  onClose: () => void
}

/**
 * 生图引擎运行时控制体（保留 v0.13.2 全部中文状态文案）：
 * - 打开即 GET /engine/runtime，停留期间每 3s 轮询；
 * - 按 7 种 state 渲染启停控件；
 * - 停止/重启前先查队列：有 RUNNING Job 时弹确认，确认后【先 pauseQueue 再 stop/restart】；
 * - RUNNING_EXTERNAL 不提供停止/重启按钮（后端会 409 ENGINE_NOT_OWNED）。
 *
 * 由 EngineControlPopover（独立引擎面板）与 PowerMenu（统一 Runtime 面板）复用，
 * 不在此渲染外层定位容器，只输出引擎区段内容 + 引擎停止/重启确认框。
 */
export function EngineRuntimeBody({ panelRef, triggerSelector, onClose }: EngineRuntimeBodyProps) {
  const [runtime, setRuntime] = useState<EngineRuntimeDTO | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)
  const actingRef = useRef(false)
  const pollGeneration = useRef(0)
  const [confirmAction, setConfirmAction] = useState<'stop' | 'restart' | null>(null)

  // 焦点管理：打开时进入面板，关闭后回到触发元素
  useFocusGuard(true, panelRef)

  // 只在可见时观察；慢请求不叠加，动作期间由动作回执负责刷新。
  useEffect(() => {
    let cancelled = false
    let inFlight = false
    const load = async () => {
      if (cancelled || inFlight || actingRef.current || document.visibilityState === 'hidden') return
      inFlight = true
      const generation = pollGeneration.current
      try {
        const rt = await refreshRuntime()
        if (!cancelled && !actingRef.current && generation === pollGeneration.current && rt) setRuntime(rt)
      } finally { inFlight = false }
    }
    const onVisibility = () => { void load() }
    void load()
    const timer = window.setInterval(load, 10000)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
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
      if (target.closest(triggerSelector)) return
      onClose()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [onClose, panelRef, triggerSelector])

  const failMessage = useCallback((e: unknown): string => {
    return e instanceof ApiRequestError ? e.message : '操作失败'
  }, [])

  const handleStart = useCallback(async () => {
    actingRef.current = true
    pollGeneration.current += 1
    setActing(true)
    setError(null)
    try {
      await engineRuntimeApi.start()
      await settleAfterAction(setRuntime)
    } catch (e) {
      setError(failMessage(e))
    } finally {
      actingRef.current = false
      pollGeneration.current += 1
      setActing(false)
    }
  }, [failMessage])

  const runStop = useCallback(
    async (withPause: boolean) => {
      actingRef.current = true
      pollGeneration.current += 1
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
        actingRef.current = false
        pollGeneration.current += 1
        setActing(false)
        setConfirmAction(null)
      }
    },
    [failMessage],
  )

  const runRestart = useCallback(
    async (withPause: boolean) => {
      actingRef.current = true
      pollGeneration.current += 1
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
        actingRef.current = false
        pollGeneration.current += 1
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
        运行中 · 本程序托管
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
    // 冷启是正常过渡态：中性文案 + 后端 detail（冷启约数分钟），绝不报"启动失败"
    header = (
      <div className="ep__title">
        <span className="ep__dot ep__dot--busy" aria-hidden="true" />
        引擎启动中
      </div>
    )
    note = (
      <div className="ep__note">
        {runtime?.detail ?? '冷启约需数分钟，可在后台等待，无需重复点击启动。'}
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
        运行中 · 外部实例
      </div>
    )
    note = (
      <div
        className="ep__note"
        title="外部启动的 ComfyUI，Studio 不控制其启停"
      >
        当前 ComfyUI 不是由 Studio 启动（{port}），Studio 不控制其停止/重启，也不会重复拉起。
      </div>
    )
  } else if (state === 'PORT_CONFLICT') {
    header = (
      <div className="ep__title ep__title--warn">
        <span className="ep__dot ep__dot--warn" aria-hidden="true" />
        端口被占用
      </div>
    )
    note = (
      <div className="ep__note">
        {port} 已被非 ComfyUI 程序占用，请释放该端口后再启动引擎。
        {runtime?.detail ? `（${runtime.detail}）` : ''}
      </div>
    )
  } else if (state === 'ERROR') {
    header = (
      <div className="ep__title ep__title--warn">
        <span className="ep__dot ep__dot--warn" aria-hidden="true" />
        启动失败
      </div>
    )
    note = (
      <div className="ep__note">
        {runtime?.detail ?? '受管 ComfyUI 启动失败'}
        {runtime?.log_location ? ` 日志：${runtime.log_location}` : ''}
      </div>
    )
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
      <div className="ep__inner">
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

/**
 * 生图引擎控制 Popover（Task4）：仅渲染生图引擎区段的独立浮层面板。
 * 统一 Runtime 面板见 PowerMenu（复用同一 EngineRuntimeBody）。
 */
export function EngineControlPopover({ onClose }: EngineControlPopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  return (
    <div
      ref={panelRef}
      className="ep"
      role="dialog"
      aria-label="生图引擎控制"
      tabIndex={-1}
    >
      <EngineRuntimeBody
        panelRef={panelRef}
        triggerSelector="[data-engine-trigger]"
        onClose={onClose}
      />
    </div>
  )
}
