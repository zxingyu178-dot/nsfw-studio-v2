import { Button } from '../../../components/ui'
import { formatDateTime } from '../../../utils/format'
import { shortJobId, type ImageJobGroupDTO } from '../../../types/workbench'

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
      {groups.map((g) => (
        <div key={g.job_id} className="gal-group">
          <button type="button" className="gal-group__main" onClick={() => onApplyJobFilter(g.job_id)}>
            <div className="gal-group__head">
              <span className="gal-group__id">{shortJobId(g.job_id)}</span>
              <span className="muted">{g.total} 张 · {formatDateTime(g.created_at)}</span>
            </div>
            <p className="gal-group__counts muted">
              未审核 {g.unreviewed} · 保留 {g.kept} · 收藏 {g.favorites} · 淘汰 {g.rejected}
            </p>
          </button>
          <Button size="sm" variant="primary" onClick={() => onReviewJob(g.job_id)}>
            开始审核
          </Button>
        </div>
      ))}
      {hasNext && (
        <div className="gal-group">
          <Button size="sm" variant="secondary" disabled={loading} onClick={() => onLoadMore(page + 1)}>
            {loading ? '加载中…' : '加载更多任务'}
          </Button>
        </div>
      )}
    </div>
  )
}
