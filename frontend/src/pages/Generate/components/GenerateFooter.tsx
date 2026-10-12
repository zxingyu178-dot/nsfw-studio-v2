import { useState } from 'react'
import { Button } from '../../../components/ui'
import { isImageCapablePrimary, snapshotFromState, useWorkbench } from '../../../stores/workbenchStore'
import { submitGeneration, useJobStore } from '../../../stores/jobStore'
import { shortJobId } from '../../../types/workbench'

/**
 * 右栏 sticky action footer（Phase 0.12 任务 5.3）：
 * 无论用户滚动到右栏何处，“生成 / 优先生成”主操作始终可见。
 * 同时承载图片生成 Gate 警告、提交错误与成功反馈。
 */
export function GenerateFooter({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
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
  const generateHint = store.submitting
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
  const disabled = store.submitting || generateHint !== undefined

  async function handleGenerate(queueMode: 'normal' | 'next'): Promise<void> {
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
  }

  return (
    <div className="wb-action-footer">
      {imageGateBlocked && (
        <p className="ds-notice ds-notice--warning wb-action-footer__gate">
          {imageGenAvailable !== true
            ? '图片生成：尚未配置可用工作流（等待模型方案确认）。可先选择输入图片并保存配方。'
            : '图片生成：当前工作流不接受输入图片，请切换到可用的图片生成工作流（如“图生图”）。'}
        </p>
      )}
      {store.lastError && (
        <p className="ds-notice ds-notice--error wb-action-footer__msg" role="alert">{store.lastError}</p>
      )}
      {notice && (
        <p className="ds-notice ds-notice--success wb-action-footer__msg" role="status">{notice}</p>
      )}
      <div className="wb-actions">
        <Button
          variant="primary" size="lg" className="wb-actions__main"
          disabled={disabled} title={generateHint}
          onClick={() => void handleGenerate('normal')}
        >
          {store.submitting ? '提交中…' : '生成'}
        </Button>
        <Button
          variant="secondary" size="sm"
          disabled={disabled} title={generateHint}
          onClick={() => void handleGenerate('next')}
        >
          优先生成（插队）
        </Button>
      </div>
    </div>
  )
}
