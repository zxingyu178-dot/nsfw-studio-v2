/**
 * WorkbenchBar（v0.15 Task 4）：顶部上下文条。
 * 左：生成模式（文生图 | 图片生成）；
 * 中：来源上下文（sourcePromptId / sourceRecipeId → 名称；信息不足只显示“当前工作台”，禁止伪造）；
 * 右：重置、保存 ▾（保存为 Prompt / 保存为配方）。保存逻辑沿用 promptApi/recipeApi，不新增数据库。
 */
import { useEffect, useRef, useState } from 'react'
import { ApiRequestError, promptApi, recipeApi } from '../../../api/client'
import { Button, Checkbox, Field, Input, Modal, SegmentedControl } from '../../../components/ui'
import { IconButton, IconChevronDown, IconRestart } from '../../../components/ui/ui3'
import {
  resetWorkbench,
  setWorkbenchMode,
  snapshotFromState,
  useWorkbench,
} from '../../../stores/workbenchStore'

type SaveTarget = 'prompt' | 'recipe' | null

export function WorkbenchBar() {
  const state = useWorkbench()
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveTarget, setSaveTarget] = useState<SaveTarget>(null)
  const [saveName, setSaveName] = useState('')
  const [saveFavorite, setSaveFavorite] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [sourceLabel, setSourceLabel] = useState<string | null>(null)
  const [saveMenuOpen, setSaveMenuOpen] = useState(false)
  const saveMenuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!saveMenuOpen) return
    const onDown = (e: MouseEvent) => {
      if (saveMenuRef.current && !saveMenuRef.current.contains(e.target as Node)) {
        setSaveMenuOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSaveMenuOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [saveMenuOpen])

  // 来源上下文：只在有 id 时按真实名称显示，否则“当前工作台”。
  const sourcePromptId = state.sourcePromptId
  const sourceRecipeId = state.sourceRecipeId
  useEffect(() => {
    let cancelled = false
    if (sourceRecipeId) {
      recipeApi
        .get(sourceRecipeId)
        .then((recipe) => {
          if (!cancelled) setSourceLabel(`配方：${recipe.name}`)
        })
        .catch(() => !cancelled && setSourceLabel('当前工作台'))
    } else if (sourcePromptId) {
      promptApi
        .get(sourcePromptId)
        .then((prompt) => {
          if (!cancelled) setSourceLabel(`Prompt：${prompt.name}`)
        })
        .catch(() => !cancelled && setSourceLabel('当前工作台'))
    } else {
      setSourceLabel('当前工作台')
    }
    return () => {
      cancelled = true
    }
  }, [sourcePromptId, sourceRecipeId])

  function openSave(target: SaveTarget): void {
    setSaveTarget(target)
    setSaveName('')
    setSaveFavorite(false)
    setMessage(null)
    setSaveOpen(true)
  }

  async function handleConfirm(): Promise<void> {
    if (!saveName.trim() || saving || !saveTarget) return
    setSaving(true)
    setMessage(null)
    const snapshot = snapshotFromState()
    try {
      if (saveTarget === 'prompt') {
        await promptApi.create({
          name: saveName.trim(),
          mode: snapshot.prompt_mode,
          positive_prompt: snapshot.prompt_mode === 'full' ? snapshot.full_prompt : '',
          negative_prompt: snapshot.negative_prompt,
          structured: snapshot.structured_prompt,
          favorite: saveFavorite,
        })
        setMessage({ kind: 'ok', text: '已保存为 Prompt（可在“提示词”页查看）' })
      } else {
        await recipeApi.create({ name: saveName.trim(), favorite: saveFavorite, snapshot })
        setMessage({ kind: 'ok', text: '已保存为配方（含 Prompt 与素材快照）' })
      }
      setSaveOpen(false)
    } catch (error) {
      setMessage({
        kind: 'error',
        text: error instanceof ApiRequestError ? error.message : '保存失败',
      })
    } finally {
      setSaving(false)
    }
  }

  const saveTitle = saveTarget === 'prompt' ? '保存为 Prompt' : '保存为配方'

  return (
    <div className="wb4-bar glass">
      <div className="wb4-bar__left">
        <SegmentedControl
          value={state.mode}
          onChange={(v) => setWorkbenchMode(v as typeof state.mode)}
          options={[
            { value: 'text', label: '文生图' },
            { value: 'image', label: '图片生成' },
          ]}
          ariaLabel="生成模式"
        />
      </div>
      <div className="wb4-bar__context" title={sourceLabel ?? '当前工作台'}>
        {sourceLabel ?? '当前工作台'}
      </div>
      <div className="wb4-bar__right">
        <IconButton
          icon={<IconRestart size={16} />}
          label="重置工作台"
          onClick={() => {
            resetWorkbench()
            setMessage({ kind: 'ok', text: '已重置工作台' })
          }}
        />
        <div className="wb4-bar__save" ref={saveMenuRef}>
          <button
            type="button"
            className="wb4-save__trigger"
            aria-haspopup="menu"
            aria-expanded={saveMenuOpen}
            onClick={() => setSaveMenuOpen((open) => !open)}
          >
            保存 <IconChevronDown size={14} />
          </button>
          {saveMenuOpen && (
            <div className="wb4-save__menu glass--strong" role="menu" aria-label="保存工作台">
              <button
                type="button"
                role="menuitem"
                className="wb4-save__item"
                onClick={() => {
                  setSaveMenuOpen(false)
                  openSave('prompt')
                }}
              >
                保存为 Prompt
              </button>
              <button
                type="button"
                role="menuitem"
                className="wb4-save__item"
                onClick={() => {
                  setSaveMenuOpen(false)
                  openSave('recipe')
                }}
              >
                保存为配方
              </button>
            </div>
          )}
        </div>
      </div>

      {message && (
        <p
          className={`ds-notice ds-notice--${message.kind === 'ok' ? 'success' : 'error'} wb4-bar__notice`}
          role="status"
          onClick={() => setMessage(null)}
        >
          {message.text}
        </p>
      )}

      <Modal
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        title={saveTitle}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSaveOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!saveName.trim() || saving} onClick={() => void handleConfirm()}>
              保存
            </Button>
          </>
        }
      >
        <Field label="名称">
          <Input value={saveName} onChange={(event) => setSaveName(event.target.value)} autoFocus />
        </Field>
        <Checkbox label="收藏" checked={saveFavorite} onChange={(event) => setSaveFavorite(event.target.checked)} />
      </Modal>
    </div>
  )
}

export default WorkbenchBar
