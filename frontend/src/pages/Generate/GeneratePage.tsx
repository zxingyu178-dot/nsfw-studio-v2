import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { moduleApi } from '../../api/client'
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

export default function GeneratePage() {
  const location = useLocation()
  const state = useWorkbench()
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
          <SettingsPane imageGenAvailable={imageGenAvailable} />
        </div>
      </div>
    </section>
  )
}