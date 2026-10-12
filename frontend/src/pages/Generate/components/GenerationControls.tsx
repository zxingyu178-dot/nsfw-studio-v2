import { useState } from 'react'
import { Button, Checkbox, Field, Select } from '../../../components/ui'
import {
  hasUpscaleModule,
  isImageCapablePrimary,
  isImageStartModule,
  setCount,
  setPrimaryModule,
  setPrimaryModuleConfig,
  setSeed,
  setSize,
  setUpscaleEnabled,
  snapshotFromState,
  useWorkbench,
} from '../../../stores/workbenchStore'
import { submitGeneration, useJobStore } from '../../../stores/jobStore'
import { MODULE_LABEL, shortJobId } from '../../../types/workbench'
import { AspectRatioPicker } from '../AspectRatioPicker'
import { ModuleParameterField } from './ModuleParameterField'

/**
 * 生成控制区（规范 §五十一、§五十三）：真实 Engine 状态 / Primary Module / 模块参数 /
 * 尺寸 / 数量 / Seed / 主操作按钮 / 提交反馈。
 * 从 SettingsPane.tsx 纯拆分（Phase 0.12 任务 9：只重构，不改行为 / API）。
 */
export function GenerationControls({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
  const state = useWorkbench()
  const store = useJobStore()
  const [notice, setNotice] = useState<string | null>(null)

  const hasPrompt =
    state.promptMode === 'full'
      ? state.fullPrompt.trim().length > 0
      : Object.values(state.structured).some((value) => value.trim().length > 0)
  const upscaleEnabled = hasUpscaleModule(state.workflowModules)
  const primaryModule = state.workflowModules[0]?.module_id ?? 'basic_generate'
  const primaryCapabilities =
    state.moduleCatalog.find((module) => module.module_id === primaryModule) ?? null
  const primaryTitle =
    primaryCapabilities?.title ?? MODULE_LABEL[primaryModule] ?? primaryModule
  // §21：图片条件 Primary 用能力判断 isImageStartModule（不再用 output_kind==='processed' 猜）
  const primaryCandidates = state.moduleCatalog.filter((module) =>
    state.mode === 'text'
      ? module.available && !module.input_required
      : isImageStartModule(module),
  )
  const configurableParams = (primaryCapabilities?.parameters ?? []).filter(
    (param) => param.configurable,
  )
  const followsInputSize = primaryCapabilities?.size_mode === 'input'
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
    <>
      {/* ===== 真实 Engine 状态 ===== */}
      <Field label="引擎">
        <span
          className={`engine-state engine-state--${
            store.engineLoaded ? (store.engine?.online ? 'online' : 'offline') : 'checking'
          }`}
          title={store.engine?.detail}
        >
          <span className="engine-state__dot" aria-hidden="true" />
          {store.engine?.online
            ? `${store.engine.engine_name} ${store.engine.engine_version}`
            : store.engineLoaded
              ? '离线'
              : '检测中'}
        </span>
      </Field>

      {/* ===== 工作流 ===== */}
      <Field label="工作流">
        {primaryCandidates.length > 1 ? (
          <Select
            id="primary-module"
            value={primaryModule}
            onChange={(event) => setPrimaryModule(event.target.value)}
            options={primaryCandidates.map((module) => ({
              value: module.module_id,
              label: module.title || MODULE_LABEL[module.module_id] || module.module_id,
            }))}
          />
        ) : (
          <p className="wb-static">① {primaryTitle}</p>
        )}
        <Checkbox
          checked={upscaleEnabled}
          onChange={(event) => setUpscaleEnabled(event.target.checked)}
          label="② 高清放大"
        />
        {upscaleEnabled && (
          <p className="muted">原图全部完成后，依次生成高清图（原图与高清保持父子关系）。</p>
        )}
      </Field>

      {/* ===== 模块参数 ===== */}
      {configurableParams.map((param) => (
        <ModuleParameterField
          key={param.name}
          param={param}
          value={state.workflowModules[0]?.config?.[param.name]}
          onChange={(value) => setPrimaryModuleConfig({ [param.name]: value })}
        />
      ))}

      {/* ===== 尺寸（画幅 + 分辨率预设） ===== */}
      {followsInputSize ? (
        <Field label="尺寸"><p className="wb-static">跟随输入图（无需设置宽高）</p></Field>
      ) : (
        <AspectRatioPicker width={state.width} height={state.height} onSizeChange={setSize} />
      )}

      <Field label="数量">
        <Select
          value={state.count}
          onChange={(event) => setCount(Number(event.target.value))}
          options={[1, 2, 4, 6, 8].map((n) => ({ value: n, label: String(n) }))}
        />
      </Field>

      <Field label="Seed">
        {state.seedMode === 'fixed' && state.seed !== null ? (
          <p className="wb-static">
            固定 {state.seed}
            <span className="muted">（单张精确复现；选择数量 &gt; 1 将自动切回随机）</span>
            <Button size="xs" variant="ghost" onClick={() => setSeed(null)}>恢复随机</Button>
          </p>
        ) : (
          <p className="wb-static">随机（每张独立）</p>
        )}
      </Field>

      {imageGateBlocked && (
        <p className="ds-notice ds-notice--warning">
          {imageGenAvailable !== true
            ? '图片生成：尚未配置可用工作流（等待模型方案确认）。可先选择输入图片并保存配方。'
            : '图片生成：当前工作流不接受输入图片，请切换到可用的图片生成工作流（如“图生图”）。'}
        </p>
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

      {store.lastError && <p className="ds-notice ds-notice--error" role="alert">{store.lastError}</p>}
      {notice && <p className="ds-notice ds-notice--success" role="status">{notice}</p>}
    </>
  )
}
