import { Button } from '../../../components/ui'
import { formatDateTime } from '../../../utils/format'
import { imageThumbUrl, shortJobId, type ImageJobGroupDTO } from '../../../types/workbench'

/**
 * Phase 0.12 Task9：按任务分组视图（从 GalleryPage 抽取，行为不变）。
 */

interface GalleryGroupViewProps {
  groups: ImageJobGroupDTO[]
  loading: boolean
  hasNext: boolean
  page: number
  onApplyJobFilter: (jobId: string) => void
  onReviewJob: (jobId: string) => void
  onLoadMore: (page: number) => void
}

export function GalleryGroupView({
  groups, loading, hasNext, page, onApplyJobFilter, onReviewJob, onLoadMore,
}: GalleryGroupViewProps) {
  return (
    <div className="gal-group-list">
      {loading && <p className="muted">加载中…</p>}
      {!loading && groups.length === 0 && (
        <p className="muted">还没有完成过的生成任务。</p>
      )}
      {groups.map((g) => {
        const previews = (g.preview_image_ids ?? []).slice(0, 4)
        const remaining = Math.max(0, g.total - previews.length)
        return (
          <article
            key={g.job_id}
            className="gal-group"
            onClick={() => onApplyJobFilter(g.job_id)}
          >
            <div className="gal-group__main">
              <div className="gal-group__head">
                <span className="gal-group__identity">
                  <span className="gal-group__id">{shortJobId(g.job_id)}</span>
                  {g.module_id && <span className="gal-group__module">{g.module_id}</span>}
                </span>
                <span className="gal-group__time">{formatDateTime(g.created_at)}</span>
              </div>
              <div className="gal-group__counts">
                <span className="gal-group__count">未审核 {g.unreviewed}</span>
                <span className="gal-group__count gal-group__count--success">保留 {g.kept}</span>
                <span className="gal-group__count gal-group__count--warning">收藏 {g.favorites}</span>
                <span className="gal-group__count gal-group__count--danger">淘汰 {g.rejected}</span>
              </div>
              <div className="gal-group__previews">
                {previews.length > 0 ? previews.map((imageId) => (
                  <img
                    key={imageId}
                    className="gal-group__thumb"
                    src={imageThumbUrl(imageId)}
                    alt=""
                    loading="lazy"
                  />
                )) : <span className="gal-group__preview-empty">暂无预览</span>}
                {previews.length > 0 && remaining > 0 && (
                  <span className="gal-group__more">+{remaining}</span>
                )}
              </div>
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={(event) => {
                event.stopPropagation()
                onReviewJob(g.job_id)
              }}
            >
              开始审核
            </Button>
          </article>
        )
      })}
      {hasNext && (
        <div className="gal-group-load-more">
          <Button size="sm" variant="secondary" disabled={loading} onClick={() => onLoadMore(page + 1)}>
            {loading ? '加载中…' : '加载更多任务'}
          </Button>
        </div>
      )}
    </div>
  )
}
