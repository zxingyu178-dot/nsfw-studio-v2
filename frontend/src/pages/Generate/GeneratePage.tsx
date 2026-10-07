import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { PromptEditorPane } from './PromptEditorPane'
import { ResultPane } from './ResultPane'
import { SettingsPane } from './SettingsPane'
import { hydrateWorkbench, resetWorkbench } from '../../stores/workbenchStore'
import type { WorkbenchNavigationState } from './workbenchNavigation'

export default function GeneratePage() {
  const location = useLocation()

  useEffect(() => {
    const navigation = (location.state ?? {}) as WorkbenchNavigationState
    if (navigation.workbench) {
      if (navigation.replace !== false) resetWorkbench()
      hydrateWorkbench(navigation.workbench, navigation.sourceRecipeId ?? null)
    }
  }, [location.state])

  return (
    <section className="workbench" aria-label="生成工作台">
      <div className="workbench__col workbench__col--editor">
        <PromptEditorPane />
      </div>
      <div className="workbench__col workbench__col--result">
        <ResultPane />
      </div>
      <div className="workbench__col workbench__col--settings">
        <SettingsPane />
      </div>
    </section>
  )
}
