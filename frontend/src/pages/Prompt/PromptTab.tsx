import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiRequestError, promptApi } from '../../api/client'
import { ComposePreview } from '../../components/ComposePreview'
import { ImagePickerDrawer } from '../../components/ImagePickerDrawer'
import {
  Badge,
  Button,
  Checkbox,
  ConfirmModal,
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
  PROMPT_EVALUATION_DIMENSIONS,
  STRUCTURED_FIELDS,
  PROMPT_STATUS_LABEL,
  emptyStructured,
  imageContentUrl,
  imagePreviewUrl,
  imageThumbUrl,
  type PromptDTO,
  type PromptEvaluationDimension,
  type PromptImageDTO,
  type PromptSort,
  type PromptStatus,
  type PromptMode,
  type PromptVersionDTO,
  type StructuredPrompt,
  type WorkbenchSnapshot,
} from '../../types/workbench'
import { PromptScoringDialog } from './PromptScoringDialog'
import { PromptImagesDrawer } from './PromptImagesDrawer'
import {
  clearPromptFilterPrefs,
  readPromptFilterPrefs,
  writePromptFilterPrefs,
  type PromptFilterPrefs,
  type PromptScoreFloor,
} from './promptFilterPrefs'

const PROMPT_FILTER_PARAM_NAMES = [
  'q', 'sort', 'status', 'scored', 'min_score', 'dimension', 'min_dimension',
] as const

type PromptFilterParamName = (typeof PROMPT_FILTER_PARAM_NAMES)[number]

/** URL 里的评分维度参数只接受 7 个白名单值，其它一律当“全部”。 */
function parseDimension(value: string | null): PromptEvaluationDimension | '' {
  return PROMPT_EVALUATION_DIMENSIONS.some((dimension) => dimension.key === value)
    ? (value as PromptEvaluationDimension)
    : ''
}

/** 评分下限只认 3/4/5；非法值当“不限”。 */
function parseScoreFloor(value: string | null): PromptScoreFloor {
  return value === '3' || value === '4' || value === '5' ? value : ''
}

function prefsToSearchParams(prefs: PromptFilterPrefs, current: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(current)
  PROMPT_FILTER_PARAM_NAMES.forEach((name) => next.delete(name))
  if (prefs.q !== '') next.set('q', prefs.q)
  if (prefs.sort !== 'updated_desc') next.set('sort', prefs.sort)
  if (prefs.status !== '') next.set('status', prefs.status)
  if (prefs.scored !== '') next.set('scored', prefs.scored)
  if ((prefs.minScore ?? '') !== '') next.set('min_score', prefs.minScore as string)
  if ((prefs.dimension ?? '') !== '') next.set('dimension', prefs.dimension as string)
  if ((prefs.minDimension ?? '') !== '') next.set('min_dimension', prefs.minDimension as string)
  return next
}

function searchParamsToPrefs(params: URLSearchParams): PromptFilterPrefs {
  const sortParam = params.get('sort')
  const statusParam = params.get('status')
  const scoredParam = params.get('scored')
  const minScore = parseScoreFloor(params.get('min_score'))
  const dimension = parseDimension(params.get('dimension'))
  const minDimension = parseScoreFloor(params.get('min_dimension'))
  return {
    q: params.get('q') ?? '',
    sort: sortParam === 'score_desc' || sortParam === 'score_asc' ? sortParam : 'updated_desc',
    status:
      statusParam === 'keep' || statusParam === 'candidate' || statusParam === 'eliminated'
        ? statusParam
        : '',
    scored: scoredParam === 'true' || scoredParam === 'false' ? scoredParam : '',
    // 未设置时省略字段，保持旧偏好文件形状与体积。
    ...(minScore === '' ? {} : { minScore }),
    ...(dimension === '' ? {} : { dimension }),
    ...(minDimension === '' ? {} : { minDimension }),
  }
}

