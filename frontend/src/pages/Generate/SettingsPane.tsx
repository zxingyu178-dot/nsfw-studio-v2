import { activeJob, useJobStore } from '../../stores/jobStore'
import { Pane } from './Pane'
import { CurrentJobCard } from './components/CurrentJobCard'
import { GenerationControls } from './components/GenerationControls'
import { QueuePanel } from './components/QueuePanel'

/**
 * 右栏（规范 §五十一、§五十三、§五十四）：生成配置 + 当前任务 + 队列。
 *
 * Phase 0.12 任务 9 纯拆分：本文件仅负责按原顺序组装三个子区域，
 * 行为 / DOM / 对外 API（`SettingsPane({ imageGenAvailable })`）保持不变：
 * - GenerationControls：引擎状态 / Primary Module / 模块参数 / 尺寸 / 数量 / Seed / 主操作；
 * - CurrentJobCard：当前任务卡片；
 * - QueuePanel：队列（拖拽排序 / 优先 / 暂停 / 取消 / 全局暂停继续）。
 */
export function SettingsPane({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
  const store = useJobStore()
  const job = activeJob(store)

  return (
    <Pane title="生成配置">
      <GenerationControls imageGenAvailable={imageGenAvailable} />

      {job && <CurrentJobCard job={job} busy={store.busyJobId === job.id} />}

      <QueuePanel />
    </Pane>
  )
}

export default SettingsPane
