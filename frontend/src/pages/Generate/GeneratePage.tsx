/**
 * GeneratePage v0.15 —— Workbench Layout 4.0（Canvas First）。
 *
 * 三栏：左 Prompt Console（生成什么）｜中 Canvas（结果，深色哑光、绝不 blur）｜右 Inspector（怎么生成）；
 * 顶 WorkbenchBar（模式/来源/重置/保存）；底 TaskDock（收起态常驻，展开态含当前任务 + 队列全能力）。
 * 数据与业务逻辑（module catalog、location.state 带入配方、job 跟踪、结果动作）与 0.14 一致，仅重构布局。
 */
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { moduleApi } from '../../api/client'
import { Tabs } from '../../components/ui'
import { CanvasStage } from './workbench/CanvasStage'
import { InspectorPanel } from './workbench/InspectorPanel'
import { PromptConsole } from './workbench/PromptConsole'
import { ResizablePane } from './workbench/ResizablePane'
import { TaskDock } from './workbench/TaskDock'
import { WorkbenchBar } from './workbench/WorkbenchBar'
import {
  LEFT_MAX,
  LEFT_MIN,
  RIGHT_MAX,
  RIGHT_MIN,
  resetLeftWidth,
  resetRightWidth,
  setLeftWidth,
  setRightWidth,
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

type WorkspaceTab = 'prompt' | 'preview' | 'settings'

const TAB_LABELS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: 'prompt', label: 'Prompt' },
  { key: 'preview', label: '预览' },
  { key: 'settings', label: '配置' },
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
    <div className={`generate wb4 generate--tab-${activeTab}`} aria-label="生成工作台">
      <WorkbenchBar />

      <Tabs
        className="generate__tabs"
        ariaLabel="工作台面板"
        items={TAB_LABELS.map((t) => ({ key: t.key, label: t.label }))}
        active={activeTab}
        onChange={(key) => setActiveTab(key as WorkspaceTab)}
      />

      <div
        className="wb4-columns"
        style={{ '--left-w': `${layout.leftWidth}px`, '--right-w': `${layout.rightWidth}px` } as React.CSSProperties}
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
        >
          <PromptConsole />
        </ResizablePane>

        <div className="wb4-pane wb4-center generate__pane generate__pane--preview">
          <CanvasStage />
        </div>

        <ResizablePane
          side="right"
          width={layout.rightWidth}
          min={RIGHT_MIN}
          max={RIGHT_MAX}
          label="参数栏宽度"
          onChange={setRightWidth}
          onReset={resetRightWidth}
          className="generate__pane generate__pane--settings"
        >
          <InspectorPanel imageGenAvailable={imageGenAvailable} />
        </ResizablePane>
      </div>

      <TaskDock />
    </div>
  )
}
