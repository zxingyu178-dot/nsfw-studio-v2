import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { moduleApi } from '../../api/client'
import { SegmentedControl } from '../../components/ui'
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
          UI 3.0：用 div[role=tab] 而非裸 <button>，保持 tablist/aria-selected 契约。 */}
      <div className="generate__tabs" role="tablist" aria-label="工作台面板">
        {TAB_LABELS.map((t) => (
          <div
            key={t.key}
            role="tab"
            tabIndex={0}
            aria-selected={activeTab === t.key}
            onClick={() => setActiveTab(t.key)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setActiveTab(t.key)
              }
            }}
          >
            {t.label}
          </div>
        ))}
      </div>
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
