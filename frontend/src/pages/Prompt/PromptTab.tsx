import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, promptApi } from '../../api/client'
import { ComposePreview } from '../../components/ComposePreview'
import { formatDateTime } from '../../utils/format'
import {
  STRUCTURED_FIELDS,
  emptyStructured,
  type PromptDTO,
  type PromptMode,
  type PromptVersionDTO,
  type StructuredPrompt,
  type WorkbenchSnapshot,
} from '../../types/workbench'

/** 我的 Prompt（规范 §三十八-§四十、§四十九、§五十四、§五十五）。 */
export function PromptTab() {
  const navigate = useNavigate()
  const [items, setItems] = useState<PromptDTO[]>([])
  const [search, setSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<{ open: boolean; prompt: PromptDTO | null }>({ open: false, prompt: null })

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    promptApi
      .list({ search: search.trim() || undefined, archived: showArchived ? null : false })
      .then((page) => setItems(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [search, showArchived])

  useEffect(() => {
    const timer = window.setTimeout(load, 250)
    return () => window.clearTimeout(timer)
  }, [load])

  function openInWorkbench(prompt: PromptDTO): void {
    setDrawer({ open: false, prompt: null })
    navigate('/generate', { state: { workbench: promptToSnapshot(prompt) } })
  }

  return (
    <div className="tab-body">
      <div className="toolbar">
        <input
          className="input toolbar__search"
          placeholder="搜索名称 / Prompt 内容"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <label className="check check--inline">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
          />
          <span>显示已归档</span>
        </label>
        <span className="toolbar__spacer" />
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setDrawer({ open: true, prompt: null })}
        >
          新建 Prompt
        </button>
      </div>

      {loading && <p className="muted">加载中…</p>}
      {error && <p className="notice notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <h1 className="empty-state__title">还没有 Prompt</h1>
          <p className="empty-state__desc">点击"新建 Prompt"，或在工作台保存当前配置。</p>
        </div>
      )}

      <div className="card-grid">
        {items.map((prompt) => (
          <article
            key={prompt.id}
            className="card card--clickable"
            onClick={() => setDrawer({ open: true, prompt })}
          >
            <header className="card__header">
              <h3 className="card__title">
                {prompt.favorite && <span title="已收藏">★ </span>}
                {prompt.name}
                {prompt.archived && <span className="badge">已归档</span>}
              </h3>
              <span className="badge badge--mode">
                {prompt.current_version?.mode === 'full' ? '完整' : '结构化'}
              </span>
            </header>
            <p className="card__excerpt">{promptSummary(prompt)}</p>
            <footer className="card__footer">{formatDateTime(prompt.updated_at)}</footer>
          </article>
        ))}
      </div>

      {drawer.open && (
        <PromptEditorDrawer
          prompt={drawer.prompt}
          onClose={() => setDrawer({ open: false, prompt: null })}
          onChanged={load}
          onOpenInWorkbench={openInWorkbench}
        />
      )}
    </div>
  )
}

function promptSummary(prompt: PromptDTO): string {
  const version = prompt.current_version
  if (!version) return '（暂无内容）'
  if (version.mode === 'full') return version.positive_prompt || '（空）'
  const parts = STRUCTURED_FIELDS.map(({ key, label }) =>
    version.structured[key] ? `${label}: ${version.structured[key]}` : null,
  ).filter(Boolean)
  return parts.join(' | ') || '（结构化字段均为空）'
}

/** Prompt 当前版本 → 统一工作台快照（规范 §四十九，复用 WorkbenchSnapshot） */
export function promptToSnapshot(prompt: PromptDTO): WorkbenchSnapshot {
  const version = prompt.current_version
  return {
    prompt_mode: version?.mode ?? 'structured',
    structured_prompt: version?.structured ?? emptyStructured(),
    full_prompt: version?.mode === 'full' ? version.positive_prompt : '',
    negative_prompt: version?.negative_prompt ?? '',
    selected_assets: {},
    width: 1024,
    height: 1024,
    count: 1,
    seed_mode: 'random',
    workflow_modules: [],
    source_prompt_id: prompt.id,
    source_prompt_version_id: version?.id ?? null,
  }
}

