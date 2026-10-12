import { Button, Checkbox, Field, Select } from '../../../components/ui'
import { useJobStore } from '../../../stores/jobStore'
import {
  hasUpscaleModule,
  isImageStartModule,
  setCount,
  setPrimaryModule,
  setPrimaryModuleConfig,
  setSeed,
  setSize,
  setUpscaleEnabled,
  useWorkbench,
} from '../../../stores/workbenchStore'
import { MODULE_LABEL } from '../../../types/workbench'
import { AspectRatioPicker } from '../AspectRatioPicker'
import { CollapsibleSection } from './CollapsibleSection'
import { ModuleParameterField } from './ModuleParameterField'

/**
 * 右栏生成配置（Phase 0.12 任务 5.3）：4 组可折叠中的前三组——
 * 工作流（Engine 只读 / Primary Module / 参数 / 高清放大）、画面（画幅 / 分辨率 / 自定义）、
 * 输出（数量 / Seed）。折叠态由 CollapsibleSection 持久化到 localStorage。
 * 主操作（生成 / 优先生成）固定在 Pane 底部 sticky action footer（见 GenerateFooter）。
 */
export function GenerationControls() {
  const state = useWorkbench()

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

  return (
    <>
      {/* ===== 工作流：Engine 只读 / Primary Module / 参数 / 高清放大 ===== */}
      <CollapsibleSection id="workflow" title="工作流">
        <Field label="引擎">
          <EngineState />
        </Field>

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

        {configurableParams.map((param) => (
          <ModuleParameterField
            key={param.name}
            param={param}
            value={state.workflowModules[0]?.config?.[param.name]}
            onChange={(value) => setPrimaryModuleConfig({ [param.name]: value })}
          />
        ))}
      </CollapsibleSection>

      {/* ===== 画面：画幅 / 分辨率 / 自定义 ===== */}
      <CollapsibleSection id="canvas" title="画面">
        {followsInputSize ? (
          <Field label="尺寸"><p className="wb-static">跟随输入图（无需设置宽高）</p></Field>
        ) : (
          <AspectRatioPicker width={state.width} height={state.height} onSizeChange={setSize} />
        )}
      </CollapsibleSection>

      {/* ===== 输出：数量 / Seed ===== */}
      <CollapsibleSection id="output" title="输出">
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
      </CollapsibleSection>
    </>
  )
}

/** Engine 只读状态点（规范 §五十一）。 */
function EngineState() {
  const store = useJobStore()
  return (
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
  )
}
