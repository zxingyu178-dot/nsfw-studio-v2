import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ImageDTO } from '../../../types/workbench'
import type { GalleryDensity } from '../hooks/useGalleryPrefs'
import { GalleryGrid } from './GalleryGrid'

vi.mock('./GalleryCard', () => ({
  GalleryCard: ({ image }: { image: ImageDTO }) => <div className="gal-card" data-image-id={image.id} />,
}))

let resizeCallback: ResizeObserverCallback

class MockResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

function image(id: string, width: number, height: number): ImageDTO {
  return {
    id,
    job_id: `job_${id}`,
    job_item_id: null,
    parent_image_id: null,
    kind: 'generated',
    file_path: `images/${id}.png`,
    width,
    height,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite: false,
    source: 'comfyui',
    metadata: {},
    created_at: '2026-10-21T00:00:00Z',
    updated_at: '2026-10-21T00:00:00Z',
  }
}

const handlers = {
  onCardClick: vi.fn(),
  onCardDoubleClick: vi.fn(),
  onToggleFavorite: vi.fn(),
}

function renderGrid(
  items: ImageDTO[],
  sentinelRef = { current: null as HTMLDivElement | null },
  density: GalleryDensity = 'normal',
) {
  return render(
    <GalleryGrid
      items={items}
      total={items.length}
      hasNext
      loading={false}
      loadingMore={false}
      selectedIds={[]}
      selectMode={false}
      density={density}
      fit="contain"
      sentinelRef={sentinelRef}
      {...handlers}
    />,
  )
}

function resize(width: number) {
  act(() => {
    resizeCallback([
      { contentRect: { width } } as ResizeObserverEntry,
    ], {} as ResizeObserver)
  })
}

function columnIds(container: HTMLElement): string[][] {
  return [...container.querySelectorAll('.gal-col')].map((column) =>
    [...column.querySelectorAll<HTMLElement>('[data-image-id]')].map((card) => card.dataset.imageId!),
  )
}

function cardPosition(columns: string[][], id: string): [number, number] {
  const columnIndex = columns.findIndex((column) => column.includes(id))
  return [columnIndex, columns[columnIndex].indexOf(id)]
}

describe('GalleryGrid stable columns', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the measured number of equal column wrappers without duplicate cards', () => {
    const items = [image('a', 100, 100), image('b', 100, 200), image('c', 200, 100), image('d', 100, 100)]
    const { container } = renderGrid(items)

    resize(684)

    expect(container.querySelectorAll('.gal-col')).toHaveLength(3)
    expect(columnIds(container)).toEqual([['a'], ['b', 'd'], ['c']])
    const renderedIds = columnIds(container).flat()
    expect(renderedIds).toHaveLength(items.length)
    expect(new Set(renderedIds)).toEqual(new Set(items.map((item) => item.id)))
  })

  it('keeps existing card column positions when items are appended at the same column count', () => {
    const initial = [image('a', 100, 300), image('b', 100, 100), image('c', 100, 100)]
    const sentinelRef = { current: null as HTMLDivElement | null }
    const view = renderGrid(initial, sentinelRef)
    resize(452)
    const before = columnIds(view.container)

    view.rerender(
      <GalleryGrid
        items={[...initial, image('d', 100, 100), image('e', 100, 100)]}
        total={5}
        hasNext
        loading={false}
        loadingMore={false}
        selectedIds={[]}
        selectMode={false}
        density="normal"
        fit="contain"
        sentinelRef={sentinelRef}
        {...handlers}
      />,
    )

    const after = columnIds(view.container)
    for (const id of initial.map((item) => item.id)) {
      expect(cardPosition(after, id)).toEqual(cardPosition(before, id))
    }
    expect(after.flat()).toHaveLength(5)
  })

  it.each([
    ['compact', 534, 3],
    ['large', 584, 2],
  ] as const)('uses the %s target width to derive %i columns', (density, width, expectedColumns) => {
    const { container } = renderGrid([image('a', 100, 100)], undefined, density)

    resize(width)

    expect(container.querySelectorAll('.gal-col')).toHaveLength(expectedColumns)
  })

  it('preserves the infinite-scroll sentinel', () => {
    const sentinelRef = { current: null as HTMLDivElement | null }
    const { container } = renderGrid([image('a', 100, 100)], sentinelRef)

    expect(container.querySelector('.gal-sentinel')).toBe(sentinelRef.current)
  })
})
