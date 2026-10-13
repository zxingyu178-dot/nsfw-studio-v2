import { useState } from 'react'
import { ActionButton, IconStart } from '../../../components/ui/ui3'
import { isImageCapablePrimary, snapshotFromState, useWorkbench } from '../../../stores/workbenchStore'
import { submitGeneration, useJobStore } from '../../../stores/jobStore'
import { shortJobId } from '../../../types/workbench'

/**
 * GenerateAction —— Generate 专属主生成按钮（UI 3.0，不放进 ui3）。
 *
 * 规格（任务书 §二十）：
 * - 高度 44~48（46），轻微 accent gradient / glow edge，不夸张；
 * - hover / pressed / loading 明确；
 * - loading 用细线进度图标，不用浏览器 spinner；
 * - disabled 不只透明，还显示 Gate 原因（可见 caption + title）；
 * - 文案随数量：count>1 显示「生成 N 张」，count=1 显示「生成」；
 * - 次级动作「优先生成（插队）」。
 *
 * 业务不变：Gate 判定、submitGeneration、snapshot 全部沿用 store/API。
 */
export function GenerateAction({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
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
    <div className="generate-action__wrap">
      {gateReason && (
        <p className="generate-action__gate" role="status">
          {gateReason}
        </p>
      )}
      {store.lastError && (
        <p className="generate-action__msg generate-action__msg--error" role="alert">{store.lastError}</p>
      )}
      {notice && (
        <p className="generate-action__msg generate-action__msg--ok" role="status">{notice}</p>
      )}
      <button
        type="button"
        className="generate-action"
        disabled={disabled}
        title={gateReason ?? undefined}
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
            <span>{label}</span>
          </>
        )}
      </button>
      <ActionButton
        className="generate-action__secondary"
        disabled={disabled}
        onClick={() => void handleGenerate('next')}
      >
        优先生成（插队）
      </ActionButton>
    </div>
  )
}

export default GenerateAction
