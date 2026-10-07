import { useState } from 'react'
import { setCount, setSize, useWorkbench } from '../../stores/workbenchStore'

/** 右栏：基础配置（规范 §四十四）。模型/队列仅显示占位文案，不制造虚假状态。 */
export function SettingsPane() {
  const state = useWorkbench()
  const [widthText, setWidthText] = useState(String(state.width))
  const [heightText, setHeightText] = useState(String(state.height))

  function commitSize(): void {
    const width = clampDimension(widthText)
    const height = clampDimension(heightText)
    setWidthText(String(width))
    setHeightText(String(height))
    setSize(width, height)
  }

  return (
    <div className="pane">
      <header className="pane__header">
        <h2 className="pane__title">基础配置</h2>
      </header>

      <div className="field">
        <label className="field__label" htmlFor="size-width">宽度 (px)</label>
        <input
          id="size-width"
          className="input"
          type="number"
          min={64}
          max={4096}
          step={64}
          value={widthText}
          onChange={(event) => setWidthText(event.target.value)}
          onBlur={commitSize}
        />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="size-height">高度 (px)</label>
        <input
          id="size-height"
          className="input"
          type="number"
          min={64}
          max={4096}
          step={64}
          value={heightText}
          onChange={(event) => setHeightText(event.target.value)}
          onBlur={commitSize}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="gen-count">数量</label>
        <select
          id="gen-count"
          className="input"
          value={state.count}
          onChange={(event) => setCount(Number(event.target.value))}
        >
          {[1, 2, 4, 6, 8].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>

      <div className="field">
        <span className="field__label">Seed</span>
        <p className="field__static">随机</p>
      </div>

      <div className="field">
        <span className="field__label">模型</span>
        <p className="field__static field__static--muted">未接入生成引擎</p>
      </div>

      <div className="field">
        <span className="field__label">队列</span>
        <p className="field__static field__static--muted">任务系统将在后续阶段接入</p>
      </div>
    </div>
  )
}

function clampDimension(text: string): number {
  const value = Number.parseInt(text, 10)
  if (Number.isNaN(value)) return 1024
  return Math.min(4096, Math.max(64, value))
}
