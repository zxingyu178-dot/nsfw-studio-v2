import {
  ApiRequestError,
  imageApi,
  reviewSessionApi,
  type ReviewQueueImageDTO,
  type ReviewSessionSummaryDTO,
} from '../../../api/client'
import type { ImageDTO, ImageReviewStatus } from '../../../types/workbench'

/**
 * Phase 0.13：冻结式审核会话适配器（桌面前端 → /api/v1/review/*）。
 *
 * 与手机桥共用同一个 ImageReviewSessionService：
 * - 队列在创建时冻结（绝对 item_index，打标不压缩、不重排）；
 * - decision 单事务 + 乐观锁（expected_status / expected_updated_at），冲突 409 REVIEW_CONFLICT；
 * - GET /sessions/latest 恢复最近 ACTIVE 会话（断点续看 current_index），不重建。
 *
 * v0.37（P0-A）新增批次语义：
 * - 新批次默认 ``only_new``：后端用 NOT EXISTS 排除旧会话成员，只冻结真正的新图；
 * - ``startNextBatch`` 显式换批：先放弃当前 ACTIVE 会话（保留 items），再按新 mode 建会话；
 * - 0 张会话由后端直接 COMPLETED（ended_reason=EMPTY），不再留下永远结束不了的 ACTIVE；
 * - ``newCount`` 用真实 DB 统计当前会话之外的待审图片，供“另有 N 张”提示与实际换批。
 *
 * 本适配器只做契约翻译（MobileImageSummary ↔ ImageDTO），不做第二套业务规则。
 */

export const REVIEW_PAGE_SIZE = 50

export type ReviewBatchMode = 'all' | 'only_new'

/** 队列项 = ImageDTO + 冻结绝对下标（decision / position 必须带上它） */
export interface SessionImage extends ImageDTO {
  sessionIndex: number
}

export interface ReviewPageResult {
  items: SessionImage[]
  has_next: boolean
  total: number
  /** 首屏恢复时应定位到列表内第几个（current_index 所在页内偏移） */
  initialIndex?: number
  /** 首屏实际加载的是第几页（resume 时 ≠ 1） */
  startPage?: number
}

export interface ReviewSessionAdapter {
  loadPage: (page: number) => Promise<ReviewPageResult>
  /** 打标（NEW→RESET 撤销到待审；KEEP/REJECT 直出） */
  decideMark: (image: SessionImage, action: ImageReviewStatus) => Promise<SessionImage>
  /** 收藏（独立于审核状态） */
  setFavorite: (image: SessionImage, favorite: boolean) => Promise<SessionImage>
  /** 409 冲突后按权威 Image 刷新（优先用错误体里返回的 image，否则 GET 单图） */
  resync: (image: SessionImage, authoritativeRaw?: ReviewQueueImageDTO) => Promise<SessionImage>
  /** 断点续看：记录浏览位置（fire-and-forget，失败只记日志不打扰用户） */
  reportPosition: (image: SessionImage) => void
  /** 结束态：标记完成（仍有未审不强完成）；失败必须回报给 UI */
  finish: () => Promise<void>
  /** 当前会话摘要（未建会话时为 null） */
  getSummary: () => ReviewSessionSummaryDTO | null
  /** 当前会话之外的待审核图片数量（未建会话时为 0） */
  countOutsideBatch: () => Promise<number>
  /**
   * 显式换批：放弃当前 ACTIVE 会话（保留 items）后按 mode 新建冻结队列。
   * - mode=only_new（默认）：只含旧会话之外的新图；
   * - mode=all：重新覆盖全部未审核图片（含旧会话里没审完的）。
   */
  startNextBatch: (mode?: ReviewBatchMode) => Promise<void>
}

/** MobileImageSummary → ImageDTO（桌面渲染仍走 8000 自己的 preview/content URL，不用 /mobile/* 路径） */
export function toSessionImage(raw: ReviewQueueImageDTO, index: number): SessionImage {
  return {
    id: raw.image_id,
    job_id: raw.job_id,
    job_item_id: null,
    parent_image_id: null,
    kind: raw.kind || 'original',
    file_path: '',
    width: raw.width,
    height: raw.height,
    seed: raw.seed,
    review_status:
      raw.status === 'KEEP' ? 'KEPT' : raw.status === 'REJECT' ? 'REJECTED' : 'UNREVIEWED',
    favorite: raw.is_favorite,
    status: raw.status,
    source: 'comfyui',
    metadata: {},
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    sessionIndex: index,
  }
}

