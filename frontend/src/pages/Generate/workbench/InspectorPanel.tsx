/**
 * InspectorPanel 4.0（v0.15 Task 10）：右栏只负责「怎么生成」。
 * 移除 EngineState（→ TopNav Power）、CurrentJobCard / QueuePanel（→ TaskDock）。
 * 顺序：Workflow（PopoverSelect 卡片，不可用就地 warning）→ Ratio/Resolution（紧凑）→
 * Count（NumberStepper）→ Seed（Random/Fixed）→ 运行环境 → Advanced 折叠。
 * 底部固定 SplitGenerateAction（左 生成 N 张 / 右 ⚡ 插队）。
 */
import { useEffect, useState } from 'react'
import { Field } from '../../../components/ui'
import { IconButton, IconChevronDown, IconClose, IconRandom, IconRestart, IconSeed, NumberStepper, PopoverSelect } from '../../../components/ui/ui3'
import { engineRuntimeApi } from '../../../api/client'
import type { EngineModelsDTO, EngineSamplingProfileDTO } from '../../../api/client'
import type { RuntimePreflightDTO, RuntimePreflightStatus } from '../../../types/workbench'
import {
  defaultWorkflowNotice,
  imagePrimaryCandidates,
  releaseStatusNotice,
  setCount,
  setPrimaryModule,
  setPrimaryModuleConfig,
  setSeed,
  setSize,
  textPrimaryCandidates,
  useWorkbench,
} from '../../../stores/workbenchStore'
import { MODULE_LABEL } from '../../../types/workbench'
import { AspectRatioPicker } from '../AspectRatioPicker'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { ModuleParameterField } from '../components/ModuleParameterField'
import { Pane } from '../Pane'
import { LoraStackEditor } from './LoraStackEditor'
import type { LoraEntry } from './LoraStackEditor'
import { SplitGenerateAction } from './SplitGenerateAction'

/** W2.0：preflight 状态中文化；括号内保留原始状态码，便于排查。 */
const PREFLIGHT_LABELS: Record<RuntimePreflightStatus, string> = {
  READY: '就绪',
  BLOCKED: '未就绪',
  UNKNOWN: '未知',
}

