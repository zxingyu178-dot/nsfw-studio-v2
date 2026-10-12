import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, promptApi } from '../../api/client'
import { ComposePreview } from '../../components/ComposePreview'
import { ImagePickerDrawer } from '../../components/ImagePickerDrawer'
import {
  Badge,
  Button,
  Checkbox,
  Drawer,
  Field,
  Input,
  SegmentedControl,
  Textarea,
} from '../../components/ui'
import { formatDateTime } from '../../utils/format'
import {
  STRUCTURED_FIELDS,
  emptyStructured,
  imageContentUrl,
  imageThumbUrl,
  type PromptDTO,
  type PromptMode,
  type PromptVersionDTO,
  type StructuredPrompt,
  type WorkbenchSnapshot,
} from '../../types/workbench'

/** 我的 Prompt（§三十八-§四十、§四十九、§五十四、§五十五）。 */
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
    <div>
      <div className="pp-toolbar">
        <Input
          placeholder="搜索名称 / Prompt 内容"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Checkbox
          label="显示已归档"
          checked={showArchived}
          onChange={(event) => setShowArchived(event.target.checked)}
        />
        <span className="pp-toolbar__spacer" />
        <Button variant="primary" onClick={() => setDrawer({ open: true, prompt: null })}>
          新建 Prompt
        </Button>
      </div>

      {loading && <p className="muted">加载中…</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="pp-empty">
          <h2 className="pp-empty__title">还没有 Prompt</h2>
          <p className="muted">点击“新建 Prompt”，或在工作台保存当前配置。</p>
        </div>
      )}

      <div className="pp-grid">
        {items.map((prompt) => (
          <PromptCard key={prompt.id} prompt={prompt} onOpen={(p) => setDrawer({ open: true, prompt: p })} />
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

/** Prompt 当前版本 → 统一工作台快照（§四十九） */
export function promptToSnapshot(prompt: PromptDTO): WorkbenchSnapshot {
  const version = prompt.current_version
  return {
    prompt_mode: version?.mode ?? 'structured',
    structured_prompt: version?.structured ?? emptyStructured(),
    full_prompt: version?.mode === 'full' ? version.positive_prompt : '',
    negative_prompt: version?.negative_prompt ?? '',
    selected_assets: {},
    generation_mode: 'text',
    width: 1024,
    height: 1024,
    count: 1,
    seed_mode: 'random',
    workflow_modules: [],
    source_prompt_id: prompt.id,
    source_prompt_version_id: version?.id ?? null,
  }
}

interface PromptCardProps {
  prompt: PromptDTO
  onOpen: (prompt: PromptDTO) => void
}

/** Prompt 卡片：封面缩略图 + 一键复制【当前版本完整 positive_prompt】（不打开抽屉）。 */
function PromptCard({ prompt, onOpen }: PromptCardProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy(event: React.MouseEvent<HTMLButtonElement>): Promise<void> {
    // 阻止冒泡：点击复制按钮绝不能打开编辑抽屉
    event.stopPropagation()
    event.preventDefault()
    const text = prompt.current_version?.positive_prompt ?? ''
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // 剪贴板权限不可用时仅做 UI 反馈，不阻断卡片
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <article className="pp-card" onClick={() => onOpen(prompt)}>
      {prompt.preview_image_id ? (
        <img
          className="pp-card__cover"
          src={imageThumbUrl(prompt.preview_image_id)}
          loading="lazy"
          alt=""
        />
      ) : (
        <div className="pp-card__cover pp-card__cover--empty">无封面</div>
      )}
      <header className="pp-card__head">
        <h3 className="pp-card__title">
          {prompt.favorite && <span title="已收藏">★ </span>}
          {prompt.name}
          {prompt.archived && <Badge>已归档</Badge>}
        </h3>
        <Badge tone="accent">
          {prompt.current_version?.mode === 'full' ? '完整' : '结构化'}
        </Badge>
      </header>
      <p className="pp-card__excerpt">{promptSummary(prompt)}</p>
      <footer className="pp-card__foot">
        <span className="pp-card__time">{formatDateTime(prompt.updated_at)}</span>
        <button
          type="button"
          className="pp-card__copy"
          title="复制当前版本完整 Prompt"
          onClick={(event) => void handleCopy(event)}
        >
          {copied ? '已复制' : '复制'}
        </button>
      </footer>
    </article>
  )
}

interface EditorDrawerProps {
  prompt: PromptDTO | null
  onClose: () => void
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
  const [coverImageId, setCoverImageId] = useState<string | null>(prompt?.preview_image_id ?? null)
  const [pickerOpen, setPickerOpen] = useState(false)

  useEffect(() => {
    setName(prompt?.name ?? '')
    setMode(prompt?.current_version?.mode ?? 'structured')
    setStructured(prompt?.current_version?.structured ?? emptyStructured())
    setFullPrompt(prompt?.current_version?.mode === 'full' ? prompt.current_version.positive_prompt : '')
    setNegative(prompt?.current_version?.negative_prompt ?? '')
    setViewingVersionId(null)
    setMessage(null)
    setCoverImageId(prompt?.preview_image_id ?? null)
    setPickerOpen(false)
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
        setCoverImageId(updated.preview_image_id)
      } else {
        // 新建 Prompt：刷新外层列表，使新卡片立即出现（否则需手动刷新页面）
        onChanged()
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

  async function handlePickCover(imageId: string): Promise<void> {
    setPickerOpen(false)
    await run(() => promptApi.setPreviewImage(prompt!.id, imageId), '封面已设置')
  }

  return (
    <Drawer
      open
      onClose={onClose}
      width="wide"
      title={isNew ? '新建 Prompt' : `编辑：${prompt!.name}`}
      footer={
        <Button variant="primary" disabled={busy || !name.trim()} onClick={() => void handleSave()}>
          {isNew ? '创建' : '保存为新版本'}
        </Button>
      }
    >
      {!isNew && prompt && (
        <div className="pp-toolbar">
          <Button size="sm" variant="ghost" onClick={() => void run(() => promptApi.updateMeta(prompt.id, { favorite: !prompt.favorite }), '已更新收藏')}>
            {prompt.favorite ? '★ 已收藏' : '☆ 收藏'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onOpenInWorkbench(prompt)}>
            在生成工作台打开
          </Button>
          {prompt.archived ? (
            <Button size="sm" variant="ghost" onClick={() => void run(() => promptApi.restore(prompt.id), '已从归档恢复')}>
              恢复
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => void run(() => promptApi.archive(prompt.id), '已归档（软删除）')}>
              归档
            </Button>
          )}
        </div>
      )}

      <Field label="名称">
        <Input value={name} onChange={(event) => setName(event.target.value)} />
      </Field>

      <SegmentedControl
        block
        ariaLabel="Prompt 模式"
        value={mode}
        onChange={(value) => setMode(value as PromptMode)}
        options={[
          { value: 'structured', label: '结构化 Prompt' },
          { value: 'full', label: '完整 Prompt' },
        ]}
      />

      {mode === 'structured' ? (
        <div>
          {STRUCTURED_FIELDS.map(({ key, label }) => (
            <Field key={key} label={label}>
              <Textarea
                rows={2}
                value={structured[key]}
                onChange={(event) => setStructured({ ...structured, [key]: event.target.value })}
              />
            </Field>
          ))}
        </div>
      ) : (
        <Field label="完整 Prompt">
          <Textarea rows={10} value={fullPrompt} onChange={(event) => setFullPrompt(event.target.value)} />
        </Field>
      )}

      <Field label="Negative Prompt">
        <Textarea rows={3} value={negative} onChange={(event) => setNegative(event.target.value)} />
      </Field>

      <ComposePreview mode={mode} structured={structured} fullPrompt={fullPrompt} />

      {!isNew && prompt && (
        <section className="pp-cover">
          <h4 className="pp-cover__title">封面</h4>
          <div className="pp-cover__body">
            {coverImageId ? (
              <img className="pp-cover__img" src={imageContentUrl(coverImageId)} loading="lazy" alt="" />
            ) : (
              <div className="pp-cover__empty">无封面</div>
            )}
            <div className="pp-cover__actions">
              <Button size="sm" variant="ghost" onClick={() => setPickerOpen(true)}>
                {coverImageId ? '更换封面' : '设置封面'}
              </Button>
              {coverImageId && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void run(() => promptApi.clearPreviewImage(prompt.id), '封面已移除')}
                >
                  移除封面
                </Button>
              )}
            </div>
          </div>
          {pickerOpen && (
            <ImagePickerDrawer
              title="选择封面图片"
              onClose={() => setPickerOpen(false)}
              onPicked={(image) => void handlePickCover(image.id)}
            />
          )}
        </section>
      )}

      {message && (
        <p className={`ds-notice ds-notice--${message.kind === 'ok' ? 'success' : 'error'}`} role="status">
          {message.text}
        </p>
      )}

      {!isNew && (
        <section className="pp-versions">
          <h4 className="pp-versions__title">版本历史（不可变；恢复 = 复制为新最新版）</h4>
          {versions.length === 0 && <p className="muted">暂无版本</p>}
          <ul className="pp-versions__list">
            {versions.map((version) => (
              <li key={version.id} className="pp-versions__item">
                <div className="pp-versions__row">
                  <span className="pp-versions__no">v{version.version_no}</span>
                  <Badge tone="accent">{version.mode === 'full' ? '完整' : '结构化'}</Badge>
                  <span className="muted">{formatDateTime(version.created_at)}</span>
                  {prompt!.current_version?.id === version.id && <Badge>当前</Badge>}
                  <span className="pp-toolbar__spacer" />
                  <Button
                    size="xs" variant="ghost"
                    onClick={() => setViewingVersionId(viewingVersionId === version.id ? null : version.id)}
                  >
                    {viewingVersionId === version.id ? '收起' : '查看'}
                  </Button>
                  <Button
                    size="xs" variant="ghost"
                    disabled={busy || prompt!.current_version?.id === version.id}
                    onClick={() =>
                      void run(
                        () => promptApi.restoreVersion(prompt!.id, version.id),
                        `已恢复 v${version.version_no}（生成新版本）`,
                      )
                    }
                  >
                    恢复为新版本
                  </Button>
                </div>
                {viewingVersionId === version.id && (
                  <pre className="pp-versions__content">
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
    </Drawer>
  )
}