/** 我的 Prompt（§三十八-§四十、§四十九、§五十四、§五十五）。 */
export function PromptTab() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [showArchived, setShowArchived] = useState(false)
  const [drawer, setDrawer] = useState<{ open: boolean; prompt: PromptDTO | null }>({ open: false, prompt: null })
  const [actionNotice, setActionNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  const hasExplicitFilterParams = PROMPT_FILTER_PARAM_NAMES.some((name) => searchParams.has(name))
  const [initialFilterPrefs] = useState<PromptFilterPrefs | null>(() =>
    hasExplicitFilterParams ? null : readPromptFilterPrefs(),
  )
  const [initialPrefsApplied, setInitialPrefsApplied] = useState(false)
  const useInitialPrefs = !hasExplicitFilterParams && !initialPrefsApplied && initialFilterPrefs !== null

  const search = useInitialPrefs ? initialFilterPrefs.q : (searchParams.get('q') ?? '')
  const sortParam = useInitialPrefs ? initialFilterPrefs.sort : searchParams.get('sort')
  const sort: PromptSort =
    sortParam === 'score_desc' || sortParam === 'score_asc' ? sortParam : 'updated_desc'
  const statusParam = useInitialPrefs ? initialFilterPrefs.status : searchParams.get('status')
  const status: PromptStatus | '' =
    statusParam === 'keep' || statusParam === 'candidate' || statusParam === 'eliminated'
      ? statusParam
      : ''
  const scoredParam = useInitialPrefs ? initialFilterPrefs.scored : searchParams.get('scored')
  const scored = scoredParam === 'true' ? true : scoredParam === 'false' ? false : undefined
  const minScoreParam = useInitialPrefs ? (initialFilterPrefs.minScore ?? '') : searchParams.get('min_score')
  const minScore = parseScoreFloor(minScoreParam)
  const dimensionParam = useInitialPrefs ? (initialFilterPrefs.dimension ?? '') : searchParams.get('dimension')
  const dimension = parseDimension(dimensionParam)
  const minDimensionParam = useInitialPrefs
    ? (initialFilterPrefs.minDimension ?? '')
    : searchParams.get('min_dimension')
  const minDimension = parseScoreFloor(minDimensionParam)

  useEffect(() => {
    if (!useInitialPrefs) return
    setInitialPrefsApplied(true)
    setSearchParams(prefsToSearchParams(initialFilterPrefs, searchParams), { replace: true })
  }, [initialFilterPrefs, searchParams, setSearchParams, useInitialPrefs])

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    let changed = false

    function remove(name: PromptFilterParamName): void {
      if (!next.has(name)) return
      next.delete(name)
      changed = true
    }

    if (search.trim() === '') remove('q')
    if (sortParam !== null && sortParam !== 'score_desc' && sortParam !== 'score_asc') remove('sort')
    if (statusParam !== null && status === '') remove('status')
    if (scoredParam !== null && scored === undefined) remove('scored')
    if (minScoreParam !== null && minScore === '') remove('min_score')
    if (dimensionParam !== null && dimension === '') remove('dimension')
    if (minDimensionParam !== null && minDimension === '') remove('min_dimension')
    if (dimension === '') {
      // 维度清空后，孤立的维度最低分不再有意义。
      if (next.has('dimension')) remove('dimension')
      if (next.has('min_dimension')) remove('min_dimension')
    } else if (!next.has('min_dimension')) {
      next.set('min_dimension', '3')
      changed = true
    }

    if (changed) setSearchParams(next, { replace: true })
  }, [
    scored, scoredParam, search, searchParams, setSearchParams, sortParam, status, statusParam,
    minScore, minScoreParam, dimension, dimensionParam, minDimension, minDimensionParam,
  ])

  // 防抖回调可能晚于其它筛选变更执行，必须读取最新的 URL 参数，避免用旧快照覆盖新条件。
  const searchParamsRef = useRef(searchParams)
  searchParamsRef.current = searchParams

  function updateFilter(name: PromptFilterParamName, value: string): void {
    const next = new URLSearchParams(searchParamsRef.current)
    const normalizedValue = name === 'q' && value.trim() === '' ? '' : value
    const isDefault = normalizedValue === '' || (name === 'sort' && normalizedValue === 'updated_desc')
    if (isDefault) next.delete(name)
    else next.set(name, normalizedValue)
    setSearchParams(next, { replace: true })
    writePromptFilterPrefs(searchParamsToPrefs(next))
  }

  /** 维度与维度最低分成对维护：选维度自动带默认下限，清空维度则一并清掉下限。 */
  function updateDimensionFilter(value: string): void {
    const next = new URLSearchParams(searchParamsRef.current)
    if (value === '') {
      next.delete('dimension')
      next.delete('min_dimension')
    } else {
      next.set('dimension', value)
      if (!next.has('min_dimension')) next.set('min_dimension', '3')
    }
    setSearchParams(next, { replace: true })
    writePromptFilterPrefs(searchParamsToPrefs(next))
  }

  function resetFilters(): void {
    const next = new URLSearchParams(searchParamsRef.current)
    PROMPT_FILTER_PARAM_NAMES.forEach((name) => next.delete(name))
    setInitialPrefsApplied(true)
    clearPromptFilterPrefs()
    setSearchParams(next, { replace: true })
  }

  const hasNonDefaultFilters =
    search.trim() !== '' || sort !== 'updated_desc' || status !== '' || scored !== undefined ||
    minScore !== '' || dimension !== '' || minDimension !== ''

  // v0.37：搜索输入本地即时反馈 + 300ms 防抖才写 URL；避免每敲一个字整表重载。
  const [searchInput, setSearchInput] = useState(search)
  const searchTimer = useRef<number | null>(null)
  useEffect(() => {
    setSearchInput(search)
  }, [search])
  useEffect(() => () => {
    if (searchTimer.current !== null) window.clearTimeout(searchTimer.current)
  }, [])
  function handleSearchInput(value: string): void {
    setSearchInput(value)
    if (searchTimer.current !== null) window.clearTimeout(searchTimer.current)
    searchTimer.current = window.setTimeout(() => {
      searchTimer.current = null
      if (value.trim() === search.trim()) return
      updateFilter('q', value)
    }, 300)
  }

  // Phase 0.12：取消后端默认 50 的隐形上限，改为 offset 分页 + 加载更多（数据全可达）。
  const fetcher = useCallback(
    (limit: number, offset: number) =>
      promptApi.list({
        search: search.trim() || undefined,
        archived: showArchived ? null : false,
        limit,
        offset,
        // v0.37.5：卡片内直接铺满全部生成图（先取 12 张，其余点「展开全部」按需加载）
        include_images: true,
        images_limit: 12,
        // Phase 0.17.3：附带最近一次评分，卡片上展示评分与状态。
        include_evaluation: true,
        ...(sort === 'updated_desc' ? {} : { sort }),
        ...(status ? { status } : {}),
        ...(scored === undefined ? {} : { scored }),
        ...(minScore === '' ? {} : { min_score: Number(minScore) }),
        ...(dimension === ''
          ? {}
          : { dimension, min_dimension_score: Number(minDimension || '3') }),
      }),
    [search, showArchived, sort, status, scored, minScore, dimension, minDimension],
  )

  const {
    items,
    total,
    hasMore,
    initialLoading,
    refreshing,
    loadingMore,
    error,
    reload,
    loadMore,
    updateItem,
  } = useInfiniteList<PromptDTO>({ pageSize: 50, fetcher, reloadDeps: [fetcher] })

  /** 收藏/评分等元数据变化：只改这一张卡片，不重载整表、不闪骨架屏。 */
  const patchPrompt = useCallback(
    (id: string, patch: Partial<PromptDTO>) => updateItem(id, patch),
    [updateItem],
  )

  // v0.37.5：卡片用 memo 渲染；这些回调必须稳定，否则每次列表刷新都会整页重渲染（观感卡顿来源之一）。
  const openPromptEditor = useCallback((prompt: PromptDTO) => {
    setDrawer({ open: true, prompt })
  }, [])

  const closeEditor = useCallback(() => setDrawer({ open: false, prompt: null }), [])

  const showError = useCallback((text: string) => {
    setActionNotice({ kind: 'error', text })
  }, [])

  const openInWorkbench = useCallback((prompt: PromptDTO): void => {
    setDrawer({ open: false, prompt: null })
    navigate('/generate', { state: { workbench: promptToSnapshot(prompt) } })
  }, [navigate])

  const archivePrompt = useCallback(async (prompt: PromptDTO): Promise<void> => {
    setActionNotice(null)
    try {
      await promptApi.archive(prompt.id)
      setActionNotice({ kind: 'ok', text: '已软删除 Prompt，可在“显示已归档”中找回' })
      reload()
    } catch (archiveError) {
      setActionNotice({
        kind: 'error',
        text: archiveError instanceof ApiRequestError ? archiveError.message : '删除失败',
      })
    }
  }, [reload])

  return (
    <div>
      <div className="pp-toolbar">
        <Input
          placeholder="搜索名称 / Prompt 内容"
          value={searchInput}
          onChange={(event) => handleSearchInput(event.target.value)}
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
            onChange={(event) => updateFilter('sort', event.target.value)}
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
            onChange={(event) => updateFilter('status', event.target.value)}
          />
          <Select
            aria-label="已评分"
            value={scoredParam === 'true' || scoredParam === 'false' ? scoredParam : ''}
            options={[
              { value: '', label: '评分：全部' },
              { value: 'true', label: '仅已评分' },
              { value: 'false', label: '仅未评分' },
            ]}
            onChange={(event) => updateFilter('scored', event.target.value)}
          />
          <Select
            aria-label="综合最低分"
            value={minScore}
            options={[
              { value: '', label: '综合：不限' },
              { value: '3', label: '综合 ≥ 3 分' },
              { value: '4', label: '综合 ≥ 4 分' },
              { value: '5', label: '综合 = 5 分' },
            ]}
            onChange={(event) => updateFilter('min_score', event.target.value)}
          />
          <Select
            aria-label="评分维度"
            value={dimension}
            options={[
              { value: '', label: '维度：全部' },
              ...PROMPT_EVALUATION_DIMENSIONS.map((item) => ({
                value: item.key,
                label: `维度：${item.label}`,
              })),
            ]}
            onChange={(event) => updateDimensionFilter(event.target.value)}
          />
          {dimension !== '' && (
            <Select
              aria-label="维度最低分"
              value={minDimension || '3'}
              options={[
                { value: '3', label: '维度 ≥ 3 分' },
                { value: '4', label: '维度 ≥ 4 分' },
                { value: '5', label: '维度 = 5 分' },
              ]}
              onChange={(event) => updateFilter('min_dimension', event.target.value)}
            />
          )}
          {hasNonDefaultFilters && (
            <Button size="xs" variant="ghost" onClick={resetFilters}>
              重置筛选
            </Button>
          )}
        </div>
        <span className="pp-toolbar__spacer" />
        {refreshing && <span className="muted" role="status">刷新中…</span>}
        <Button variant="primary" onClick={() => setDrawer({ open: true, prompt: null })}>
          新建 Prompt
        </Button>
      </div>

      {actionNotice && (
        <p
          className={`ds-notice ds-notice--${actionNotice.kind === 'ok' ? 'success' : 'error'}`}
          role="status"
        >
          {actionNotice.text}
        </p>
      )}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {!initialLoading && !error && items.length === 0 && (
        <div className="pp-empty">
          <h2 className="pp-empty__title">还没有 Prompt</h2>
          <p className="muted">点击“新建 Prompt”，或在工作台保存当前配置。</p>
        </div>
      )}

      {initialLoading ? (
        <PromptListSkeleton />
      ) : (
        <div className="pp-grid pp-grid--single">
          {items.map((prompt) => (
            <PromptCard
              key={prompt.id}
              prompt={prompt}
              onOpen={openPromptEditor}
              onUse={openInWorkbench}
              onArchive={archivePrompt}
              onPatched={patchPrompt}
              onError={showError}
            />
          ))}
        </div>
      )}

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
          onClose={closeEditor}
          onChanged={reload}
          onOpenInWorkbench={openInWorkbench}
        />
      )}
    </div>
  )
}

