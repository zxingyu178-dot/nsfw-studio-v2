// 已运行时长格式化（Commit 7）：只展示"已运行多久"，禁止 ETA / 完成时间预测。

/**
 * 秒数 → 中文友好时长字符串。
 * - 不足 1 小时：mm:ss（0 → "00:00"）；
 * - 达到 / 超过 1 小时：hh:mm:ss。
 * 负值 / NaN 按 0 处理。
 */
export function formatElapsed(totalSeconds: number): string {
  const s =
    Number.isFinite(totalSeconds) && totalSeconds > 0 ? Math.floor(totalSeconds) : 0
  const hours = Math.floor(s / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  const secs = s % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(secs).padStart(2, '0')
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${mm}:${ss}`
  }
  return `${mm}:${ss}`
}