export function createReviewSessionAdapter(
  filter: Record<string, unknown> = { status: 'NEW', sort: 'created_desc' },
): ReviewSessionAdapter {
  let sessionId: string | null = null
  let summary: ReviewSessionSummaryDTO | null = null
  /** 最近一次后端会话（可能已完成）；用于“另有 N 张”统计，不用于浏览 */
  let lastKnown: ReviewSessionSummaryDTO | null = null
  let resumeIndex = 0
  let initialized = false
  let pendingMode: ReviewBatchMode | null = null

  async function ensureSession(): Promise<string | null> {
    if (sessionId) return sessionId
    if (pendingMode !== null) {
      const mode = pendingMode
      pendingMode = null
      const created = await reviewSessionApi.createSession(filter, { mode })
      sessionId = created.id
      summary = created
      lastKnown = created
      resumeIndex = 0
      return sessionId
    }
    try {
      const latest = await reviewSessionApi.latestSession()
      lastKnown = latest
      if (latest.status === 'ACTIVE') {
        // 继续上次审核：断点续看，不重建
        sessionId = latest.id
        summary = latest
        resumeIndex = latest.current_index
        return sessionId
      }
      // 已完成 / 已放弃 / 空批次：不自动重建，等用户显式选择新批次
      return null
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 404) return null
      throw e
    }
  }

  return {
    async loadPage(page: number) {
      const sid = await ensureSession()
      if (!sid) {
        initialized = true
        return { items: [], has_next: false, total: 0 }
      }
      let targetPage = page
      let resumeOffset: number | undefined
      let startPage: number | undefined
      if (!initialized) {
        initialized = true
        const resumePage = Math.floor(resumeIndex / REVIEW_PAGE_SIZE) + 1
        if (resumePage > page) targetPage = resumePage
        startPage = targetPage
        resumeOffset = resumeIndex - (targetPage - 1) * REVIEW_PAGE_SIZE
      }
      const resp = await reviewSessionApi.queuePage(sid, targetPage, REVIEW_PAGE_SIZE)
      const items = resp.items.map((it) => toSessionImage(it.image, it.index))
      const hasNext = targetPage * resp.page_size < resp.total
      return {
        items,
        has_next: hasNext,
        total: resp.total,
        initialIndex: resumeOffset,
        startPage,
      }
    },

    async decideMark(image, action) {
      const sid = await ensureSession()
      if (!sid) throw new Error('审核会话尚未建立')
      // 冻结会话 decision 只接受 KEEP/REJECT/RESET；撤销回待审 = RESET
      const decisionAction = action === 'KEEP' ? 'KEEP' : action === 'REJECT' ? 'REJECT' : 'RESET'
      const res = await reviewSessionApi.decide(sid, {
        item_index: image.sessionIndex,
        action: decisionAction,
        expected_status: image.status ?? 'NEW',
        expected_updated_at: image.updated_at,
      })
      return toSessionImage(res.image, res.item_index)
    },

    async setFavorite(image, favorite) {
      const sid = await ensureSession()
      if (!sid) throw new Error('审核会话尚未建立')
      const res = await reviewSessionApi.decide(sid, {
        item_index: image.sessionIndex,
        favorite,
        expected_status: image.status ?? 'NEW',
        expected_updated_at: image.updated_at,
      })
      return toSessionImage(res.image, res.item_index)
    },

    async resync(image, authoritativeRaw) {
      if (authoritativeRaw) return toSessionImage(authoritativeRaw, image.sessionIndex)
      const dto = await imageApi.get(image.id)
      return { ...dto, sessionIndex: image.sessionIndex }
    },

    reportPosition(image) {
      if (!sessionId) return
      reviewSessionApi.reportPosition(sessionId, image.sessionIndex).catch((err: unknown) => {
        // 断点位置只是体验优化：失败降级为“下次从会话开头继续”，不打断审核
        console.warn('[review] reportPosition 失败', err)
      })
    },

    async finish() {
      if (!sessionId) return
      summary = await reviewSessionApi.complete(sessionId)
      lastKnown = summary
    },

    getSummary() {
      return summary ?? lastKnown
    },

    async countOutsideBatch() {
      const sid = sessionId ?? lastKnown?.id
      if (!sid) return 0
      const res = await reviewSessionApi.newCount(sid)
      return res.count
    },

    async startNextBatch(mode = 'only_new') {
      const closingId = sessionId
      if (closingId && summary?.status === 'ACTIVE') {
        // 显式换批：先把旧 ACTIVE 会话标 ABANDONED（保留 items 供追溯）
        try {
          summary = await reviewSessionApi.abandon(closingId)
          lastKnown = summary
        } catch (err) {
          // 会话可能已被他处结束（409/404），不阻塞换批
          if (!(err instanceof ApiRequestError && (err.status === 409 || err.status === 404))) {
            throw err
          }
        }
      }
      sessionId = null
      summary = null
      resumeIndex = 0
      initialized = false
      pendingMode = mode
    },
  }
}
