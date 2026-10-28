/**
 * PromptLibraryDrawer（Phase 0.28）：从提示词库一键填入工作台。
 *
 * - 列出提示词库（搜索、最近更新优先），展示名称 + 正向摘要 + 模式；
 * - 结构化提示词：逐字段回填 structured，并切到「结构化」模式；
 * - 完整提示词：回填 fullPrompt，并切到「完整」模式；
 * - 两种模式都回填 negative_prompt，并记录 source_prompt_id/version（Provenance）。
 *
 * v0.37 P1-C：搜索 300ms 防抖 + 服务端 offset/limit 分页（不再固定只取前 50 条），
 * 切搜索词时用请求序号丢弃过期响应，保留已加载页并支持「加载更多」。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
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

export const PAGE_SIZE = 30

function excerpt(text: string, length = 72): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length > length ? `${clean.slice(0, length)}…` : clean
}

export function PromptLibraryDrawer({ open, onClose }: PromptLibraryDrawerProps) {
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<PromptDTO[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestSeq = useRef(0)

  const fetchPage = useCallback(
    (offset: number, replace: boolean) => {
      const seq = ++requestSeq.current
      const keyword = search.trim() || undefined
      if (replace) setLoading(true)
      else setLoadingMore(true)
      setError(null)
      promptApi
        .list({ search: keyword, limit: PAGE_SIZE, offset, sort: 'updated_desc' })
        .then((res) => {
          if (seq !== requestSeq.current) return
          setTotal(typeof res.total === 'number' ? res.total : offset + res.items.length)
          setItems((prev) => {
            if (replace) return res.items
            const known = new Set(prev.map((item) => item.id))
            return [...prev, ...res.items.filter((item) => !known.has(item.id))]
          })
        })
        .catch((err: unknown) => {
          if (seq !== requestSeq.current) return
          setError(err instanceof ApiRequestError ? err.message : '提示词库加载失败')
        })
        .finally(() => {
          if (seq !== requestSeq.current) return
          if (replace) setLoading(false)
          else setLoadingMore(false)
        })
    },
    [search],
  )

  useEffect(() => {
    if (!open) return
    // 搜索词变化立即作废在途请求，避免旧响应先落到新搜索的列表上。
    requestSeq.current += 1
    setItems([])
    setTotal(0)
    setLoading(true)
    setError(null)
    const timer = setTimeout(() => fetchPage(0, true), 300)
    return () => clearTimeout(timer)
  }, [open, fetchPage])

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

  const hasNext = items.length < total

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
        {!loading && !error && items.length > 0 && (
          <div className="prompt-library__foot">
            <span className="muted">已加载 {items.length} / 共 {total} 条</span>
            {hasNext && (
              <Button
                size="sm"
                variant="secondary"
                loading={loadingMore}
                onClick={() => fetchPage(items.length, false)}
              >
                加载更多
              </Button>
            )}
          </div>
        )}
      </div>
    </Drawer>
  )
}
