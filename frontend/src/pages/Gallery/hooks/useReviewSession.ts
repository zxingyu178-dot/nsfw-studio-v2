import {
  ApiRequestError,
  imageApi,
  reviewSessionApi,
  type ReviewQueueImageDTO,
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
 * 本适配器只做契约翻译（MobileImageSummary ↔ ImageDTO），不做第二套业务规则。
 */

export const REVIEW_PAGE_SIZE = 50

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
  /** 断点续看：记录浏览位置（fire-and-forget） */
  reportPosition: (image: SessionImage) => void
  /** 结束态：标记完成（仍有未审不强完成） */
  finish: () => void
  /** 继续下一批：丢弃旧 session 句柄，下次 loadPage 开新冻结队列 */
  startNextBatch: () => Promise<void>
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
  let resumeIndex = 0
  let initialized = false

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId
    try {
      const latest = await reviewSessionApi.latestSession()
      if (latest.status === 'ACTIVE') {
        sessionId = latest.id
        resumeIndex = latest.current_index
        return sessionId
      }
      // 最近会话已 COMPLETED → 开新冻结队列
      sessionId = (await reviewSessionApi.createSession(filter)).id
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 404) {
        sessionId = (await reviewSessionApi.createSession(filter)).id
      } else {
        throw e
      }
    }
    return sessionId
  }

  return {
    async loadPage(page: number) {
      const sid = await ensureSession()
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
      reviewSessionApi.reportPosition(sessionId, image.sessionIndex).catch(() => {})
    },

    finish() {
      if (!sessionId) return
      reviewSessionApi.complete(sessionId).catch(() => {})
    },

    async startNextBatch() {
      // 丢弃旧句柄；下次 loadPage → ensureSession 重新 latest/create
      sessionId = null
      initialized = false
      resumeIndex = 0
    },
  }
}
