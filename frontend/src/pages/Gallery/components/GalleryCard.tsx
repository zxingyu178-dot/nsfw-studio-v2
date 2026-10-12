import { useEffect, useRef, useState } from 'react'
import {
  IMAGE_KIND_LABEL,
  IMAGE_STATUS_LABEL,
  imageThumbUrl,
  normalizeImageStatus,
  shortJobId,
  type ImageDTO,
} from '../../../types/workbench'

/**
 * Phase 0.12 Task6：单张图库卡片。
 * - 左上：HD/processed 徽标；右上：收藏 ★（多选模式改为 checkbox/选中态）；
 * - 底部 hover overlay：尺寸 + 审核状态。
 * 进入选择模式后才显示 checkbox，平时不打扰浏览。
 */

interface GalleryCardProps {
  image: ImageDTO
  selected: boolean
  selectMode: boolean
  onCardClick: (image: ImageDTO) => void
  onCardDoubleClick: (image: ImageDTO) => void
}

export function GalleryCard({ image, selected, selectMode, onCardClick, onCardDoubleClick }: GalleryCardProps) {
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
      {image.kind === 'upscaled' && <span className="gal-card__hd">HD</span>}
      <span className="gal-card__corner">
        {selectMode && (
          <span className={`gal-card__check${selected ? ' gal-card__check--on' : ''}`} aria-hidden="true">
            {selected ? '✓' : ''}
          </span>
        )}
        {!selectMode && image.favorite && <span className="gal-card__fav" title="收藏">★</span>}
      </span>
      <span className="gal-card__overlay">
        <span className="gal-card__overlay-size">{image.width}×{image.height}</span>
        <span className="gal-card__overlay-status">{IMAGE_STATUS_LABEL[status]}</span>
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
