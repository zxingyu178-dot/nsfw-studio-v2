import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { ElapsedTimer } from './ElapsedTimer'

const BASE = new Date('2026-01-01T00:00:00.000Z')

function iso(ms: number): string {
  return new Date(ms).toISOString()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(BASE)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ElapsedTimer', () => {
  it('渲染"已运行 mm:ss"，fake timers 推进后每秒递增', () => {
    // 65 秒前开始
    render(<ElapsedTimer startedAt={iso(Date.now() - 65_000)} />)
    const node = screen.getByTestId('elapsed-timer')
    expect(node).toHaveTextContent('已运行 01:05')

    act(() => {
      vi.advanceTimersByTime(30_000)
    })
    expect(node).toHaveTextContent('已运行 01:35')
  })

  it('超过 1 小时显示 hh:mm:ss', () => {
    render(<ElapsedTimer startedAt={iso(Date.now() - 3661_000)} />)
    expect(screen.getByTestId('elapsed-timer')).toHaveTextContent('已运行 01:01:01')
  })

  it('只显示已运行时长，不出现 ETA / 预计完成字样', () => {
    render(<ElapsedTimer startedAt={iso(Date.now() - 120_000)} label="任务" />)
    const text = screen.getByTestId('elapsed-timer').textContent ?? ''
    expect(text).toContain('已运行 02:00')
    expect(text).not.toMatch(/预计|ETA|剩余|预计完成|还要/)
  })

  it('提供 finishedAt 时定格在该时长，推进时间也不变', () => {
    const started = Date.now() - 100_000
    const finished = Date.now() // 正好跑了 100s
    render(<ElapsedTimer startedAt={iso(started)} finishedAt={iso(finished)} />)
    const node = screen.getByTestId('elapsed-timer')
    expect(node).toHaveTextContent('已运行 01:40')

    act(() => {
      vi.advanceTimersByTime(120_000)
    })
    expect(node).toHaveTextContent('已运行 01:40')
  })
})
