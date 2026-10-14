/**
 * Workbench Layout 4.0 宽度/坞状态持久化（v0.15 Task 1）。
 */
import { beforeEach, describe, expect, it } from 'vitest'
import {
  LEFT_DEFAULT,
  LEFT_MAX,
  LEFT_MIN,
  RIGHT_DEFAULT,
  RIGHT_MAX,
  RIGHT_MIN,
  __resetLayoutForTest,
  clampWidth,
  getLayoutState,
  resetLeftWidth,
  resetRightWidth,
  setDockOpen,
  setLeftWidth,
  setRightWidth,
  toggleDock,
} from './workbenchLayout'

beforeEach(() => {
  localStorage.clear()
  __resetLayoutForTest()
})

describe('clampWidth 边界', () => {
  it('左/右宽度 clamp 到各自 min/max', () => {
    expect(clampWidth(10, LEFT_MIN, LEFT_MAX)).toBe(LEFT_MIN)
    expect(clampWidth(99999, LEFT_MIN, LEFT_MAX)).toBe(LEFT_MAX)
    expect(clampWidth(300, LEFT_MIN, LEFT_MAX)).toBe(300)
    expect(clampWidth(10, RIGHT_MIN, RIGHT_MAX)).toBe(RIGHT_MIN)
    expect(clampWidth(99999, RIGHT_MIN, RIGHT_MAX)).toBe(RIGHT_MAX)
  })
})

describe('宽度持久化', () => {
  it('setLeftWidth/setRightWidth 更新状态并写 localStorage（范围内）', () => {
    setLeftWidth(360)
    setRightWidth(330)
    expect(getLayoutState().leftWidth).toBe(360)
    expect(getLayoutState().rightWidth).toBe(330)
    expect(localStorage.getItem('workbench.leftWidth')).toBe('360')
    expect(localStorage.getItem('workbench.rightWidth')).toBe('330')
  })

  it('超范围值被 clamp，不持久化越界值', () => {
    setLeftWidth(10)
    setRightWidth(99999)
    expect(getLayoutState().leftWidth).toBe(LEFT_MIN)
    expect(getLayoutState().rightWidth).toBe(RIGHT_MAX)
    expect(localStorage.getItem('workbench.leftWidth')).toBe(String(LEFT_MIN))
    expect(localStorage.getItem('workbench.rightWidth')).toBe(String(RIGHT_MAX))
  })

  it('resetLeftWidth/resetRightWidth 恢复默认', () => {
    setLeftWidth(400)
    setRightWidth(360)
    resetLeftWidth()
    resetRightWidth()
    expect(getLayoutState().leftWidth).toBe(LEFT_DEFAULT)
    expect(getLayoutState().rightWidth).toBe(RIGHT_DEFAULT)
  })
})

describe('TaskDock 展开态', () => {
  it('setDockOpen/toggleDock 切换并持久化', () => {
    expect(getLayoutState().dockOpen).toBe(false)
    toggleDock()
    expect(getLayoutState().dockOpen).toBe(true)
    expect(localStorage.getItem('workbench.taskDockOpen')).toBe('1')
    setDockOpen(false)
    expect(getLayoutState().dockOpen).toBe(false)
    expect(localStorage.getItem('workbench.taskDockOpen')).toBe('0')
  })
})
