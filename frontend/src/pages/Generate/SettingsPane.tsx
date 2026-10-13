import { activeJob, useJobStore } from '../../stores/jobStore'
import { Pane } from './Pane'
import { CollapsibleSection } from './components/CollapsibleSection'
import { CurrentJobCard } from './components/CurrentJobCard'
import { GenerateAction } from './components/GenerateAction'
import { GenerationControls } from './components/GenerationControls'
import { QueuePanel } from './components/QueuePanel'

/**
 * 右栏（规范 §五十一、§五十三、§五十四；Phase 0.12 任务 5.3）。
 *
 * 不改三栏结构，只把连续堆叠的字段分成 4 组可折叠（折叠态存 localStorage）：
 * - 工作流：Engine 只读 / Primary Module / 模块参数 / 高清放大；
 * - 画面：画幅 / 分辨率 / 自定义尺寸；
 * - 输出：数量 / Seed；
 * - 任务与队列：Current Job + Queue（固定高度内部滚动）。
 * 主操作 [生成][优先生成] 固定在卡片底部 sticky action footer，滚到右栏任何位置都可见。
 */
export function SettingsPane({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
  const store = useJobStore()
  const job = activeJob(store)

  return (
    <Pane
      title="生成配置"
      footer={<GenerateAction imageGenAvailable={imageGenAvailable} />}
    >
      <GenerationControls />

      <CollapsibleSection id="tasks" title="任务与队列">
        {job && <CurrentJobCard job={job} busy={store.busyJobId === job.id} />}
        <QueuePanel />
      </CollapsibleSection>
    </Pane>
  )
}

export default SettingsPane
