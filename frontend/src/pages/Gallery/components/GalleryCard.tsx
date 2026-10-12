import { useEffect, useRef, useState } from 'react'
import { Badge, StatusBadge } from '../../../components/ui'
import {
  IMAGE_KIND_LABEL,
  IMAGE_STATUS_LABEL,
  imageThumbUrl,
  normalizeImageStatus,
  shortJobId,
  type ImageDTO,
} from '../../../types/workbench'

/**
 * Phase 0.12 Task9：单张图库卡片（从 GalleryPage 抽取，行为不变）。
 * 单击打开详情（父组件带延迟）、双击打开 Lightbox；进入选择模式时切换选中。
 */

interface GalleryCardProps {
  image: ImageDTO
  selected: boolean
  onCardClick: (image: ImageDTO) => void
  onCardDoubleClick: (image: ImageDTO) => void
}

export function GalleryCard({ image, selected, onCardClick, onCardDoubleClick }: GalleryCardProps) {
  const status = normalizeImageStatus(image)
  return (
    <button
      type="button"
      className={`gal-card${selected ? ' gal-card--selected' : ''}`}
      onClick={() => onCardClick(image)}
      onDoubleClick={() => onCardDoubleClick(image)}
      title={`${IMAGE_KIND_LABEL[image.kind] ?? image.kind} · ${shortJobId(image.job_id ?? '')} · ${IMAGE_STATUS_LABEL[status]}`}
    >
      <GalleryThumb image={image} />
      <span className="gal-card__badges">
        {image.kind === 'upscaled' && <span className="gal-card__hd">HD</span>}
        {selected && <Badge tone="accent">✓</Badge>}
        {image.favorite && <span className="gal-card__fav" title="收藏">★</span>}
        {status !== 'NEW' && <StatusBadge status={status} />}
      </span>
    </button>
  )
}

/** 卡片缩略图：进入 viewport+300px 才加载，带占位 / 错误重试 */
function GalleryThumb({ image }: { image: ImageDTO }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [inView, setInView] = useState(false)
  const [error, setError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setInView(true)
          obs.disconnect()
        }
      },
      { rootMargin: '300px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div className="gal-card__media" ref={ref}>
      {!inView ? (
        <div className="gal-card__ph" aria-hidden="true" />
      ) : error ? (
        <div className="gal-card__err" onClick={() => { setError(false); setRetryKey((k) => k + 1) }} role="button" tabIndex={0}>
          加载失败 · 重试
        </div>
      ) : (
        <img
          key={retryKey}
          className="gal-card__img"
          src={imageThumbUrl(image.id)}
          alt=""
          onError={() => setError(true)}
        />
      )}
    </div>
  )
}
