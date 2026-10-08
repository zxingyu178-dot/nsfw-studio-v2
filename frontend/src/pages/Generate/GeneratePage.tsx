import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { moduleApi } from '../../api/client'
import { PromptEditorPane } from './PromptEditorPane'
import { ResultPane } from './ResultPane'
import { SettingsPane } from './SettingsPane'
import { hydrateWorkbench, resetWorkbench, setWorkbenchMode, useWorkbench } from '../../stores/workbenchStore'
import type { WorkbenchNavigationState } from './workbenchNavigation'

export default function GeneratePage() {
  const location = useLocation()
  const state = useWorkbench()
  /**
   * 图片生成 Gate（Phase 5 §二十）：需要存在 input_required=true 且 output_kind=processed 的模块。
   * Gate B（无可用工作流）→ 图片生成模式显示"尚未配置可用工作流"，提交按钮禁用。
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
      .then((modules) =>
        setImageGenAvailable(
          modules.some((module) => module.input_required && module.output_kind === 'processed'),
        ),
      )
      .catch(() => setImageGenAvailable(false))
  }, [])

  return (
    <section className="workbench" aria-label="生成工作台">
      <div className="workbench__modebar">
        <div className="segmented" role="tablist" aria-label="生成模式">
          <button
            type="button"
            role="tab"
            aria-selected={state.mode === 'text'}
            className={`segmented__item${state.mode === 'text' ? ' segmented__item--active' : ''}`}
            onClick={() => setWorkbenchMode('text')}
          >
            文生图
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={state.mode === 'image'}
            className={`segmented__item${state.mode === 'image' ? ' segmented__item--active' : ''}`}
            onClick={() => setWorkbenchMode('image')}
          >
            图片生成
          </button>
        </div>
        {state.mode === 'image' && (
          <span className="muted">
            {imageGenAvailable === null
              ? '正在检查图片生成工作流…'
              : imageGenAvailable
                ? '输入图片 + Prompt → 处理型工作流'
                : '图片生成：尚未配置可用工作流'}
          </span>
        )}
      </div>
      <div className="workbench__columns">
        <div className="workbench__col workbench__col--editor">
          <PromptEditorPane />
        </div>
        <div className="workbench__col workbench__col--result">
          <ResultPane />
        </div>
        <div className="workbench__col workbench__col--settings">
          <SettingsPane imageGenAvailable={imageGenAvailable === true} />
        </div>
      </div>
    </section>
  )
}