/**
 * 图片审阅变更串行队列（v0.15.1）。
 *
 * 背景：favorite / KEEP / REJECT 是用户高频连点操作。若每次点击都立即并发 PATCH：
 * - 后发先至会让“最终状态”与“最后一次点击意图”不一致（KEEP→REJECT 却停在 KEEP）；
 * - 失败时只做本地回滚会静默吞错，且可能回滚到过期状态。
 *
 * 本队列保证：
 * 1. **同一张图片串行**：同一 imageId 的变更严格一个个落地，绝不并发（不同图片互不阻塞）；
 * 2. **最后意图生效**：in-flight 期间到达的新意图被合并为“最新目标”，当前请求结束后继续落地，
 *    直到没有更新的意图——因此连点的最终状态恒等于最后一次点击；
 * 3. 失败处理（含重新 GET 权威状态 + 提示）由调用方在 apply 回调里统一做，队列只负责调度。
 */
export interface ImageMutation {
  favorite?: boolean
  status?: 'KEEP' | 'REJECT'
}

export type ImageMutationApply = (imageId: string, mutation: ImageMutation) => Promise<void>

export class ImageMutationQueue {
  /** 每张图的最新目标状态（对象引用用于判断 in-flight 期间是否又有新意图）。 */
  private latest = new Map<string, ImageMutation>()
  /** 每张图当前的排空 Promise；存在即表示该图正在串行处理。 */
  private drainPromise = new Map<string, Promise<void>>()

  constructor(private readonly apply: ImageMutationApply) {}

  /** 入队一次变更；返回该图片的排空 Promise（全部最新意图落地后 resolve）。 */
  enqueue(imageId: string, mutation: ImageMutation): Promise<void> {
    const previous = this.latest.get(imageId)
    this.latest.set(imageId, { ...(previous ?? {}), ...mutation })
    const existing = this.drainPromise.get(imageId)
    if (existing) return existing // 同图在途：合并最新意图，由在途排空循环继续落地，不重复起
    const promise = this.drain(imageId).finally(() => {
      this.drainPromise.delete(imageId)
    })
    this.drainPromise.set(imageId, promise)
    return promise
  }

  /** 串行排空：每次落地当前最新目标；in-flight 期间若又被替换则继续，直到没有更新意图。 */
  private async drain(imageId: string): Promise<void> {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const desired = this.latest.get(imageId)
      if (!desired) break
      await this.apply(imageId, desired)
      // in-flight 期间若有更新意图（latest 被替换成新对象），继续落地；否则本次排空完成。
      if (this.latest.get(imageId) === desired) {
        this.latest.delete(imageId)
        break
      }
    }
  }

  /** 该图片是否仍在串行处理。 */
  isBusy(imageId: string): boolean {
    return this.drainPromise.has(imageId)
  }
}