export function InspectorPanel({
  imageGenAvailable,
  onCollapse,
}: {
  imageGenAvailable: boolean | null
  onCollapse?: () => void
}) {
  const state = useWorkbench()

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
  // W1.2.1：默认工作流不可用时明确提示（未选定 Primary 才提示；用户显式选择后保留其选择）
  const defaultNotice =
    state.mode === 'text' && primaryModule === ''
      ? defaultWorkflowNotice(state.moduleCatalog)
      : null
  const configurableParams = (primaryCapabilities?.parameters ?? []).filter((param) => param.configurable)
  const followsInputSize = primaryCapabilities?.size_mode === 'input'
  const modelParam = configurableParams.find((param) => param.name === 'model') ?? null
  const faceDetailerParam = configurableParams.find((param) => param.name === 'face_detailer') ?? null
  const advancedParams = configurableParams.filter(
    (param) => param.name !== 'model' && param.name !== 'face_detailer',
  )
  const supportsLora = (primaryCapabilities?.parameters ?? []).some((param) => param.name === 'loras')
  const primaryConfig = state.workflowModules[0]?.config ?? {}
  const selectedModel = typeof primaryConfig.model === 'string' ? primaryConfig.model : ''
  const selectedLoras: LoraEntry[] = Array.isArray(primaryConfig.loras)
    ? (primaryConfig.loras as LoraEntry[]).filter(
        (item) => item && typeof item.name === 'string' && item.name,
      )
    : []

  // 模型 / LoRA 候选：引擎离线时为空数组，不影响其他参数编辑。
  const [engineModels, setEngineModels] = useState<EngineModelsDTO>({ checkpoints: [], loras: [] })
  const [engineModelsState, setEngineModelsState] = useState<'loading' | 'ready' | 'offline'>('loading')
  const [modelsRefreshKey, setModelsRefreshKey] = useState(0)
  useEffect(() => {
    const models = (engineRuntimeApi as { models?: () => Promise<EngineModelsDTO> }).models
    if (typeof models !== 'function') { setEngineModelsState('offline'); return }
    let cancelled = false
    setEngineModelsState('loading')
    models()
      .then((result) => {
        if (cancelled) return
        setEngineModels(result)
        setEngineModelsState('ready')
      })
      .catch(() => {
        if (cancelled) return
        setEngineModels({ checkpoints: [], loras: [] })
        setEngineModelsState('offline')
      })
    return () => { cancelled = true }
  }, [modelsRefreshKey])
  const selectedModelProfile = selectedModel
    ? engineModels.sampling_profiles?.[selectedModel] ?? null
    : null
  const profileApplied =
    selectedModelProfile !== null && samplingProfileMatches(primaryConfig, selectedModelProfile)

  // W2.0：最小运行环境检测入口（不轮询；工作流变化即清除旧结果）
  const preflightModuleIds = state.workflowModules.map((module) => module.module_id)
  const preflightKey = preflightModuleIds.join('|')
  const [preflight, setPreflight] = useState<RuntimePreflightDTO | null>(null)
  const [preflightBusy, setPreflightBusy] = useState(false)

  useEffect(() => {
    setPreflight(null)
  }, [preflightKey])

  const runPreflight = async () => {
    if (preflightModuleIds.length === 0) return
    setPreflightBusy(true)
    try {
      const result = await engineRuntimeApi.preflight(preflightModuleIds)
      setPreflight(result)
      // 引擎刚恢复在线时刷新底模/LoRA 候选，避免用户重开页面才能选模型。
      if (result.status === 'READY') setModelsRefreshKey((key) => key + 1)
    } catch (error) {
      setPreflight({
        status: 'UNKNOWN',
        engine: { online: false, version: '', detail: error instanceof Error ? error.message : String(error) },
        modules: [],
        checked_at: new Date().toISOString(),
        cache_hit: false,
      })
    } finally {
      setPreflightBusy(false)
    }
  }

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
          {primaryCandidates.length > 0 && (primaryCandidates.length > 1 || primaryModule === '') ? (
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
          {defaultNotice && (
            <p className="ds-notice ds-notice--warning" role="alert">
              {defaultNotice}
            </p>
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

        <button
          type="button"
          className="wb4-runtime-row"
          aria-label="检查运行环境"
          title="检测引擎 / 节点 / 模型"
          disabled={preflightModuleIds.length === 0 || preflightBusy}
          onClick={() => { void runPreflight() }}
        >
          <span className="wb4-runtime-row__main">
            <span className="wb4-switch-row__label">运行环境</span>
            <span className="wb4-switch-row__sub">
              {preflightBusy
                ? '正在检测…'
                : preflight
                  ? `${PREFLIGHT_LABELS[preflight.status]}（${preflight.status}）`
                  : '点击检测引擎 / 节点 / 模型'}
            </span>
          </span>
          <span
            className={`wb4-runtime-row__dot wb4-runtime-row__dot--${
              preflightBusy ? 'busy' : (preflight?.status ?? 'idle').toLowerCase()
            }`}
            aria-hidden="true"
          />
          <IconRestart size={14} />
        </button>
        {preflight && (
          <div>
            <p
              data-testid="runtime-preflight-status"
              className={
                preflight.status === 'READY'
                  ? 'ds-notice'
                  : 'ds-notice ds-notice--warning'
              }
              role="status"
            >
              运行环境：{PREFLIGHT_LABELS[preflight.status]}（{preflight.status}）
              {preflight.engine.version ? `（ComfyUI ${preflight.engine.version}）` : ''}
            </p>
            <ul data-testid="runtime-preflight-details" className="wb-static">
              {preflight.modules.flatMap((module) => [
                ...module.missing_nodes.map((node) => (
                  <li key={`${module.module_id}-node-${node}`}>
                    {module.module_id} 缺少节点：{node}
                  </li>
                )),
                ...module.missing_models.map((model) => (
                  <li key={`${module.module_id}-model-${model.folder}-${model.filename}`}>
                    {module.module_id} 缺少模型：{model.folder}/{model.filename}
                  </li>
                )),
                ...module.missing_requirements.map((reason) => (
                  <li key={`${module.module_id}-req-${reason}`}>{module.module_id}：{reason}</li>
                )),
                ...module.unknown_reasons.map((reason) => (
                  <li key={`${module.module_id}-unknown-${reason}`}>{module.module_id}：{reason}</li>
                )),
                ...module.notes.map((note) => (
                  <li key={`${module.module_id}-note-${note}`}>{module.module_id}：{note}</li>
                )),
              ])}
            </ul>
            {preflight.status !== 'READY' && !preflight.engine.online && preflight.engine.detail && (
              <p className="ds-notice ds-notice--warning">{preflight.engine.detail}</p>
            )}
          </div>
        )}
      </div>

      {/* ===== 底模（v15 任务级模型） ===== */}
      {modelParam && (
        <div className="wb-param">
          <span className="wb-param__label">{modelParam.title || '底模'}</span>
          <PopoverSelect
            value={selectedModel}
            onChange={(value) => setPrimaryModuleConfig({ model: value || undefined })}
            ariaLabel="底模"
            options={[
              { value: '', label: '绑定默认' },
              ...engineModels.checkpoints.map((name) => ({ value: name, label: name })),
            ]}
          />
          {selectedModelProfile && (
            <div className="wb-model-profile">
              <span className="wb-param__label" title={selectedModelProfile.note || undefined}>
                推荐：{formatSamplingProfile(selectedModelProfile)}
              </span>
              {profileApplied ? (
                <span className="wb-model-profile__applied">已采用推荐</span>
              ) : (
                <button
                  type="button"
                  className="ds-btn ds-btn--ghost ds-btn--xs"
                  onClick={() => setPrimaryModuleConfig({
                    steps: selectedModelProfile.steps,
                    cfg: selectedModelProfile.cfg,
                    sampler_name: selectedModelProfile.sampler_name,
                    scheduler: selectedModelProfile.scheduler,
                    denoise: selectedModelProfile.denoise,
                  })}
                >
                  应用推荐
                </button>
              )}
            </div>
          )}
          {engineModelsState === 'loading' && (
            <span className="wb-param__label">正在读取引擎底模…</span>
          )}
          {engineModelsState === 'offline' && (
            <span className="wb-param__label">引擎离线：仅可使用绑定默认底模</span>
          )}
          {engineModelsState === 'ready' && engineModels.checkpoints.length === 0 && (
            <span className="wb-param__label">引擎未安装可用底模：仅可使用绑定默认底模</span>
          )}
        </div>
      )}

      {/* ===== LoRA（最多 2 条） ===== */}
      {supportsLora && engineModels.loras.length > 0 && (
        <LoraStackEditor
          loras={selectedLoras}
          options={engineModels.loras}
          onChange={(next) => setPrimaryModuleConfig({ loras: next.length > 0 ? next : undefined })}
        />
      )}

      {/* ===== 人脸修复（FaceDetailer，性能开关） ===== */}
      {faceDetailerParam && (
        <ModuleParameterField
          param={faceDetailerParam}
          value={primaryConfig.face_detailer}
          onChange={(value) => setPrimaryModuleConfig({ face_detailer: value })}
        />
      )}

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
      {advancedParams.length > 0 && (
        <CollapsibleSection id="advanced" title="高级参数" defaultOpen={false}>
          {advancedParams.map((param) => (
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

/** 当前 Primary config 是否已与推荐采样参数一致（推荐中缺失的字段不参与比较）。 */
function samplingProfileMatches(
  config: Record<string, unknown>,
  profile: EngineSamplingProfileDTO,
): boolean {
  return (
    (profile.steps == null || config.steps === profile.steps) &&
    (profile.cfg == null || config.cfg === profile.cfg) &&
    (profile.sampler_name == null || config.sampler_name === profile.sampler_name) &&
    (profile.scheduler == null || config.scheduler === profile.scheduler) &&
    (profile.denoise == null || config.denoise === profile.denoise)
  )
}

/** 底模推荐采样参数的紧凑文案；缺失字段自动跳过。 */
function formatSamplingProfile(profile: EngineSamplingProfileDTO): string {
  const parts: string[] = []
  if (profile.steps != null) parts.push(`${profile.steps} 步`)
  if (profile.cfg != null) parts.push(`cfg${profile.cfg}`)
  if (profile.sampler_name) parts.push(profile.sampler_name)
  if (profile.scheduler) parts.push(profile.scheduler)
  return parts.join(' · ')
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