function PromptListSkeleton() {
  return (
    <div className="pp-grid pp-grid--single pp-skeleton-list" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <article className="pp-skeleton" key={index}>
          <div className="pp-skeleton__head" />
          <div className="pp-skeleton__text" />
          <div className="pp-skeleton__text pp-skeleton__text--short" />
          <div className="pp-skeleton__media" />
          <div className="pp-skeleton__actions" />
        </article>
      ))}
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
  /** 软删除并刷新外层列表。 */
  onArchive: (prompt: PromptDTO) => Promise<void>
  /** 收藏 / 评分等元数据就地更新（不整表重载）。 */
  onPatched: (id: string, patch: Partial<PromptDTO>) => void
  /** 失败时回到页面错误条，不静默吞掉。 */
  onError: (text: string) => void
}

/** v0.37.5：展开全部生成图的进程内缓存——收起后再展开不重复请求。 */
const expandedImagesCache = new Map<string, PromptImageDTO[]>()

/**
 * Prompt 整行卡片：
 * 名称/状态/评分 → 摘要（≤2 行）→ 图片 → 更新时间与操作。
 * 无图不渲染媒体区；点图才打开预览，无图不弹错。
 * 不自动覆盖封面，封面仍在编辑抽屉里显式“设为 Prompt 封面”。
 */
