/**
 * GeneratePage —— 紧凑创作台。
 *
 * 双栏：左 Prompt Console（生成什么）｜右 Inspector（怎么生成）；
 * 实时预览统一在首页，创作页只保留明确入口。顶 WorkbenchBar，底 TaskDock。
 */
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { moduleApi } from '../../api/client'
import { Tabs } from '../../components/ui'
import { InspectorPanel } from './workbench/InspectorPanel'
import { PromptConsole } from './workbench/PromptConsole'
import { ResizablePane } from './workbench/ResizablePane'
import { TaskDock } from './workbench/TaskDock'
import { WorkbenchBar } from './workbench/WorkbenchBar'
import {
  COLLAPSED_WIDTH,
  LEFT_MAX,
  LEFT_MIN,
  RIGHT_MAX,
  RIGHT_MIN,
  resetLeftWidth,
  resetRightWidth,
  setLeftWidth,
  setRightWidth,
  toggleLeftCollapsed,
  toggleRightCollapsed,
  useWorkbenchLayout,
} from './workbench/workbenchLayout'
import {
  availableImageModuleIds,
  hydrateWorkbench,
  resetWorkbench,
  setModuleCatalog,
  useWorkbench,
} from '../../stores/workbenchStore'
import type { WorkbenchNavigationState } from './workbenchNavigation'
import './generate.css'

type WorkspaceTab = 'prompt' | 'settings'

const TAB_LABELS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: 'prompt', label: 'Prompt' },
  { key: 'settings', label: '参数' },
]

export default function GeneratePage() {
  const location = useLocation()
  useWorkbench()
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('prompt')
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
        setModuleCatalog(modules)
        setImageGenAvailable(availableImageModuleIds(modules).length > 0)
      })
      .catch(() => {
        setModuleCatalog([])
        setImageGenAvailable(false)
      })
  }, [])

  const layout = useWorkbenchLayout()

  return (
    <div className={`generate wb4 generate--studio-fusion generate--creation generate--tab-${activeTab}`} aria-label="生成工作台">
      <WorkbenchBar />

      <div className="generate__preview-entry">
        <Link className="ds-link generate__preview-link" to="/">查看实时预览</Link>
      </div>

      <Tabs
        className="generate__tabs"
        ariaLabel="工作台面板"
        items={TAB_LABELS.map((t) => ({ key: t.key, label: t.label }))}
        active={activeTab}
        onChange={(key) => setActiveTab(key as WorkspaceTab)}
      />

      <div
        className="wb4-columns"
        aria-label="创作工作区"
        style={{
          '--left-w': layout.leftCollapsed ? `${COLLAPSED_WIDTH}px` : `${layout.leftWidth}px`,
          '--right-w': layout.rightCollapsed ? `${COLLAPSED_WIDTH}px` : `${layout.rightWidth}px`,
        } as React.CSSProperties}
      >
        <ResizablePane
          side="left"
          width={layout.leftWidth}
          min={LEFT_MIN}
          max={LEFT_MAX}
          label="Prompt 栏宽度"
          onChange={setLeftWidth}
          onReset={resetLeftWidth}
          className="generate__pane generate__pane--prompt"
          collapsed={layout.leftCollapsed}
          collapseLabel="Prompt 栏"
          onToggleCollapse={toggleLeftCollapsed}
        >
          <PromptConsole onCollapse={toggleLeftCollapsed} />
        </ResizablePane>

        <ResizablePane
          side="right"
          width={layout.rightWidth}
          min={RIGHT_MIN}
          max={RIGHT_MAX}
          label="参数栏宽度"
          onChange={setRightWidth}
          onReset={resetRightWidth}
          className="generate__pane generate__pane--settings"
          collapsed={layout.rightCollapsed}
          collapseLabel="参数栏"
          onToggleCollapse={toggleRightCollapsed}
        >
          <InspectorPanel imageGenAvailable={imageGenAvailable} onCollapse={toggleRightCollapsed} />
        </ResizablePane>
      </div>

      <TaskDock />
    </div>
  )
}
