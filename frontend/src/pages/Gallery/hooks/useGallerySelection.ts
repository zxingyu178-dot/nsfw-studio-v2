import { useCallback, useState } from 'react'

/**
 * Phase 0.12 Task9：图库多选状态 hook（从 GalleryPage 抽取，行为不变）。
 * 进入/退出选择模式时清空已选集合；toggleSelect 单张切换。
 */
export function useGallerySelection() {
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const toggleSelect = useCallback((imageId: string) => {
    setSelectedIds((previous) =>
      previous.includes(imageId) ? previous.filter((id) => imageId !== id) : [...previous, imageId],
    )
  }, [])

  // 与原行为一致：切换按钮时清空已选
  const toggleSelectMode = useCallback(() => {
    setSelectMode((prev) => {
      setSelectedIds([])
      return !prev
    })
  }, [])

  // 显式退出选择模式（批量操作完成 / 取消选择）
  const exitSelect = useCallback(() => {
    setSelectMode(false)
    setSelectedIds([])
  }, [])

  const clearSelection = useCallback(() => setSelectedIds([]), [])

  return { selectMode, selectedIds, toggleSelect, toggleSelectMode, exitSelect, clearSelection, setSelectedIds }
}