const PromptCard = memo(function PromptCard({
  prompt, onOpen, onUse, onArchive, onPatched, onError,
}: PromptCardProps) {
  const [copied, setCopied] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [favBusy, setFavBusy] = useState(false)
  // v0.37：收藏先乐观更新本地，失败再回滚；不再触发整表重载。
  const [favorite, setFavorite] = useState(prompt.favorite)
  useEffect(() => setFavorite(prompt.favorite), [prompt.favorite])
  // v0.37.6：卡片内直接改名 / 改状态（乐观更新，失败回滚）。
  const [renaming, setRenaming] = useState(false)
  const [nameDraft, setNameDraft] = useState(prompt.name)
  const [status, setStatusLocal] = useState<PromptStatus>(prompt.status ?? 'candidate')
  const [statusBusy, setStatusBusy] = useState(false)
  const renameBusyRef = useRef(false)
  const cancelRenameRef = useRef(false)
  useEffect(() => setNameDraft(prompt.name), [prompt.name])
  useEffect(() => setStatusLocal(prompt.status ?? 'candidate'), [prompt.status])
  // Phase 0.17.2：卡片下展示该提示词生成过的图；点击看大图。
  const [galleryImage, setGalleryImage] = useState<PromptImageDTO | null>(null)
  // Phase 0.17.3：人工评分弹窗。
  const [scoringOpen, setScoringOpen] = useState(false)
  // v0.37.5：卡片内联加载「全部」生成图。首批 12 张随列表返回；其余按需分页拉取并缓存。
  const [extraImages, setExtraImages] = useState<PromptImageDTO[]>([])
  const [expandState, setExpandState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [imagesOpen, setImagesOpen] = useState(false)  // 按类型/状态筛选（保留原抽屉能力）
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteBusy, setDeleteBusy] = useState(false)
  // DB 有 preview_image_id 但 rendition 缺失/损坏时，移除整个媒体区。
  const [previewFailed, setPreviewFailed] = useState(false)

  const baseImages = prompt.images ?? []
  const visibleImages = extraImages.length > 0 ? [...baseImages, ...extraImages] : baseImages
  const totalImages = prompt.images_total ?? baseImages.length
  const hasHiddenImages = totalImages > visibleImages.length

  /** 一次性拉齐该 Prompt 的全部关联图（服务端分页，最多几次请求），并去重合并。 */
  async function expandAllImages(): Promise<void> {
    if (expandState === 'loading') return
    const cached = expandedImagesCache.get(prompt.id)
    if (cached) {
      setExtraImages(cached)
      return
    }
    setExpandState('loading')
    try {
      const collected: PromptImageDTO[] = []
      let offset = 0
      for (;;) {
        const page = await promptApi.listImages(prompt.id, { limit: 100, offset })
        collected.push(...page.items)
        offset += page.items.length
        if (page.items.length === 0 || collected.length >= page.total) break
      }
      const baseIds = new Set(baseImages.map((image) => image.id))
      const extras = collected.filter((image) => !baseIds.has(image.id))
      expandedImagesCache.set(prompt.id, extras)
      setExtraImages(extras)
      setExpandState('idle')
    } catch (err) {
      setExpandState('error')
      onError(err instanceof ApiRequestError ? err.message : '加载全部生成图失败')
    }
  }

  // 封面 id 变化（重新设置封面）时重置失败态，允许重试新加载。
  useEffect(() => {
    setPreviewFailed(false)
  }, [prompt.preview_image_id])

  const hasPreview = Boolean(prompt.preview_image_id) && !previewFailed
  const hasMedia = hasPreview || visibleImages.length > 0

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
    const next = !favorite
    setFavBusy(true)
    setFavorite(next)
    onPatched(prompt.id, { favorite: next })
    try {
      await promptApi.updateMeta(prompt.id, { favorite: next })
    } catch (err) {
      setFavorite(!next)
      onPatched(prompt.id, { favorite: !next })
      onError(err instanceof ApiRequestError ? err.message : '收藏失败')
    } finally {
      setFavBusy(false)
    }
  }

  async function handleArchive(): Promise<void> {
    if (deleteBusy) return
    setDeleteBusy(true)
    try {
      await onArchive(prompt)
      setDeleteOpen(false)
    } finally {
      setDeleteBusy(false)
    }
  }

  /** 卡片内改名：Enter / 失焦保存，Esc 取消；空名视为放弃。 */
  async function commitRename(): Promise<void> {
    if (cancelRenameRef.current) {
      cancelRenameRef.current = false
      return
    }
    if (!renaming || renameBusyRef.current) return
    const next = nameDraft.trim()
    if (next === '' || next === prompt.name) {
      setNameDraft(prompt.name)
      setRenaming(false)
      return
    }
    renameBusyRef.current = true
    setRenaming(false)
    onPatched(prompt.id, { name: next })
    try {
      await promptApi.updateMeta(prompt.id, { name: next })
    } catch (err) {
      setNameDraft(prompt.name)
      onPatched(prompt.id, { name: prompt.name })
      onError(err instanceof ApiRequestError ? err.message : '重命名失败')
    } finally {
      renameBusyRef.current = false
    }
  }

  /** 卡片内切换状态：乐观更新，失败回滚并回到页面错误条。 */
  async function handleStatusChange(next: PromptStatus): Promise<void> {
    if (next === status || statusBusy) return
    const previous = status
    setStatusLocal(next)
    setStatusBusy(true)
    onPatched(prompt.id, { status: next })
    try {
      await promptApi.setStatus(prompt.id, { status: next })
    } catch (err) {
      setStatusLocal(previous)
      onPatched(prompt.id, { status: previous })
      onError(err instanceof ApiRequestError ? err.message : '更新状态失败')
    } finally {
      setStatusBusy(false)
    }
  }

  return (
    <article className={`pp-card pp-card--compact${hasMedia ? ' pp-card--with-media' : ''}`}>
      <header className="pp-card__head">
        <h3 className="pp-card__title">
          {prompt.favorite && <span title="已收藏">★ </span>}
          {renaming ? (
            <input
              className="pp-card__title-input"
              aria-label="重命名 Prompt"
              autoFocus
              value={nameDraft}
              onChange={(event) => setNameDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  void commitRename()
                } else if (event.key === 'Escape') {
                  event.preventDefault()
                  cancelRenameRef.current = true
                  setNameDraft(prompt.name)
                  setRenaming(false)
                }
              }}
              onBlur={() => void commitRename()}
            />
          ) : (
            <button
              type="button"
              className="pp-card__title-text"
              title="点击改名"
              onClick={() => {
                setNameDraft(prompt.name)
                setRenaming(true)
              }}
            >
              {prompt.name}
            </button>
          )}
          {prompt.archived && <Badge>已归档</Badge>}
        </h3>
        <div className="pp-card__meta">
          <span className="pp-card__badges">
            <Badge tone="accent">
              {prompt.current_version?.mode === 'full' ? '完整' : '结构化'}
            </Badge>
            <select
              className={`pp-card__status pp-card__status--${status} pp-card__status-select`}
              aria-label="提示词状态"
              title="直接切换状态"
              value={status}
              disabled={statusBusy}
              onChange={(event) => void handleStatusChange(event.target.value as PromptStatus)}
            >
              {(['keep', 'candidate', 'eliminated'] as PromptStatus[]).map((value) => (
                <option key={value} value={value}>
                  {PROMPT_STATUS_LABEL[value]}
                </option>
              ))}
            </select>
          </span>
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
        </div>
      </header>

      <p className="pp-card__excerpt">{promptSummary(prompt)}</p>

      {(hasPreview || visibleImages.length > 0 || expandState === 'error') && (
        <div className="pp-card__media">
          {/* 保留日用封面、内联全部图片和筛选能力，仅收敛到紧凑卡片的媒体列。 */}
          {hasPreview && prompt.preview_image_id && (
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
                decoding="async"
                alt=""
                onError={() => {
                  // 后端清了文件但元数据仍在 / rendition 损坏：移除封面。
                  setPreviewFailed(true)
                }}
              />
            </button>
          )}
          {visibleImages.length > 0 && (
            <div
              className="pp-card__gallery"
              aria-label={`该提示词生成过的图片，共 ${totalImages} 张`}
            >
              {visibleImages.map((image) => (
                <button
                  key={image.id}
                  type="button"
                  className="pp-card__gallery-thumb"
                  onClick={() => setGalleryImage(image)}
                  title={image.module_id ? `由 ${image.module_id} 生成` : '查看大图'}
                  aria-label={`查看生成图 ${image.id}`}
                >
                  <img src={image.thumbnail_url} loading="lazy" decoding="async" alt="" />
                </button>
              ))}
            </div>
          )}
          {(visibleImages.length > 0 || expandState === 'error') && (
            <div className="pp-card__gallery-tools">
              {hasHiddenImages && (
                <button
                  type="button"
                  className="pp-card__gallery-expand"
                  disabled={expandState === 'loading'}
                  onClick={() => void expandAllImages()}
                >
                  {expandState === 'loading' ? '加载中…' : `展开全部 ${totalImages} 张`}
                </button>
              )}
              {expandState === 'error' && <span className="muted">加载失败，可重试</span>}
              {extraImages.length > 0 && (
                <button type="button" className="pp-card__gallery-expand" onClick={() => setExtraImages([])}>
                  收起
                </button>
              )}
              {totalImages > 0 && (
                <button type="button" className="pp-card__gallery-expand" onClick={() => setImagesOpen(true)}>
                  按类型/状态筛选
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {imagesOpen && (
        <PromptImagesDrawer
          promptId={prompt.id}
          promptName={prompt.name}
          onClose={() => setImagesOpen(false)}
        />
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
          {!prompt.archived && (
            <button
              type="button"
              className="pp-card__action pp-card__action--danger"
              onClick={() => setDeleteOpen(true)}
            >
              删除
            </button>
          )}
        </span>
      </footer>

      <ConfirmModal
        open={deleteOpen}
        title={`删除 Prompt“${prompt.name}”？`}
        message="软删除后，可在“显示已归档”中找回。"
        confirmText={deleteBusy ? '删除中…' : '确认删除'}
        cancelText="取消"
        danger
        onCancel={() => {
          if (!deleteBusy) setDeleteOpen(false)
        }}
        onConfirm={() => void handleArchive()}
      />

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
        <PromptScoringDialog
          prompt={prompt}
          onClose={() => setScoringOpen(false)}
          onSaved={(patch) => onPatched(prompt.id, patch)}
        />
      )}
    </article>
  )
})

interface EditorDrawerProps {
  prompt: PromptDTO | null
  onClose: () => void
  onChanged: () => void
  onOpenInWorkbench: (prompt: PromptDTO) => void
}

/** 编辑器“已保存基线”：用于判断是否有未保存修改（Ctrl+S / 关闭确认）。 */
function editorBaseline(prompt: PromptDTO | null) {
  const version = prompt?.current_version
  return {
    name: prompt?.name ?? '',
    mode: (version?.mode ?? 'structured') as PromptMode,
    structured: version?.structured ?? emptyStructured(),
    fullPrompt: version?.mode === 'full' ? version.positive_prompt : '',
    negative: version?.negative_prompt ?? '',
  }
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
  // v0.37.5：未保存修改保护 + Ctrl+S
  const [baseline, setBaseline] = useState(() => editorBaseline(prompt))
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false)

  const dirty =
    name !== baseline.name ||
    mode !== baseline.mode ||
    fullPrompt !== baseline.fullPrompt ||
    negative !== baseline.negative ||
    STRUCTURED_FIELDS.some(({ key }) => structured[key] !== baseline.structured[key])

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
    setBaseline(editorBaseline(prompt))
    setCloseConfirmOpen(false)
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
        setBaseline(editorBaseline(updated))
      } else {
        // 新建 Prompt：刷新外层列表，使新卡片立即出现（否则需手动刷新页面）
        onChanged()
        setBaseline({ name, mode, structured, fullPrompt, negative })
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

  /** v0.37.5：有未保存修改时关闭需二次确认，避免误关丢内容。 */
  function requestClose(): void {
    if (busy) return
    if (dirty) setCloseConfirmOpen(true)
    else onClose()
  }

  async function handleCopyAll(): Promise<void> {
    const text = mode === 'full'
      ? fullPrompt
      : STRUCTURED_FIELDS.map(({ key, label }) => (structured[key] ? `${label}: ${structured[key]}` : null))
          .filter(Boolean)
          .join('\n')
    const payload = negative.trim() ? `${text}\n\nNegative: ${negative}` : text
    try {
      await navigator.clipboard.writeText(payload)
      setMessage({ kind: 'ok', text: '已复制完整 Prompt' })
    } catch {
      setMessage({ kind: 'error', text: '复制失败（剪贴板不可用）' })
    }
  }

  // Ctrl/Cmd+S 保存；用 ref 取最新闭包，避免频繁重建监听。
  const saveRef = useRef<() => void>(() => {})
  saveRef.current = () => {
    if (!busy && name.trim()) void handleSave()
  }
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 's') return
      event.preventDefault()
      saveRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <Drawer
      open
      onClose={requestClose}
      width="wide"
      title={isNew ? '新建 Prompt' : `编辑：${prompt!.name}`}
      footer={
        <div className="pp-editor__foot">
          {dirty && <span className="muted">未保存 · Ctrl+S 保存</span>}
          <Button variant="primary" disabled={busy || !name.trim()} onClick={() => void handleSave()}>
            {isNew ? '创建' : '保存为新版本'}
          </Button>
        </div>
      }
    >
      {!isNew && prompt && (
        <div className="pp-toolbar">
          <Button size="sm" variant="ghost" onClick={() => void run(() => promptApi.updateMeta(prompt.id, { favorite: !prompt.favorite }), '已更新收藏')}>
            {prompt.favorite ? '★ 已收藏' : '☆ 收藏'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void handleCopyAll()}>
            复制完整 Prompt
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

      <ConfirmModal
        open={closeConfirmOpen}
        title="放弃未保存的修改？"
        message="当前修改尚未保存为版本，关闭后会丢失。"
        confirmText="放弃修改"
        cancelText="继续编辑"
        danger
        onCancel={() => setCloseConfirmOpen(false)}
        onConfirm={() => {
          setCloseConfirmOpen(false)
          onClose()
        }}
      />
    </Drawer>
  )
}
