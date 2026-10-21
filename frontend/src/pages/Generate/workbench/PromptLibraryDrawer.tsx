/**
 * PromptLibraryDrawer（Phase 0.28）：从提示词库一键填入工作台。
 *
 * - 列出提示词库（搜索、最近更新优先），展示名称 + 正向摘要 + 模式；
 * - 结构化提示词：逐字段回填 structured，并切到「结构化」模式；
 * - 完整提示词：回填 fullPrompt，并切到「完整」模式；
 * - 两种模式都回填 negative_prompt，并记录 source_prompt_id/version（Provenance）。
 */
import { useEffect, useState } from 'react'
import { promptApi, ApiRequestError } from '../../../api/client'
import { Button, Drawer, Input, Spinner } from '../../../components/ui'
import {
  setFullPrompt,
  setNegativePrompt,
  setPromptMode,
  setSourcePrompt,
  setStructuredField,
} from '../../../stores/workbenchStore'
import { STRUCTURED_FIELDS, type PromptDTO } from '../../../types/workbench'

export interface PromptLibraryDrawerProps {
  open: boolean
  onClose: () => void
}

function excerpt(text: string, length = 72): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length > length ? `${clean.slice(0, length)}…` : clean
}

export function PromptLibraryDrawer({ open, onClose }: PromptLibraryDrawerProps) {
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<PromptDTO[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const timer = setTimeout(() => {
      promptApi
        .list({ search: search.trim() || undefined, limit: 50, sort: 'updated_desc' })
        .then((res) => {
          if (cancelled) return
          setItems(res.items ?? [])
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setError(err instanceof ApiRequestError ? err.message : '提示词库加载失败')
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [open, search])

  function applyPrompt(prompt: PromptDTO): void {
    const version = prompt.current_version
    if (!version) return
    if (version.mode === 'structured') {
      const structured = version.structured
      if (structured) {
        for (const { key } of STRUCTURED_FIELDS) {
          const value = structured[key]
          if (typeof value === 'string') setStructuredField(key, value)
        }
      }
      setPromptMode('structured')
    } else {
      setFullPrompt(version.positive_prompt ?? '')
      setPromptMode('full')
    }
    setNegativePrompt(version.negative_prompt ?? '')
    setSourcePrompt(prompt.id, version.id)
    onClose()
  }

  return (
    <Drawer open={open} onClose={onClose} title="从提示词库填入" width="wide">
      <div className="prompt-library">
        <Input
          className="prompt-library__search"
          type="search"
          aria-label="搜索提示词库"
          placeholder="搜索名称 / Prompt 内容…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          autoFocus
        />
        {error && <p className="ds-notice ds-notice--error" role="alert">{error}</p>}
        {loading && <Spinner ariaLabel="提示词库加载中" />}
        {!loading && !error && items.length === 0 && (
          <p className="muted">提示词库为空，先去「提示词」页新建或导入。</p>
        )}
        <ul className="prompt-library__list">
          {items.map((prompt) => {
            const version = prompt.current_version
            const positive = version?.positive_prompt ?? ''
            const modeLabel = version?.mode === 'structured' ? '结构化' : '完整'
            return (
              <li key={prompt.id} className="prompt-library__item">
                <button
                  type="button"
                  className="prompt-library__pick"
                  onClick={() => applyPrompt(prompt)}
                  disabled={!version}
                >
                  <span className="prompt-library__head">
                    <span className="prompt-library__name">{prompt.name}</span>
                    <span className="prompt-library__mode">{modeLabel}</span>
                    {prompt.favorite && <span className="prompt-library__fav" aria-label="收藏">★</span>}
                  </span>
                  <span className="prompt-library__excerpt">{excerpt(positive) || '（无正向内容）'}</span>
                </button>
                <Button size="sm" variant="secondary" onClick={() => applyPrompt(prompt)} disabled={!version}>
                  填入
                </Button>
              </li>
            )
          })}
        </ul>
      </div>
    </Drawer>
  )
}
