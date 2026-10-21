export function distributeColumns<T>(
  items: readonly T[],
  columnCount: number,
  aspectOf: (item: T) => number,
): T[][] {
  const count = Math.max(1, Math.floor(columnCount) || 1)
  const columns = Array.from({ length: count }, () => [] as T[])
  const heights = Array.from({ length: count }, () => 0)

  for (const item of items) {
    let target = 0
    for (let index = 1; index < count; index += 1) {
      if (heights[index] < heights[target]) target = index
    }
    columns[target].push(item)
    const aspect = aspectOf(item)
    heights[target] += Number.isFinite(aspect) && aspect > 0 ? aspect : 1
  }

  return columns
}
