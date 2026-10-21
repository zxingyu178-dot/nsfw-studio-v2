import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ImageDTO } from '../../../types/workbench'
import { GalleryCard } from './GalleryCard'

const galleryCss = readFileSync(resolve(process.cwd(), 'src/pages/Gallery/gallery.css'), 'utf8')

const image: ImageDTO = {
  id: 'img_perf',
  job_id: 'job_perf',
  job_item_id: null,
  parent_image_id: null,
  kind: 'generated',
  file_path: 'images/perf.png',
  width: 768,
  height: 1024,
  seed: 42,
  review_status: 'UNREVIEWED',
  favorite: false,
  source: 'comfyui',
  metadata: {},
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
}

function finalRule(selector: string): string {
  const cssWithoutComments = galleryCss.replace(/\/\*[\s\S]*?\*\//g, '')
  const matches = [...cssWithoutComments.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, ruleSelector]) => ruleSelector.trim() === selector)
  return matches.at(-1)?.[2] ?? ''
}

describe('GalleryCard performance guards', () => {
  it('keeps the card structure and decodes the observed thumbnail asynchronously', () => {
    const { container } = render(
      <GalleryCard
        image={image}
        selected={false}
        selectMode={false}
        onCardClick={vi.fn()}
        onCardDoubleClick={vi.fn()}
        onToggleFavorite={vi.fn()}
      />,
    )

    const card = container.querySelector(':scope > .gal-card')
    expect(card).not.toBeNull()
    expect(card?.querySelector(':scope > .gal-card__media')).not.toBeNull()
    expect(card?.querySelector('.gal-card__img')).toBeNull()

    act(() => {
      ;(window as unknown as { __triggerIntersection: () => void }).__triggerIntersection()
    })

    const thumbnail = card?.querySelector(':scope > .gal-card__media > img.gal-card__img')
    expect(thumbnail).not.toBeNull()
    expect(thumbnail).toHaveAttribute('loading', 'lazy')
    expect(thumbnail).toHaveAttribute('decoding', 'async')
  })

  it('不从卡片层使用 content-visibility（避免 intrinsic-size 估算导致进入视口时跳动）', () => {
    const cardRule = finalRule('.gal-card')
    expect(cardRule).not.toMatch(/content-visibility/)
    expect(cardRule).not.toMatch(/contain-intrinsic-size/)
  })

  it('contains gallery grid layout and painting', () => {
    expect(finalRule('.gal-grid')).toMatch(/contain\s*:\s*layout\s+paint\s*;/)
  })
})
