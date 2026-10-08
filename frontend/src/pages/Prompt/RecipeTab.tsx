import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, recipeApi } from '../../api/client'
import { formatDateTime } from '../../utils/format'
import {
  ASSET_TYPE_LABEL,
  emptyStructured,
  imageContentUrl,
  type RecipeDTO,
  type RecipeVersionDTO,
  type WorkbenchSnapshot,
} from '../../types/workbench'

/** 配方 Tab（规范 §五十）：列表 + 版本历史 + 在生成工作台打开。 */
export function RecipeTab() {
  const navigate = useNavigate()
  const [items, setItems] = useState<RecipeDTO[]>([])
  const [search, setSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<{ open: boolean; recipe: RecipeDTO | null }>({ open: false, recipe: null })

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    recipeApi
      .list({ search: search.trim() || undefined, archived: showArchived ? null : false })
      .then((page) => setItems(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [search, showArchived])

  useEffect(() => {
    const timer = window.setTimeout(load, 250)
    return () => window.clearTimeout(timer)
  }, [load])

  function openInWorkbench(recipe: RecipeDTO): void {
    setDrawer({ open: false, recipe: null })
    navigate('/generate', {
      state: { workbench: recipeToSnapshot(recipe.current_version), sourceRecipeId: recipe.id },
    })
  }

  return (
    <div className="tab-body">
      <div className="toolbar">
        <input
          className="input toolbar__search"
          placeholder="搜索配方名称 / Prompt"
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
        <p className="muted">配方在生成工作台通过"保存为配方"创建</p>
      </div>

      {loading && <p className="muted">加载中…</p>}
      {error && <p className="notice notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <h1 className="empty-state__title">还没有配方</h1>
          <p className="empty-state__desc">在生成工作台配置 Prompt 与素材后，点击"保存为配方"。</p>
        </div>
      )}

      <div className="card-grid">
        {items.map((recipe) => {
          const version = recipe.current_version
          return (
            <article
              key={recipe.id}
              className="card card--clickable"
              onClick={() => setDrawer({ open: true, recipe })}
            >
              <header className="card__header">
                <h3 className="card__title">
                  {recipe.favorite && <span title="已收藏">★ </span>}
                  {recipe.name}
                  {recipe.archived && <span className="badge">已归档</span>}
                </h3>
                <span className="badge badge--mode">{version?.prompt_mode === 'full' ? '完整' : '结构化'}</span>
              </header>
              <p className="card__excerpt">
                {version
                  ? `${version.asset_snapshots.length ? version.asset_snapshots.map((s) => `${ASSET_TYPE_LABEL[s.slot]}: ${s.asset_name}`).join(' | ') || '无素材' : '无素材'} · ${version.generation_settings.width}×${version.generation_settings.height} · ${version.default_count} 张`
                  : '（暂无版本）'}
              </p>
              <footer className="card__footer">{formatDateTime(recipe.updated_at)}</footer>
            </article>
          )
        })}
      </div>

      {drawer.open && drawer.recipe && (
        <RecipeDrawer
          recipe={drawer.recipe}
          onClose={() => setDrawer({ open: false, recipe: null })}
          onChanged={load}
          onOpenInWorkbench={openInWorkbench}
        />
      )}
    </div>
  )
}

/** RecipeVersion → 统一工作台快照（规范 §五十：Workflow Snapshot 为空也走同一结构） */
export function recipeToSnapshot(version: RecipeVersionDTO | null): WorkbenchSnapshot {
  if (!version) {
    return {
      prompt_mode: 'structured',
      structured_prompt: emptyStructured(),
      full_prompt: '',
      negative_prompt: '',
      selected_assets: {},
      width: 1024,
      height: 1024,
      count: 1,
      seed_mode: 'random',
      workflow_modules: [],
    }
  }
  const selected: WorkbenchSnapshot['selected_assets'] = {}
  for (const snapshot of version.asset_snapshots) {
    selected[snapshot.slot] = {
      asset_id: snapshot.asset_id,
      asset_version_id: snapshot.asset_version_id,
      name: snapshot.asset_name,
    }
  }
  return {
    prompt_mode: version.prompt_mode,
    structured_prompt: version.structured_prompt,
    full_prompt: version.prompt_mode === 'full' ? version.positive_prompt_snapshot : '',
    negative_prompt: version.negative_prompt_snapshot,
    selected_assets: selected,
    width: version.generation_settings.width,
    height: version.generation_settings.height,
    count: version.default_count,
    seed_mode: 'random',
    workflow_modules: version.workflow_snapshot.modules,
    // §九：输入图关系原样恢复（missing 标记随快照进入工作台，显式提示不静默清空）
    input_images: (version.input_images ?? []).map((ref) => ({
      role: 'source' as const,
      image_id: ref.image_id,
      missing: ref.missing,
    })),
    source_prompt_id: version.source_prompt_id,
    source_prompt_version_id: version.source_prompt_version_id,
  }
}

interface RecipeDrawerProps {
  recipe: RecipeDTO
  onClose: () => void
  onChanged: () => void
  onOpenInWorkbench: (recipe: RecipeDTO) => void
}

function RecipeDrawer({ recipe, onClose, onChanged, onOpenInWorkbench }: RecipeDrawerProps) {
  const [versions, setVersions] = useState<RecipeVersionDTO[]>([])
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState(recipe.name)

  useEffect(() => {
    setName(recipe.name)
    recipeApi
      .listVersions(recipe.id)
      .then(setVersions)
      .catch(() => setVersions([]))
  }, [recipe])

  async function run(action: () => Promise<unknown>, okText: string): Promise<void> {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      setVersions(await recipeApi.listVersions(recipe.id))
      onChanged()
      setMessage({ kind: 'ok', text: okText })
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof ApiRequestError ? error.message : '操作失败' })
    } finally {
      setBusy(false)
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
          <h3 className="drawer__title">配方：{recipe.name}</h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="关闭">✕</button>
        </header>

        <div className="drawer__meta-actions">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => void run(() => recipeApi.updateMeta(recipe.id, { favorite: !recipe.favorite }), '已更新收藏')}
          >
            {recipe.favorite ? '★ 已收藏' : '☆ 收藏'}
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => onOpenInWorkbench(recipe)}>
            在生成工作台打开
          </button>
          {recipe.archived ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => void run(() => recipeApi.restore(recipe.id), '已从归档恢复')}
            >
              恢复
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => void run(() => recipeApi.archive(recipe.id), '已归档（软删除）')}
            >
              归档
            </button>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="recipe-name">名称</label>
          <input
            id="recipe-name"
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => {
              if (name.trim() && name.trim() !== recipe.name) {
                void run(() => recipeApi.updateMeta(recipe.id, { name: name.trim() }), '已重命名')
              }
            }}
          />
        </div>

        {message && <p className={`notice notice--${message.kind}`} role="status">{message.text}</p>}

        <section className="version-history">
          <h4 className="version-history__title">版本历史（快照不可变；恢复 = 复制为新最新版）</h4>
          {versions.length === 0 && <p className="muted">暂无版本</p>}
          <ul className="version-history__list">
            {versions.map((version) => (
              <li key={version.id} className="version-history__item">
                <div className="version-history__row">
                  <span className="version-history__no">v{version.version_no}</span>
                  <span className="badge badge--mode">{version.prompt_mode === 'full' ? '完整' : '结构化'}</span>
                  <span className="muted">{formatDateTime(version.created_at)}</span>
                  {recipe.current_version?.id === version.id && <span className="badge">当前</span>}
                  <span className="toolbar__spacer" />
                  <button
                    type="button"
                    className="btn btn--ghost btn--xs"
                    onClick={() => setViewingId(viewingId === version.id ? null : version.id)}
                  >
                    {viewingId === version.id ? '收起' : '查看'}
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--xs"
                    disabled={busy}
                    onClick={() =>
                      void run(
                        () => recipeApi.restoreVersion(recipe.id, version.id),
                        `已恢复 v${version.version_no}（生成新版本，快照原样复制）`,
                      )
                    }
                  >
                    恢复为新版本
                  </button>
                </div>
                {viewingId === version.id && (
                  <div className="version-history__content">
                    <p className="muted">
                      {version.prompt_mode === 'full'
                        ? '完整 Prompt 模式'
                        : '结构化 Prompt 模式'}
                      {' · '}
                      {version.generation_settings.width}×{version.generation_settings.height}
                      {' · '}
                      {version.default_count} 张 · Seed 随机
                    </p>
                    <pre className="version-history__content">
                      {version.prompt_mode === 'full'
                        ? version.positive_prompt_snapshot
                        : Object.entries(version.structured_prompt)
                            .filter(([, value]) => value)
                            .map(([key, value]) => `${key}: ${value}`)
                            .join('\n') || '（结构化字段均为空）'}
                    </pre>
                    {version.negative_prompt_snapshot && (
                      <pre className="version-history__content">
                        --- Negative ---{'\n'}
                        {version.negative_prompt_snapshot}
                      </pre>
                    )}
                    <p className="muted">素材快照：</p>
                    <ul className="muted">
                      {version.asset_snapshots.length === 0 && <li>无</li>}
                      {version.asset_snapshots.map((snapshot) => (
                        <li key={snapshot.id}>
                          {ASSET_TYPE_LABEL[snapshot.slot]} · {snapshot.asset_name} · prompt: {snapshot.prompt || '（空）'}
                        </li>
                      ))}
                    </ul>
                    <p className="muted">输入图片：</p>
                    <ul className="muted">
                      {(version.input_images ?? []).length === 0 && <li>无</li>}
                      {(version.input_images ?? []).map((ref) => (
                        <li key={ref.image_id} className="version-history__input-image">
                          {!ref.missing && <img src={imageContentUrl(ref.image_id)} alt="" />}
                          <span>
                            {ref.role === 'source' ? '来源' : ref.role} · {ref.image_id}
                            {ref.missing && <strong>（输入图片已丢失）</strong>}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  )
}
