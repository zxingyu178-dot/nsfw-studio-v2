import { Checkbox, Field } from '../../../components/ui'
import { IconButton, IconClose, IconRandom, IconSeed, NumberStepper, PopoverSelect } from '../../../components/ui/ui3'
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
 * 右栏 Parameter Console（UI 3.0）：
 * - Workflow：PopoverSelect（禁止原生 <select>）；
 * - 画面：画幅 ChoiceTile / 分辨率 segmented（见 AspectRatioPicker）；
 * - 数量：NumberStepper + 快捷 chips（保留 1–64 自由输入与钳制）；
 * - Seed：一行，Random 状态 / Fixed·数值 + 清除。
 * 不改业务：WorkbenchStore / Job API / Seed 规则全部沿用。
 */
export function GenerationControls() {
  const state = useWorkbench()

  const upscaleEnabled = hasUpscaleModule(state.workflowModules)
  const primaryModule = state.workflowModules[0]?.module_id ?? 'basic_generate'
  const primaryCapabilities =
    state.moduleCatalog.find((module) => module.module_id === primaryModule) ?? null
  const primaryTitle =
    primaryCapabilities?.title ?? MODULE_LABEL[primaryModule] ?? primaryModule
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
      {/* ===== 工作流 ===== */}
      <CollapsibleSection id="workflow" title="工作流">
        <div className="wb-param">
          <span className="wb-param__label">引擎</span>
          <EngineState />
        </div>

        <div className="wb-param">
          <span className="wb-param__label">工作流</span>
          {primaryCandidates.length > 1 ? (
            <PopoverSelect
              value={primaryModule}
              onChange={(v) => setPrimaryModule(v)}
              ariaLabel="工作流"
              options={primaryCandidates.map((module) => ({
                value: module.module_id,
                label: module.title || MODULE_LABEL[module.module_id] || module.module_id,
              }))}
            />
          ) : (
            <p className="wb-static">① {primaryTitle}</p>
          )}
        </div>

        <Checkbox
          checked={upscaleEnabled}
          onChange={(event) => setUpscaleEnabled(event.target.checked)}
          label="② 高清放大"
        />

        {configurableParams.map((param) => (
          <ModuleParameterField
            key={param.name}
            param={param}
            value={state.workflowModules[0]?.config?.[param.name]}
            onChange={(value) => setPrimaryModuleConfig({ [param.name]: value })}
          />
        ))}
      </CollapsibleSection>

      {/* ===== 画面 ===== */}
      <CollapsibleSection id="canvas" title="画面">
        {followsInputSize ? (
          <Field label="尺寸"><p className="wb-static">跟随输入图（无需设置宽高）</p></Field>
        ) : (
          <AspectRatioPicker width={state.width} height={state.height} onSizeChange={setSize} />
        )}
      </CollapsibleSection>

      {/* ===== 输出 ===== */}
      <CollapsibleSection id="output" title="输出">
        <div className="wb-param">
          <span className="wb-param__label">数量</span>
          <NumberStepper
            value={state.count}
            onChange={(v) => setCount(v)}
            min={1}
            max={64}
            chips={[1, 2, 4, 6, 8]}
            ariaLabel="数量"
          />
          <span className="wb-param__label">1–64 张</span>
        </div>

        <SeedRow />
      </CollapsibleSection>
    </>
  )
}

/** Seed 一行：Random 状态 / Fixed·数值 + 清除（不改 Seed 规则）。 */
function SeedRow() {
  const state = useWorkbench()
  const fixed = state.seedMode === 'fixed' && state.seed !== null

  return (
    <div className="wb-param">
      <span className="wb-param__label">Seed</span>
      <div className="wb-seed-row">
        {fixed ? (
          <>
            <IconSeed size={16} />
            <span className="wb-seed-value">Fixed · {state.seed}</span>
            <IconButton icon={<IconClose size={14} />} label="恢复随机" onClick={() => setSeed(null)} />
          </>
        ) : (
          <>
            <IconRandom size={16} />
            <span className="wb-static">随机（每张独立）</span>
          </>
        )}
      </div>
    </div>
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
