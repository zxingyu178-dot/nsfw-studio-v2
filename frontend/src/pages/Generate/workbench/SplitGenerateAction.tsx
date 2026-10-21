/**
 * SplitGenerateAction（v0.15 Task 11）：拆分为左「✦ 生成 N 张」(normal) + 右「⚡」(next 插队)。
 * 不再上下叠放两个大按钮；Gate 判定与 submitGeneration/snapshot 全部沿用 GenerateAction 逻辑。
 */
import { useCallback, useEffect, useState } from 'react'
import { IconStart } from '../../../components/ui/ui3'
import { isImageCapablePrimary, snapshotFromState, useWorkbench } from '../../../stores/workbenchStore'
import { submitGeneration, useJobStore } from '../../../stores/jobStore'
import { shortJobId } from '../../../types/workbench'

export function SplitGenerateAction({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
  const state = useWorkbench()
  const store = useJobStore()
  const [notice, setNotice] = useState<string | null>(null)

  const hasPrompt =
    state.promptMode === 'full'
      ? state.fullPrompt.trim().length > 0
      : Object.values(state.structured).some((value) => value.trim().length > 0)
  const primaryImageCapable = state.mode !== 'image' || isImageCapablePrimary(state)
  const inputImage = state.inputImages[0] ?? null
  const engineOffline = store.engineLoaded && store.engine !== null && !store.engine.online
  const imageGateBlocked = state.mode === 'image' && (imageGenAvailable !== true || !primaryImageCapable)

  const gateReason = store.submitting
    ? undefined
    : engineOffline
      ? 'Engine 离线，无法提交'
      : !hasPrompt
        ? '请先填写 Prompt'
        : imageGateBlocked
          ? imageGenAvailable !== true
            ? '图片生成：尚未配置可用工作流'
            : '图片生成：当前工作流不接受输入图片'
          : state.mode === 'image' && !inputImage
            ? '请先选择输入图片'
            : inputImage?.missing
              ? '输入图片已丢失，请移除后重新选择'
              : undefined

  const disabled = store.submitting || gateReason !== undefined
  const label = state.count > 1 ? `生成 ${state.count} 张` : '生成'

  const handleGenerate = useCallback(async (queueMode: 'normal' | 'next'): Promise<void> => {
    setNotice(null)
    const created = await submitGeneration(snapshotFromState(), queueMode)
    if (!created) return
    if (created.idempotent_replay) {
      setNotice(`相同请求已提交过，已定位到原任务 ${shortJobId(created.id)}`)
    } else {
      setNotice(
        created.disk_space === 'warning'
          ? `已加入队列 ${shortJobId(created.id)}（磁盘空间偏低，建议清理）`
          : `已加入队列 ${shortJobId(created.id)}`,
      )
    }
  }, [])

  // 快捷键：Ctrl+Enter / ⌘+Enter 提交普通生成（不抢占输入框内的 Enter 换行）。
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (!(event.ctrlKey || event.metaKey) || event.key !== 'Enter') return
      event.preventDefault()
      if (disabled) return
      void handleGenerate('normal')
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [disabled, handleGenerate])

  return (
    <div className="wb4-generate">
      {gateReason && (
        <p className="generate-action__gate" role="status">
          {gateReason}
        </p>
      )}
      {store.lastError && (
        <p className="generate-action__msg generate-action__msg--error" role="alert">
          {store.lastError}
        </p>
      )}
      {notice && (
        <p className="generate-action__msg generate-action__msg--ok" role="status">
          {notice}
        </p>
      )}
      <div className="wb4-generate__split" role="group" aria-label="生成操作">
        <button
          type="button"
          className="generate-action wb4-generate__main"
          disabled={disabled}
          title={gateReason ?? '生成（Ctrl+Enter）'}
          aria-keyshortcuts="Control+Enter"
          aria-busy={store.submitting || undefined}
          onClick={() => void handleGenerate('normal')}
        >
          {store.submitting ? (
            <>
              <span className="generate-action__line" aria-hidden="true" />
              <span>提交中…</span>
            </>
          ) : (
            <>
              <span className="generate-action__icon" aria-hidden="true"><IconStart size={16} /></span>
              <span>✦ {label}</span>
            </>
          )}
        </button>
        <button
          type="button"
          className="wb4-generate__next"
          disabled={disabled}
          title="优先生成：插入当前任务之后"
          aria-label="优先生成（插入当前任务之后）"
          onClick={() => void handleGenerate('next')}
        >
          ⚡
        </button>
      </div>
    </div>
  )
}

export default SplitGenerateAction
