/**
 * Resume family（v0.15.1）：Canvas 必须展示完整的“断点续作链”图片，而不只是一层 parent。
 *
 * 背景：resume-remaining 会在父任务上继续生成，形成 A(root)→B→C 的单向链
 * （JobDTO.resume_of_job_id 指向直接父任务）。v0.15 只取 [current, parent] 一层，
 * 导致 A→B→C 时 Canvas 漏掉 A 的图片。本模块沿 resume_of_job_id 向上遍历，
 * 返回从 root 到 current 的完整任务 id 序列（[A, B, C]），供逐任务拉取并合并图片。
 *
 * 安全：
 * - cycle guard：visited 集合，遇到重复 id 立即停止（数据异常形成环时不死循环）；
 * - max-depth guard：上限 MAX_RESUME_FAMILY_DEPTH，超过即截断（防止异常数据无限上溯）。
 */
export const MAX_RESUME_FAMILY_DEPTH = 16

export interface ResumeChainNode {
  resume_of_job_id: string | null
}

/**
 * 沿 resume_of_job_id 向上遍历，返回 root → current 顺序的任务 id 链。
 * @param getJob 按 id 拉取最小 Job 信息（仅需 resume_of_job_id），由调用方注入以便测试/复用
 */
export async function fetchResumeFamilyJobIds<TNode extends ResumeChainNode>(
  getJob: (id: string) => Promise<TNode>,
  jobId: string,
): Promise<string[]> {
  const chain: string[] = []
  const seen = new Set<string>()
  let current: string | null = jobId
  for (let depth = 0; depth < MAX_RESUME_FAMILY_DEPTH && current !== null; depth++) {
    if (seen.has(current)) break // cycle guard
    seen.add(current)
    chain.push(current)
    const node = await getJob(current)
    current = node.resume_of_job_id ?? null
  }
  return chain.reverse() // root … current
}
