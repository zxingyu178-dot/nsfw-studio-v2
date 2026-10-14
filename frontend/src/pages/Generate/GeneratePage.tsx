import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { moduleApi } from '../../api/client'
import { SegmentedControl, Tabs } from '../../components/ui'
import { PromptEditorPane } from './PromptEditorPane'
import { ResultPane } from './ResultPane'
import { SettingsPane } from './SettingsPane'
import {
  availableImageModuleIds,
  hydrateWorkbench,
  resetWorkbench,
  setModuleCatalog,
  setWorkbenchMode,
  useWorkbench,
} from '../../stores/workbenchStore'
import type { WorkbenchNavigationState } from './workbenchNavigation'
import './generate.css'

type WorkspaceTab = 'prompt' | 'preview' | 'settings'

const TAB_LABELS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: 'prompt', label: 'Prompt' },
  { key: 'preview', label: '预览' },
  { key: 'settings', label: '配置' },
]

export default function GeneratePage() {
  const location = useLocation()
  const state = useWorkbench()
  // 窄屏（<1024）Workspace Tabs：一次只显示一个 pane；宽屏三栏时该状态不影响布局。
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('prompt')
  /**
   * 图片生成 Gate（Phase 5 §二十；Phase 5.1 Task7）：
   * 目录中存在 **available=true** 且 input_required=true / output_kind=processed 的模块才算可用。
   * 只注册、未配置 provider binding 的模块 → registered=true / available=false → Gate 关闭。
   */
  const [imageGenAvailable, setImageGenAvailable] = useState<boolean | null>(null)

  useEffect(() => {
    const navigation = (location.state ?? {}) as WorkbenchNavigationState
    if (navigation.workbench) {
      if (navigation.replace !== false) resetWorkbench()
      hydrateWorkbench(navigation.workbench, navigation.sourceRecipeId ?? null)
    }
  }, [location.state])

  useEffect(() => {
    moduleApi
      .list()
      .then((modules) => {
        // Task6/Task7：目录进 store（校正 Primary Module + 作为 Gate 唯一依据）
        setModuleCatalog(modules)
        setImageGenAvailable(availableImageModuleIds(modules).length > 0)
      })
      .catch(() => {
        setModuleCatalog([])
        setImageGenAvailable(false)
      })
  }, [])

  return (
    <div className={`generate generate--tab-${activeTab}`} aria-label="生成工作台">
      <div className="generate__modebar">
        <SegmentedControl
          value={state.mode}
          onChange={(v) => setWorkbenchMode(v as typeof state.mode)}
          options={[
            { value: 'text', label: '文生图' },
            { value: 'image', label: '图片生成' },
          ]}
          ariaLabel="生成模式"
        />
        {state.mode === 'image' && (
          <span className="muted generate__modebar-hint">
            {imageGenAvailable === null
              ? '正在检查图片生成工作流…'
              : imageGenAvailable
                ? '输入图片 + Prompt → 处理型工作流'
                : '图片生成：尚未配置可用工作流'}
          </span>
        )}
      </div>
      {/* 窄屏（<1024）Workspace Tabs：宽屏由 CSS 隐藏。
          收口到 components/ui/Tabs（标准 WAI-ARIA tablist/tab/tabpanel），不再自造 div tab。 */}
      <Tabs
        className="generate__tabs"
        ariaLabel="工作台面板"
        items={TAB_LABELS.map((t) => ({ key: t.key, label: t.label }))}
        active={activeTab}
        onChange={(key) => setActiveTab(key as WorkspaceTab)}
      />
      <div className="generate__columns">
        <div className="generate__pane generate__pane--prompt">
          <PromptEditorPane />
        </div>
        <div className="generate__pane generate__pane--preview">
          <ResultPane />
        </div>
        <div className="generate__pane generate__pane--settings">
          <SettingsPane imageGenAvailable={imageGenAvailable} />
        </div>
      </div>
    </div>
  )
}
