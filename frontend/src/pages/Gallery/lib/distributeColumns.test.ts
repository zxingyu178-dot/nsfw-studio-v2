import { describe, expect, it } from 'vitest'
import { distributeColumns } from './distributeColumns'

describe('distributeColumns', () => {
  it('uses the lowest estimated column and resolves equal heights by column index', () => {
    const items = [
      { id: 'a', aspect: 1 },
      { id: 'b', aspect: 1 },
      { id: 'c', aspect: 1 },
      { id: 'd', aspect: 1 },
      { id: 'e', aspect: 1 },
    ]

    expect(distributeColumns(items, 2, (item) => item.aspect).map((column) => column.map((item) => item.id)))
      .toEqual([['a', 'c', 'e'], ['b', 'd']])
  })

  it('is deterministic and does not mutate its input', () => {
    const items = [
      { id: 'wide', aspect: 0.5 },
      { id: 'portrait', aspect: 2 },
      { id: 'square', aspect: 1 },
    ]
    const snapshot = [...items]

    const first = distributeColumns(items, 3, (item) => item.aspect)
    const second = distributeColumns(items, 3, (item) => item.aspect)

    expect(first).toEqual(second)
    expect(items).toEqual(snapshot)
  })

  it('keeps estimated column heights balanced by greedy placement', () => {
    const items = [1.8, 1.4, 1.2, 1, 0.8, 0.7, 0.6, 0.5]
    const columns = distributeColumns(items, 3, (aspect) => aspect)
    const heights = columns.map((column) => column.reduce((sum, aspect) => sum + aspect, 0))

    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(Math.max(...items))
    expect(columns.flat()).toHaveLength(items.length)
  })

  it('keeps every existing column and in-column index when a suffix is appended', () => {
    const prefix = [1.8, 0.6, 1.1, 0.9, 1.4]
    const before = distributeColumns(prefix, 3, (aspect) => aspect)
    const after = distributeColumns([...prefix, 0.7, 1.2], 3, (aspect) => aspect)

    prefix.forEach((aspect, itemIndex) => {
      const beforeColumn = before.findIndex((column) => column.includes(aspect))
      const afterColumn = after.findIndex((column) => column.includes(aspect))
      expect(afterColumn).toBe(beforeColumn)
      expect(after[afterColumn].indexOf(aspect)).toBe(before[beforeColumn].indexOf(aspect))
      expect(after[afterColumn][before[beforeColumn].indexOf(aspect)]).toBe(prefix[itemIndex])
    })
  })

  it('always creates at least one column', () => {
    expect(distributeColumns(['a', 'b'], 0, () => 1)).toEqual([['a', 'b']])
  })
})
