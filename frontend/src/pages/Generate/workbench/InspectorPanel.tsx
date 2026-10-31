/**
 * InspectorPanel 4.0（v0.15 Task 10）：右栏只负责「怎么生成」。
 * 移除 EngineState（→ TopNav Power）、CurrentJobCard / QueuePanel（→ TaskDock）。
 * 顺序：Workflow（PopoverSelect 卡片，不可用就地 warning）→ Ratio/Resolution（紧凑）→
 * Count（NumberStepper）→ Seed（Random/Fixed）→ Upscale（Switch 行 + 副标）→ Advanced 折叠。
 * 底部固定 SplitGenerateAction（左 生成 N 张 / 右 ⚡ 插队）。
 */
import { Field, Switch } from '../../../components/ui'
import { IconButton, IconChevronDown, IconClose, IconRandom, IconSeed, NumberStepper, PopoverSelect } from '../../../components/ui/ui3'
import {
  hasUpscaleModule,
  imagePrimaryCandidates,
  releaseStatusNotice,
  setCount,
  setPrimaryModule,
  setPrimaryModuleConfig,
  setSeed,
  setSize,
  setUpscaleEnabled,
  textPrimaryCandidates,
  useWorkbench,
} from '../../../stores/workbenchStore'
import { MODULE_LABEL } from '../../../types/workbench'
import { AspectRatioPicker } from '../AspectRatioPicker'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { ModuleParameterField } from '../components/ModuleParameterField'
import { Pane } from '../Pane'
import { SplitGenerateAction } from './SplitGenerateAction'

export function InspectorPanel({
  imageGenAvailable,
  onCollapse,
}: {
  imageGenAvailable: boolean | null
  onCollapse?: () => void
}) {
  const state = useWorkbench()

  const upscaleEnabled = hasUpscaleModule(state.workflowModules)
  const primaryModule = state.workflowModules[0]?.module_id ?? ''
  const primaryCapabilities =
    state.moduleCatalog.find((module) => module.module_id === primaryModule) ?? null
  const primaryTitle =
    (primaryCapabilities?.title ?? MODULE_LABEL[primaryModule] ?? primaryModule) || '工作流'
  // W1.2：文生图与图片生成使用各自的能力候选（process 与 generate 不混用）
  const primaryCandidates =
    state.mode === 'text'
      ? textPrimaryCandidates(state.moduleCatalog)
      : imagePrimaryCandidates(state.moduleCatalog)
  const primaryReleaseNotice = primaryCapabilities ? releaseStatusNotice(primaryCapabilities) : null
  const configurableParams = (primaryCapabilities?.parameters ?? []).filter((param) => param.configurable)
  const followsInputSize = primaryCapabilities?.size_mode === 'input'

  return (
    <Pane
      title="参数"
      actions={
        onCollapse ? (
          <IconButton
            icon={<IconChevronDown size={14} className="wb-pane__collapse-icon wb-pane__collapse-icon--right" />}
            label="收起参数栏"
            onClick={onCollapse}
          />
        ) : undefined
      }
      footer={<SplitGenerateAction imageGenAvailable={imageGenAvailable} />}
    >
      {/* ===== 工作流 ===== */}
      <div className="wb4-inspector__group">
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
            <p className="wb-static wb4-workflow-title">{primaryTitle}</p>
          )}
          {primaryReleaseNotice && (
            <p className="ds-notice" role="status">
              {primaryReleaseNotice}
            </p>
          )}
          {state.mode === 'text' && primaryCandidates.length === 0 && (
            <p className="ds-notice ds-notice--warning" role="alert">
              当前没有可用的文生图工作流，请检查 Engine 与模型绑定。
            </p>
          )}
        </div>

        <div className="wb4-switch-row">
          <div className="wb4-switch-row__text">
            <span className="wb4-switch-row__label">高清放大</span>
            <span className="wb4-switch-row__sub">原图全部完成后处理</span>
          </div>
          <Switch
            checked={upscaleEnabled}
            onChange={(event) => setUpscaleEnabled(event.target.checked)}
            aria-label="高清放大"
          />
        </div>
      </div>

      {/* ===== 画面（画幅 / 分辨率 / 自定义） ===== */}
      {followsInputSize ? (
        <Field label="尺寸"><p className="wb-static">跟随输入图（无需设置宽高）</p></Field>
      ) : (
        <AspectRatioPicker width={state.width} height={state.height} onSizeChange={setSize} />
      )}

      {/* ===== 数量 ===== */}
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

      {/* ===== Seed ===== */}
      <SeedRow />

      {/* ===== 高级参数（默认折叠） ===== */}
      {configurableParams.length > 0 && (
        <CollapsibleSection id="advanced" title="高级参数" defaultOpen={false}>
          {configurableParams.map((param) => (
            <ModuleParameterField
              key={param.name}
              param={param}
              value={state.workflowModules[0]?.config?.[param.name]}
              onChange={(value) => setPrimaryModuleConfig({ [param.name]: value })}
            />
          ))}
        </CollapsibleSection>
      )}
    </Pane>
  )
}

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

export default InspectorPanel
