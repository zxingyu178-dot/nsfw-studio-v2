import { useEffect, useState } from 'react'
import { formatElapsed } from '../../utils/elapsed'

interface ElapsedTimerProps {
  /** 任务开始时间（ISO 字符串）。 */
  startedAt: string
  /** 结束时间（ISO 字符串）；提供则定格在该时长，不再走表。 */
  finishedAt?: string | null
  /** 可选前缀标签。 */
  label?: string
}

/**
 * 自包含"已运行"计时器（Commit 7）。
 *
 * 性能红线：1 秒 interval 只在本组件内部，仅本组件每秒重渲染；
 * 不放到父组件 / store，避免整个 GeneratePage 每秒重渲染。
 * 只显示"已运行 mm:ss"，绝不做 ETA / 完成时间预测。
 */
export function ElapsedTimer({ startedAt, finishedAt = null, label }: ElapsedTimerProps) {
  const [now, setNow] = useState<number>(() => Date.now())

  useEffect(() => {
    if (finishedAt) return // 已结束：定格，不启动 interval
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [finishedAt])

  const startMs = new Date(startedAt).getTime()
  const endMs = finishedAt ? new Date(finishedAt).getTime() : now
  const seconds = (endMs - startMs) / 1000

  return (
    <span className="elapsed-timer" data-testid="elapsed-timer" title={label}>
      {label ? `${label} ` : ''}已运行 {formatElapsed(seconds)}
    </span>
  )
}

export default ElapsedTimer