interface EditorDrawerProps {
  prompt: PromptDTO | null
  onClose: () => void
  /** 任一变更后由父级重新拉取列表 */
  onChanged: () => void
  onOpenInWorkbench: (prompt: PromptDTO) => void
}

function PromptEditorDrawer({ prompt, onClose, onChanged, onOpenInWorkbench }: EditorDrawerProps) {
  const isNew = prompt === null
  const [name, setName] = useState(prompt?.name ?? '')
  const [mode, setMode] = useState<PromptMode>(prompt?.current_version?.mode ?? 'structured')
  const [structured, setStructured] = useState<StructuredPrompt>(
    prompt?.current_version?.structured ?? emptyStructured(),
  )
  const [fullPrompt, setFullPrompt] = useState(
    prompt?.current_version?.mode === 'full' ? prompt.current_version.positive_prompt : '',
  )
  const [negative, setNegative] = useState(prompt?.current_version?.negative_prompt ?? '')
  const [versions, setVersions] = useState<PromptVersionDTO[]>([])
  const [viewingVersionId, setViewingVersionId] = useState<string | null>(null)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setName(prompt?.name ?? '')
    setMode(prompt?.current_version?.mode ?? 'structured')
    setStructured(prompt?.current_version?.structured ?? emptyStructured())
    setFullPrompt(prompt?.current_version?.mode === 'full' ? prompt.current_version.positive_prompt : '')
    setNegative(prompt?.current_version?.negative_prompt ?? '')
    setViewingVersionId(null)
    setMessage(null)
    if (prompt) {
      promptApi
        .listVersions(prompt.id)
        .then(setVersions)
        .catch(() => setVersions([]))
    } else {
      setVersions([])
    }
  }, [prompt])

  async function refreshDetail(promptId: string): Promise<PromptDTO> {
    const [updated, versionList] = await Promise.all([
      promptApi.get(promptId),
      promptApi.listVersions(promptId),
    ])
    setVersions(versionList)
    onChanged()
    return updated
  }

  async function run(action: () => Promise<unknown>, okText: string): Promise<void> {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      if (prompt) {
        const updated = await refreshDetail(prompt.id)
        setName(updated.name)
      }
      setMessage({ kind: 'ok', text: okText })
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof ApiRequestError ? error.message : '操作失败' })
    } finally {
      setBusy(false)
    }
  }

  async function handleSave(): Promise<void> {
    if (busy || !name.trim()) return
    if (isNew) {
      await run(
        () =>
          promptApi.create({
            name,
            mode,
            positive_prompt: mode === 'full' ? fullPrompt : '',
            negative_prompt: negative,
            structured,
          }),
        '已创建',
      )
    } else {
      await run(
        () =>
          promptApi.addVersion(prompt!.id, {
            mode,
            positive_prompt: mode === 'full' ? fullPrompt : '',
            negative_prompt: negative,
            structured,
          }),
        '已保存（内容变化创建新版本，内容不变不产生版本）',
      )
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="drawer drawer--wide"
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer__header">
          <h3 className="drawer__title">{isNew ? '新建 Prompt' : `编辑：${prompt!.name}`}</h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="关闭">✕</button>
        </header>

        {!isNew && prompt && (
          <div className="drawer__meta-actions">
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => void run(() => promptApi.updateMeta(prompt.id, { favorite: !prompt.favorite }), '已更新收藏')}
            >
              {prompt.favorite ? '★ 已收藏' : '☆ 收藏'}
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => onOpenInWorkbench(prompt)}>
              在生成工作台打开
            </button>
            {prompt.archived ? (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => void run(() => promptApi.restore(prompt.id), '已从归档恢复')}
              >
                恢复
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => void run(() => promptApi.archive(prompt.id), '已归档（软删除）')}
              >
                归档
              </button>
            )}
          </div>
        )}

        <div className="field">
          <label className="field__label" htmlFor="prompt-name">名称</label>
          <input id="prompt-name" className="input" value={name} onChange={(event) => setName(event.target.value)} />
        </div>

        <div className="segmented segmented--block">
          <button
            type="button"
            className={`segmented__item${mode === 'structured' ? ' segmented__item--active' : ''}`}
            onClick={() => setMode('structured')}
          >
            结构化 Prompt
          </button>
          <button
            type="button"
            className={`segmented__item${mode === 'full' ? ' segmented__item--active' : ''}`}
            onClick={() => setMode('full')}
          >
            完整 Prompt
          </button>
        </div>

        {mode === 'structured' ? (
          <div className="structured-editor">
            {STRUCTURED_FIELDS.map(({ key, label }) => (
              <div key={key} className="field">
                <label className="field__label" htmlFor={`p-edit-${key}`}>{label}</label>
                <textarea
                  id={`p-edit-${key}`}
                  className="input input--area"
                  rows={2}
                  value={structured[key]}
                  onChange={(event) => setStructured({ ...structured, [key]: event.target.value })}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="field">
            <label className="field__label" htmlFor="p-edit-full">完整 Prompt</label>
            <textarea
              id="p-edit-full"
              className="input input--area"
              rows={10}
              value={fullPrompt}
              onChange={(event) => setFullPrompt(event.target.value)}
            />
          </div>
        )}

        <div className="field">
          <label className="field__label" htmlFor="p-edit-negative">Negative Prompt</label>
          <textarea
            id="p-edit-negative"
            className="input input--area"
            rows={3}
            value={negative}
            onChange={(event) => setNegative(event.target.value)}
          />
        </div>

        <ComposePreview mode={mode} structured={structured} fullPrompt={fullPrompt} />

        <div className="pane__footer">
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy || !name.trim()}
            onClick={() => void handleSave()}
          >
            {isNew ? '创建' : '保存为新版本'}
          </button>
        </div>

        {message && <p className={`notice notice--${message.kind}`} role="status">{message.text}</p>}

        {!isNew && (
          <section className="version-history">
            <h4 className="version-history__title">版本历史（不可变；恢复 = 复制为新最新版）</h4>
            {versions.length === 0 && <p className="muted">暂无版本</p>}
            <ul className="version-history__list">
              {versions.map((version) => (
                <li key={version.id} className="version-history__item">
                  <div className="version-history__row">
                    <span className="version-history__no">v{version.version_no}</span>
                    <span className="badge badge--mode">{version.mode === 'full' ? '完整' : '结构化'}</span>
                    <span className="muted">{formatDateTime(version.created_at)}</span>
                    {prompt!.current_version?.id === version.id && <span className="badge">当前</span>}
                    <span className="toolbar__spacer" />
                    <button
                      type="button"
                      className="btn btn--ghost btn--xs"
                      onClick={() =>
                        setViewingVersionId(viewingVersionId === version.id ? null : version.id)
                      }
                    >
                      {viewingVersionId === version.id ? '收起' : '查看'}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--xs"
                      disabled={busy || prompt!.current_version?.id === version.id}
                      onClick={() =>
                        void run(
                          () => promptApi.restoreVersion(prompt!.id, version.id),
                          `已恢复 v${version.version_no}（生成新版本）`,
                        )
                      }
                    >
                      恢复为新版本
                    </button>
                  </div>
                  {viewingVersionId === version.id && (
                    <pre className="version-history__content">
                      {version.mode === 'full'
                        ? version.positive_prompt
                        : STRUCTURED_FIELDS.map(({ key, label }) =>
                            version.structured[key] ? `${label}: ${version.structured[key]}` : null,
                          )
                            .filter(Boolean)
                            .join('\n') || '（空）'}
                      {version.negative_prompt && `\n--- Negative ---\n${version.negative_prompt}`}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
  )
}
