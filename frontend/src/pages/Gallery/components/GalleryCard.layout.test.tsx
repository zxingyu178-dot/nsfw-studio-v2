import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ImageDTO } from '../../../types/workbench'
import { GalleryCard } from './GalleryCard'

const galleryCss = readFileSync(resolve(process.cwd(), 'src/pages/Gallery/gallery.css'), 'utf8')

const portrait: ImageDTO = {
  id: 'img_portrait',
  job_id: 'job_portrait',
  job_item_id: null,
  parent_image_id: null,
  kind: 'generated',
  file_path: 'images/portrait.png',
  width: 1088,
  height: 1920,
  seed: 42,
  review_status: 'UNREVIEWED',
  favorite: false,
  source: 'comfyui',
  metadata: {},
  created_at: '2026-10-20T00:00:00Z',
  updated_at: '2026-10-20T00:00:00Z',
}

function declarationsFor(selectorFragment: string, property: string): string[] {
  return [...galleryCss.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.includes(selectorFragment))
    .flatMap(([, , declarations]) => [...declarations.matchAll(new RegExp(`${property}\\s*:\\s*([^;]+)`, 'g'))])
    .map(([, value]) => value.trim())
}

describe('GalleryCard 瀑布流布局', () => {
  it('媒体容器按服务端宽高比预留高度，图片填满容器（避免加载瞬间抖动）', () => {
    // 媒体容器高度由 aspect-ratio 决定（height:auto 不保留固定高度）。
    expect(declarationsFor('.gal-card__media', 'height')).toEqual(['auto'])
    // 图片填满容器，object-fit contain 保持完整构图；容器 aspect-ratio 由 GalleryCard inline style 提供。
    expect(declarationsFor('.gal-card__img', 'height')).toEqual(['100%'])
    expect(declarationsFor('.gal-card__img', 'object-fit')).toEqual(['contain'])
  })

  it('媒体容器 inline 设置真实宽高比，缩略图加载前后高度不变', () => {
    const { container } = render(
      <GalleryCard
        image={portrait}
        selected={false}
        selectMode={false}
        onCardClick={vi.fn()}
        onCardDoubleClick={vi.fn()}
        onToggleFavorite={vi.fn()}
      />,
    )

    const media = container.querySelector<HTMLElement>('.gal-card__media')
    expect(media?.style.aspectRatio).toBe('1088 / 1920')
  })

  it('DOM 保持媒体容器包裹图片，比例标签与 hover 覆盖层位于卡片上层', () => {
    const { container } = render(
      <div className="gal-grid gal-grid--normal">
        <GalleryCard
          image={portrait}
          selected={false}
          selectMode={false}
          onCardClick={vi.fn()}
          onCardDoubleClick={vi.fn()}
          onToggleFavorite={vi.fn()}
        />
      </div>,
    )

    act(() => {
      ;(window as unknown as { __triggerIntersection: () => void }).__triggerIntersection()
    })

    const card = container.querySelector('.gal-card')
    const media = card?.querySelector(':scope > .gal-card__media')
    const image = media?.querySelector(':scope > .gal-card__img')

    expect(media).not.toBeNull()
    expect(image).not.toBeNull()
    expect(card?.querySelector(':scope > .gal-card__ratio')).toHaveTextContent('1088×1920')
    expect(card?.querySelector(':scope > .gal-card__overlay')).not.toBeNull()
  })

  it('外部导入图片在 title 与覆盖层中显示导入标识', () => {
    const imported = { ...portrait, job_id: null }
    const { container } = render(
      <GalleryCard
        image={imported}
        selected={false}
        selectMode={false}
        onCardClick={vi.fn()}
        onCardDoubleClick={vi.fn()}
        onToggleFavorite={vi.fn()}
      />,
    )

    const card = container.querySelector('.gal-card')
    expect(card).toHaveAttribute('title', 'generated · 外部导入 · 待审核')
    expect(card?.querySelector('.gal-card__overlay-import')).toHaveTextContent('导入')
  })
})
