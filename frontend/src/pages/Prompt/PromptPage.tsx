import { useState } from 'react'
import { HistoryTab } from './HistoryTab'
import { PromptTab } from './PromptTab'
import { RecipeTab } from './RecipeTab'

type PromptPageTab = 'prompts' | 'recipes' | 'history'

/** 提示词页（规范 §三十七）：[我的 Prompt] [配方] [历史]（Phase 4 Task5：历史正式接 Job） */
export default function PromptPage() {
  const [tab, setTab] = useState<PromptPageTab>('prompts')

  return (
    <section className="page page--wide">
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'prompts'}
          className={`tabs__item${tab === 'prompts' ? ' tabs__item--active' : ''}`}
          onClick={() => setTab('prompts')}
        >
          我的 Prompt
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'recipes'}
          className={`tabs__item${tab === 'recipes' ? ' tabs__item--active' : ''}`}
          onClick={() => setTab('recipes')}
        >
          配方
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'history'}
          className={`tabs__item${tab === 'history' ? ' tabs__item--active' : ''}`}
          onClick={() => setTab('history')}
        >
          历史
        </button>
      </div>

      {tab === 'prompts' && <PromptTab />}
      {tab === 'recipes' && <RecipeTab />}
      {tab === 'history' && <HistoryTab />}
    </section>
  )
}
