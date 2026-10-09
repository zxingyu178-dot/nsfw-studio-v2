import { useEffect, useState } from 'react'
import { ApiRequestError, promptApi } from '../api/client'
import { Button } from './ui'
import type { PromptMode, StructuredPrompt } from '../types/workbench'
import './compose-preview.css'

interface ComposePreviewProps {
  mode: PromptMode
  structured: StructuredPrompt
  fullPrompt: string
}

/**
 * 完整 Prompt 预览（§四十）：默认折叠；调用与保存相同的后端合成规则，
 * 保证“UI 看到的 Prompt == 真正保存的 Prompt”。只读，不可直接编辑拼接结果。
 */
export function ComposePreview({ mode, structured, fullPrompt }: ComposePreviewProps) {
  const [expanded, setExpanded] = useState(false)
  const [composed, setComposed] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!expanded || mode !== 'structured') return
    const timer = window.setTimeout(() => {
      promptApi
        .compose({ mode, structured })
        .then((result) => {
          setComposed(result.composed_prompt)
          setError(null)
        })
        .catch((err: unknown) => {
          setError(err instanceof ApiRequestError ? err.message : '合成失败')
        })
    }, 250)
    return () => window.clearTimeout(timer)
  }, [expanded, mode, structured])

  const text = mode === 'structured' ? composed : fullPrompt

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="compose-preview">
      <button
        type="button"
        className="compose-preview__toggle"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        完整 Prompt 预览 <span aria-hidden="true">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="compose-preview__body">
          {mode === 'structured' && error && <p className="ds-notice ds-notice--error">{error}</p>}
          <pre className="compose-preview__text" aria-live="polite">
            {text || (mode === 'structured' ? '（结构化字段均为空）' : '（完整 Prompt 为空）')}
          </pre>
          <Button size="xs" variant="ghost" onClick={() => void handleCopy()} disabled={!text}>
            {copied ? '已复制' : '复制'}
          </Button>
        </div>
      )}
    </div>
  )
}
