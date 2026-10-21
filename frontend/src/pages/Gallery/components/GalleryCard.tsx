import { useEffect, useRef, useState } from 'react'
import {
  IMAGE_KIND_LABEL,
  IMAGE_STATUS_LABEL,
  imageContentUrl,
  imageThumbUrl,
  normalizeImageStatus,
  shortJobId,
  type ImageDTO,
} from '../../../types/workbench'

/**
 * 图库卡片（Phase 0.18 C：对齐 docs/DESIGN.md）。
 * - 瀑布流自然比例：媒体不固定高度，图片按原始宽高比排列；
 * - 左上比例标签；右上收藏 ★（多选模式改 checkbox）；
 * - hover 底部升起黑色渐变操作层：尺寸/状态 + 收藏 + 下载。
 */

interface GalleryCardProps {
  image: ImageDTO
  selected: boolean
  selectMode: boolean
  onCardClick: (image: ImageDTO) => void
  onCardDoubleClick: (image: ImageDTO) => void
  onToggleFavorite: (image: ImageDTO) => void
}

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b)
}

/** 简化宽高比为「3:4」这类比例标签；过大的非标准比例回退到「W×H」。 */
export function ratioLabel(width: number, height: number): string {
  if (!width || !height) return ''
  const divisor = gcd(width, height)
  const rw = width / divisor
  const rh = height / divisor
  if (rw <= 16 && rh <= 16) return `${rw}:${rh}`
  return `${width}×${height}`
}

export function GalleryCard({
  image, selected, selectMode, onCardClick, onCardDoubleClick, onToggleFavorite,
}: GalleryCardProps) {
  const status = normalizeImageStatus(image)
  const imported = !image.job_id
  const jobLabel = image.job_id ? shortJobId(image.job_id) : '外部导入'
  return (
    <div
      data-image-id={image.id}
      className={`gal-card${selected ? ' gal-card--selected' : ''}`}
      onClick={() => onCardClick(image)}
      onDoubleClick={() => onCardDoubleClick(image)}
      title={`${IMAGE_KIND_LABEL[image.kind] ?? image.kind} · ${jobLabel} · ${IMAGE_STATUS_LABEL[status]}`}
    >
      <GalleryThumb image={image} />
      <span className="gal-card__ratio">{ratioLabel(image.width, image.height)}</span>
      <span className="gal-card__corner">
        {selectMode && (
          <span className={`gal-card__check${selected ? ' gal-card__check--on' : ''}`} aria-hidden="true">
            {selected ? '✓' : ''}
          </span>
        )}
        {!selectMode && image.favorite && <span className="gal-card__fav" title="收藏">★</span>}
      </span>
      <span className="gal-card__overlay">
        <span className="gal-card__overlay-meta">
          {image.kind === 'upscaled' && <span className="gal-card__overlay-hd">HD</span>}
          {image.width}×{image.height} · {IMAGE_STATUS_LABEL[status]}
          {imported && <span className="gal-card__overlay-import">导入</span>}
        </span>
        <span className="gal-card__overlay-actions">
          <button
            type="button"
            className={`gal-card__action${image.favorite ? ' gal-card__action--on' : ''}`}
            title={image.favorite ? '取消收藏' : '收藏'}
            aria-label={image.favorite ? '取消收藏' : '收藏'}
            onClick={(event) => {
              event.stopPropagation()
              onToggleFavorite(image)
            }}
          >
            ★
          </button>
          <a
            className="gal-card__action"
            href={imageContentUrl(image.id)}
            download
            title="下载原图"
            aria-label="下载原图"
            onClick={(event) => event.stopPropagation()}
          >
            ↓
          </a>
        </span>
      </span>
    </div>
  )
}

/** 卡片缩略图：进入 viewport+300px 才加载，带占位 / 错误重试。
 *
 * 关键：媒体容器在图片加载前就按服务端给出的宽高比预留高度（aspect-ratio），
 * 否则占位 3:4 与真实比例（如 9:16）不一致，缩略图加载完成的瞬间卡片高度变化，
 * 整个瀑布流会上下抖动（用户反馈的"竖着刷新"）。
 */
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

  const aspectRatio = image.width > 0 && image.height > 0
    ? `${image.width} / ${image.height}`
    : undefined

  return (
    <div className="gal-card__media" ref={ref} style={aspectRatio ? { aspectRatio } : undefined}>
      {!inView ? (
        <div className="gal-card__ph" aria-hidden="true" />
      ) : error ? (
        <button
          type="button"
          className="gal-card__err"
          onClick={() => { setError(false); setRetryKey((k) => k + 1) }}
        >
          加载失败 · 重试
        </button>
      ) : (
        <img
          key={retryKey}
          className="gal-card__img"
          src={imageThumbUrl(image.id)}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setError(true)}
        />
      )}
    </div>
  )
}
