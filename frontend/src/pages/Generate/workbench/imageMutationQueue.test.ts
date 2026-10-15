/**
 * ImageMutationQueue（v0.15.1）合同：
 * - 同一图片串行（in-flight 时不并发第二次）；
 * - 连点合并为最后意图（KEEP→REJECT 最终落 REJECT；反复收藏最终=最后一次）；
 * - 不同图片互不阻塞。
 */
import { describe, expect, it, vi } from 'vitest'
import { ImageMutationQueue, type ImageMutation } from './imageMutationQueue'

/** 可控的 apply：用 gate 手动放行每次请求，便于断言“在途不并发”。 */
function gatedApply() {
  const calls: Array<{ id: string; mut: ImageMutation }> = []
  const gates: Array<() => void> = []
  const apply = vi.fn((id: string, mut: ImageMutation) => {
    calls.push({ id, mut })
    return new Promise<void>((resolve) => {
      gates.push(resolve)
    })
  })
  return { apply, calls, gates }
}

describe('ImageMutationQueue', () => {
  it('同图串行：第一次在途时，第二次不并发，仅合并最新意图', async () => {
    const { apply, calls, gates } = gatedApply()
    const queue = new ImageMutationQueue(apply)

    const p = queue.enqueue('img1', { status: 'KEEP' })
    queue.enqueue('img1', { status: 'REJECT' }) // 在途连点
    expect(apply).toHaveBeenCalledTimes(1) // 仍只有第一个请求在跑
    expect(calls[0].mut).toEqual({ status: 'KEEP' })

    gates[0]() // 放行第一个
    await new Promise((r) => setTimeout(r, 0))
    // 第一个落地后立即排空合并后的最新意图（REJECT）
    expect(apply).toHaveBeenCalledTimes(2)
    expect(calls[1].mut.status).toBe('REJECT')
    gates[1]()
    await p
    // 最终落地序列末状态为 REJECT
    expect(calls[calls.length - 1].mut.status).toBe('REJECT')
  })

  it('favorite 连点最终=最后一次意图（false→true→false 最终 false）', async () => {
    const applied: ImageMutation[] = []
    const apply = vi.fn(async (_id: string, mut: ImageMutation) => {
      // 模拟在途：每轮让出一个微任务
      await Promise.resolve()
      applied.push(mut)
    })
    const queue = new ImageMutationQueue(apply)
    await Promise.all([
      queue.enqueue('img', { favorite: true }),
      queue.enqueue('img', { favorite: false }),
      queue.enqueue('img', { favorite: true }),
      queue.enqueue('img', { favorite: false }),
    ])
    expect(applied[applied.length - 1].favorite).toBe(false)
  })

  it('不同图片互不阻塞：两张图各发起一次，apply 各被调用', async () => {
    const apply = vi.fn(async () => { await Promise.resolve() })
    const queue = new ImageMutationQueue(apply)
    await Promise.all([
      queue.enqueue('imgA', { favorite: true }),
      queue.enqueue('imgB', { status: 'REJECT' }),
    ])
    expect(apply).toHaveBeenCalledTimes(2)
  })

  it('favorite 与 status 合并到同一在途批次（合并为一个目标对象）', async () => {
    const { apply, calls, gates } = gatedApply()
    const queue = new ImageMutationQueue(apply)
    const p = queue.enqueue('img1', { favorite: true })
    queue.enqueue('img1', { status: 'REJECT' })
    gates[0]() // 放行第一个（favorite:true）
    await new Promise((r) => setTimeout(r, 0))
    // 随后排空合并目标（同时含 favorite=true 与 status=REJECT）
    gates[1]()
    await p
    const last = calls[calls.length - 1].mut
    expect(last.status).toBe('REJECT')
    expect(last.favorite).toBe(true)
  })
})
