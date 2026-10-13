import { useCallback, useRef, useState } from 'react'
import { ApiRequestError, systemApi } from '../api/client'
import { Button, ConfirmModal } from './ui'
import { IconButton, IconPower } from './ui/ui3'
import { EngineRuntimeBody } from './EngineControlPopover'
import './PowerMenu.css'

export interface PowerMenuProps {
  onClose: () => void
}

/**
 * 统一 Runtime 面板（Task6 §十一 / Task16 §二十三）：
 *
 * 生图引擎区
 *   ● ComfyUI 运行中
 *   [停止引擎] [重启]        ← 复用 EngineRuntimeBody（保留 v0.13.2 中文状态）
 *
 * Studio 后台区
 *   ● 运行中
 *   [停止全部后台]           ← 先弹确认；确认后 POST /system/request-shutdown
 *
 * 语义边界（§十一）：Queue 的"暂停队列"属调度（在 Generate 内），这里不重复队列控件；
 * 这里的"停止引擎 / 停止全部后台"才是释放资源。RUNNING_EXTERNAL 时引擎区无停止/重启。
 *
 * 自停（§11.2）：前端绝不直接杀进程。POST /request-shutdown 由后端回 202，
 * 再由一次性 detached helper 经官方 lifecycle CLI 停止整套；前端 202 后只给
 * "正在停止…"反馈并引导关闭/刷新。
 */
export function PowerMenu({ onClose }: PowerMenuProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [confirmStopAll, setConfirmStopAll] = useState(false)
  const [shuttingDown, setShuttingDown] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConfirmStopAll = useCallback(async () => {
    setError(null)
    try {
      await systemApi.requestShutdown()
      // 202 Accepted：后端已 detached 拉起停止 helper。前端不杀进程，只给反馈。
      setConfirmStopAll(false)
      setShuttingDown(true)
    } catch (e) {
      // 未拿到 202：保留面板，展示错误，仍可用桌面停止快捷方式兜底
      setConfirmStopAll(false)
      setError(e instanceof ApiRequestError ? e.message : '停止请求失败')
    }
  }, [])

  return (
    <>
      <div
        ref={panelRef}
        className="ep pm"
        role="dialog"
        aria-label="运行时电源"
        tabIndex={-1}
      >
        <div className="pm__section">
          <div className="pm__section-title">生图引擎</div>
          <EngineRuntimeBody
            panelRef={panelRef}
            triggerSelector="[data-power-trigger]"
            onClose={onClose}
          />
        </div>

        <div className="pm__divider" aria-hidden="true" />

        <div className="pm__section">
          <div className="pm__section-title">Studio 后台</div>
          <div className="pm__studio-status">
            <span className="ep__dot ep__dot--ok" aria-hidden="true" />
            运行中
          </div>
          {error && (
            <div className="ep__error" role="alert">
              {error}
            </div>
          )}
          {shuttingDown ? (
            <div className="pm__stopping" role="status">
              正在停止… 请关闭本窗口，或刷新页面确认后台已退出。
            </div>
          ) : (
            <div className="ep__actions">
              <Button variant="danger" size="sm" onClick={() => setConfirmStopAll(true)}>
                停止全部后台
              </Button>
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={confirmStopAll}
        title="停止全部后台？"
        message="将停止当前生成、Mobile Review、Studio Backend 和受管 ComfyUI；未完成任务将在下次启动时按恢复机制处理。"
        confirmText="停止全部"
        cancelText="取消"
        danger
        onConfirm={() => void handleConfirmStopAll()}
        onCancel={() => setConfirmStopAll(false)}
      />
    </>
  )
}

/**
 * TopNav 电源触发器：克制的 icon 按钮（不开大按钮框），点击打开统一 Runtime 面板。
 * 面板触发元素标记 data-power-trigger，供面板内"点击外部关闭"忽略自身。
 */
export function PowerControl() {
  const [open, setOpen] = useState(false)

  return (
    <span className="power-control" data-power-trigger="true">
      <IconButton
        icon={<IconPower size={16} />}
        label="电源"
        tooltip="运行时电源 / 停止全部"
        active={open}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
      />
      {open && <PowerMenu onClose={() => setOpen(false)} />}
    </span>
  )
}
