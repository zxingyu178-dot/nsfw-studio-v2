import { useState } from 'react'

/** 中栏：Phase 1 不产生任何生成结果（规范 §二、§四十四）。 */
export function ResultPane() {
  const [notice, setNotice] = useState<string | null>(null)

  function handleGenerateClick(): void {
    setNotice('生成引擎尚未接入')
  }

  return (
    <div className="pane pane--center">
      <header className="pane__header">
        <h2 className="pane__title">预览</h2>
      </header>

      <div className="result-placeholder">
        <div className="empty-state__badge">Coming Soon</div>
        <p className="result-placeholder__text">暂无生成结果</p>
        <p className="muted">生成引擎接入后，结果与缩略图将显示在这里。</p>
      </div>

      {notice && (
        <p className="notice notice--warn" role="alert">{notice}</p>
      )}

      <div className="result-pane__actions">
        <button type="button" className="btn btn--primary btn--lg" onClick={handleGenerateClick}>
          生成
        </button>
      </div>
      <p className="muted result-pane__hint">结构化 Prompt 最终内容由后端统一合成，可在左栏"完整 Prompt 预览"查看。</p>
    </div>
  )
}
