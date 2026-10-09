import { useState } from 'react'
import { HistoryTab } from './HistoryTab'
import { PromptTab } from './PromptTab'
import { RecipeTab } from './RecipeTab'
import { Tabs, TabPanel } from '../../components/ui'
import './prompt.css'

type PromptPageTab = 'prompts' | 'recipes' | 'history'

/** 提示词页（§三十七）：[我的 Prompt] [配方] [历史] */
export default function PromptPage() {
  const [tab, setTab] = useState<PromptPageTab>('prompts')

  return (
    <>
      <Tabs
        ariaLabel="提示词页签"
        active={tab}
        onChange={(key) => setTab(key as PromptPageTab)}
        items={[
          { key: 'prompts', label: '我的 Prompt' },
          { key: 'recipes', label: '配方' },
          { key: 'history', label: '历史' },
        ]}
      />
      <TabPanel itemKey="prompts" active={tab}>
        <PromptTab />
      </TabPanel>
      <TabPanel itemKey="recipes" active={tab}>
        <RecipeTab />
      </TabPanel>
      <TabPanel itemKey="history" active={tab}>
        <HistoryTab />
      </TabPanel>
    </>
  )
}
