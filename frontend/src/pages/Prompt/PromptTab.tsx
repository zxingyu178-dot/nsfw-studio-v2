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
  Modal,
  SegmentedControl,
  Select,
  Textarea,
} from '../../components/ui'
import { formatDateTime } from '../../utils/format'
import { useInfiniteList } from './useInfiniteList'
import {
  STRUCTURED_FIELDS,
  PROMPT_STATUS_LABEL,
  emptyStructured,
  imageContentUrl,
  imagePreviewUrl,
  imageThumbUrl,
  type PromptDTO,
  type PromptImageDTO,
  type PromptSort,
  type PromptStatus,
  type PromptMode,
  type PromptVersionDTO,
  type StructuredPrompt,
  type WorkbenchSnapshot,
} from '../../types/workbench'
import { PromptScoringDialog } from './PromptScoringDialog'

/** 我的 Prompt（§三十八-§四十、§四十九、§五十四、§五十五）。 */
export function PromptTab() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [sort, setSort] = useState<PromptSort>('updated_desc')
  const [status, setStatus] = useState<PromptStatus | ''>('')
  const [drawer, setDrawer] = useState<{ open: boolean; prompt: PromptDTO | null }>({ open: false, prompt: null })

  // Phase 0.12：取消后端默认 50 的隐形上限，改为 offset 分页 + 加载更多（数据全可达）。
  const fetcher = useCallback(
    (limit: number, offset: number) =>
      promptApi.list({
        search: search.trim() || undefined,
        archived: showArchived ? null : false,
        limit,
        offset,
        // Phase 0.17.2：卡片下直接展示「这条提示词生成过的图」。
        include_images: true,
        images_limit: 3,
        // Phase 0.17.3：附带最近一次评分，卡片上展示评分与状态。
        include_evaluation: true,
        ...(sort === 'updated_desc' ? {} : { sort }),
        ...(status ? { status } : {}),
      }),
    [search, showArchived, sort, status],
  )

  const {
    items,
    total,
    hasMore,
    initialLoading,
    loadingMore,
    error,
    reload,
    loadMore,
  } = useInfiniteList<PromptDTO>({ pageSize: 50, fetcher, reloadDeps: [fetcher] })

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
        <div className="pp-toolbar__filters">
          <Select
            aria-label="Prompt 排序"
            value={sort}
            options={[
              { value: 'updated_desc', label: '排序：最近更新' },
              { value: 'score_desc', label: '排序：评分高→低' },
              { value: 'score_asc', label: '排序：评分低→高' },
            ]}
            onChange={(event) => setSort(event.target.value as PromptSort)}
          />
          <Select
            aria-label="Prompt 状态"
            value={status}
            options={[
              { value: '', label: '状态：全部' },
              { value: 'keep', label: '状态：保留' },
              { value: 'candidate', label: '状态：候选' },
              { value: 'eliminated', label: '状态：已淘汰' },
            ]}
            onChange={(event) => setStatus(event.target.value as PromptStatus | '')}
          />
        </div>
        <span className="pp-toolbar__spacer" />
        <Button variant="primary" onClick={() => setDrawer({ open: true, prompt: null })}>
          新建 Prompt
        </Button>
      </div>

      {initialLoading && <p className="muted">加载中…</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {!initialLoading && !error && items.length === 0 && (
        <div className="pp-empty">
          <h2 className="pp-empty__title">还没有 Prompt</h2>
          <p className="muted">点击“新建 Prompt”，或在工作台保存当前配置。</p>
        </div>
      )}

      <div className="pp-grid">
        {items.map((prompt) => (
          <PromptCard
            key={prompt.id}
            prompt={prompt}
            onOpen={(p) => setDrawer({ open: true, prompt: p })}
            onUse={openInWorkbench}
            onChanged={reload}
          />
        ))}
      </div>

      {!initialLoading && !error && items.length > 0 && (
        <div className="pp-loadmore">
          {hasMore ? (
            <Button variant="secondary" loading={loadingMore} disabled={loadingMore} onClick={loadMore}>
              {loadingMore ? '加载中…' : '加载更多'}
            </Button>
          ) : (
            <span className="muted">已加载全部 {total} 条</span>
          )}
          <span className="muted">已加载 {items.length} / 共 {total}</span>
        </div>
      )}

      {drawer.open && (
        <PromptEditorDrawer
          prompt={drawer.prompt}
          onClose={() => setDrawer({ open: false, prompt: null })}
          onChanged={reload}
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
  /** 打开编辑抽屉。 */
  onOpen: (prompt: PromptDTO) => void
  /** 一键带入工作台（使用）。 */
  onUse: (prompt: PromptDTO) => void
  /** 收藏等元数据变化后刷新外层列表。 */
  onChanged: () => void
}

/**
 * Prompt 可视化卡片（v0.15 Task 13/14）：
 * 名称 → 摘要（≤3 行）→ 预览图（在文本下方）→ 更新时间 → 使用 / 复制 / 编辑 / 收藏。
 * 无图统一低对比“暂未生成”占位（固定 aspect ratio、绝不 broken-image）；点图才打开预览，无图不弹错。
 * 不自动覆盖封面，封面仍在编辑抽屉里显式“设为 Prompt 封面”。
 */
function PromptCard({ prompt, onOpen, onUse, onChanged }: PromptCardProps) {
  const [copied, setCopied] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [favBusy, setFavBusy] = useState(false)
  // Phase 0.17.2：卡片下展示该提示词生成过的图；点击看大图。
  const [galleryImage, setGalleryImage] = useState<PromptImageDTO | null>(null)
  // Phase 0.17.3：人工评分弹窗。
  const [scoringOpen, setScoringOpen] = useState(false)
  // v0.15.1：DB 有 preview_image_id 但 rendition 缺失/损坏时，统一回退“暂未生成”占位，
  // 而不是把 img 隐藏后留下一个空白 preview 区。
  const [previewFailed, setPreviewFailed] = useState(false)

  // 封面 id 变化（重新设置封面）时重置失败态，允许重试新加载。
  useEffect(() => {
    setPreviewFailed(false)
  }, [prompt.preview_image_id])

  const hasPreview = Boolean(prompt.preview_image_id) && !previewFailed

  async function handleCopy(): Promise<void> {
    const text = prompt.current_version?.positive_prompt ?? ''
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // 剪贴板权限不可用时仅做 UI 反馈，不阻断卡片
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  async function handleToggleFavorite(): Promise<void> {
    if (favBusy) return
    setFavBusy(true)
    try {
      await promptApi.updateMeta(prompt.id, { favorite: !prompt.favorite })
      onChanged()
    } finally {
      setFavBusy(false)
    }
  }

  return (
    <article className="pp-card">
      <header className="pp-card__head">
        <h3 className="pp-card__title">
          {prompt.favorite && <span title="已收藏">★ </span>}
          {prompt.name}
          {prompt.archived && <Badge>已归档</Badge>}
        </h3>
        <span className="pp-card__badges">
          <Badge tone="accent">
            {prompt.current_version?.mode === 'full' ? '完整' : '结构化'}
          </Badge>
          <span className={`pp-card__status pp-card__status--${prompt.status ?? 'candidate'}`}>
            {PROMPT_STATUS_LABEL[prompt.status ?? 'candidate']}
          </span>
        </span>
      </header>

      <p className="pp-card__excerpt">{promptSummary(prompt)}</p>

      {prompt.latest_evaluation && (
        <div
          className="pp-card__score"
          aria-label={`最近评分 ${prompt.latest_evaluation.overall_score} 分（满分 5）`}
        >
          <span className="pp-card__score-value">{prompt.latest_evaluation.overall_score}</span>
          <span className="pp-card__score-label">/ 5</span>
          {prompt.status_reason && <span className="pp-card__score-note">{prompt.status_reason}</span>}
        </div>
      )}

      {/* 预览图：Phase 0.18 D 起图片优先——DOM 仍在文本之后，由 CSS `order: -1` 置顶铺满卡片。 */}
      {hasPreview && prompt.preview_image_id ? (
        <button
          type="button"
          className="pp-card__preview"
          onClick={() => setPreviewOpen(true)}
          title="点击预览封面"
          aria-label={`预览 ${prompt.name} 的封面`}
        >
          <img
            src={imageThumbUrl(prompt.preview_image_id)}
            loading="lazy"
            alt=""
            onError={() => {
              // 后端清了文件但元数据仍在 / rendition 损坏：进入统一占位，不显示 broken-image、不留空白。
              setPreviewFailed(true)
            }}
          />
        </button>
      ) : (
        <div className="pp-card__preview pp-card__preview--empty" aria-label="暂未生成预览">
          <span>暂未生成</span>
        </div>
      )}

      {prompt.images && prompt.images.length > 0 && (
        <div
          className="pp-card__gallery"
          aria-label={`该提示词生成过的图片，共 ${prompt.images_total ?? prompt.images.length} 张`}
        >
          {prompt.images.map((image) => (
            <button
              key={image.id}
              type="button"
              className="pp-card__gallery-thumb"
              onClick={() => setGalleryImage(image)}
              title={image.module_id ? `由 ${image.module_id} 生成` : '查看大图'}
              aria-label={`查看生成图 ${image.id}`}
            >
              <img src={image.thumbnail_url} loading="lazy" alt="" />
            </button>
          ))}
          {(prompt.images_total ?? 0) > prompt.images.length && (
            <span className="pp-card__gallery-more" aria-hidden="true">
              +{(prompt.images_total ?? 0) - prompt.images.length}
            </span>
          )}
        </div>
      )}

      <footer className="pp-card__foot">
        <span className="pp-card__time">{formatDateTime(prompt.updated_at)}</span>
        <span className="pp-card__actions">
          <button type="button" className="pp-card__action" onClick={() => onUse(prompt)}>
            使用
          </button>
          <button
            type="button"
            className="pp-card__action"
            title="复制当前版本完整 Prompt"
            onClick={() => void handleCopy()}
          >
            {copied ? '已复制' : '复制'}
          </button>
          <button type="button" className="pp-card__action" onClick={() => onOpen(prompt)}>
            编辑
          </button>
          <button type="button" className="pp-card__action" onClick={() => setScoringOpen(true)}>
            {prompt.latest_evaluation ? '重新评分' : '评分'}
          </button>
          <button
            type="button"
            className="pp-card__action"
            disabled={favBusy}
            onClick={() => void handleToggleFavorite()}
          >
            {prompt.favorite ? '★ 已收藏' : '☆ 收藏'}
          </button>
        </span>
      </footer>

      {previewOpen && prompt.preview_image_id && (
        <Modal open title={prompt.name} onClose={() => setPreviewOpen(false)}>
          <img className="pp-card__preview-modal" src={imageContentUrl(prompt.preview_image_id)} alt={prompt.name} />
        </Modal>
      )}

      {galleryImage && (
        <Modal open title={`${prompt.name} · 生成图`} onClose={() => setGalleryImage(null)}>
          <img className="pp-card__preview-modal" src={galleryImage.preview_url} alt="" />
        </Modal>
      )}

      {scoringOpen && (
        <PromptScoringDialog prompt={prompt} onClose={() => setScoringOpen(false)} onSaved={onChanged} />
      )}
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
  // v0.15.1：小封面 rendition 加载失败时回退“无封面”，不显示 broken-image。
  const [coverFailed, setCoverFailed] = useState(false)
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
    setCoverFailed(false)
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
        setCoverFailed(false)
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
            {coverImageId && !coverFailed ? (
              <img
                className="pp-cover__img"
                src={imagePreviewUrl(coverImageId)}
                loading="lazy"
                alt=""
                onError={() => setCoverFailed(true)}
              />
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
