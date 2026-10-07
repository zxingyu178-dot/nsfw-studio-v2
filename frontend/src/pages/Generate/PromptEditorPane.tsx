import { useState } from 'react'
import { ApiRequestError, promptApi, recipeApi } from '../../api/client'
import { ComposePreview } from '../../components/ComposePreview'
import { STRUCTURED_FIELDS, type StructuredPrompt } from '../../types/workbench'
import {
  applyAssetToSlot,
  clearAssetFromSlot,
  setFullPrompt,
  setNegativePrompt,
  setPromptMode,
  setStructuredField,
  snapshotFromState,
  useWorkbench,
} from '../../stores/workbenchStore'
import { AssetPickerDrawer } from './AssetPickerDrawer'

type SaveTarget = 'prompt' | 'recipe' | null

export function PromptEditorPane() {
  const state = useWorkbench()
  const [pickerSlot, setPickerSlot] = useState<import('../../types/workbench').AssetType | null>(null)
  const [saveTarget, setSaveTarget] = useState<SaveTarget>(null)
  const [saveName, setSaveName] = useState('')
  const [saveFavorite, setSaveFavorite] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const structuredEditable = state.promptMode === 'structured'

  async function handleSaveConfirm(): Promise<void> {
    if (!saveName.trim() || saving) return
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
        setMessage({ kind: 'ok', text: '已保存为 Prompt（可在"提示词"页查看）' })
      } else if (saveTarget === 'recipe') {
        await recipeApi.create({ name: saveName.trim(), favorite: saveFavorite, snapshot })
        setMessage({ kind: 'ok', text: '已保存为配方（含 Prompt 与素材快照）' })
      }
      setSaveTarget(null)
      setSaveName('')
      setSaveFavorite(false)
    } catch (error) {
      const text = error instanceof ApiRequestError ? error.message : '保存失败'
      setMessage({ kind: 'error', text })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pane">
      <header className="pane__header">
        <h2 className="pane__title">Prompt 编辑</h2>
        <div className="segmented">
          <button
            type="button"
            className={`segmented__item${state.promptMode === 'structured' ? ' segmented__item--active' : ''}`}
            onClick={() => setPromptMode('structured')}
          >
            结构化
          </button>
          <button
            type="button"
            className={`segmented__item${state.promptMode === 'full' ? ' segmented__item--active' : ''}`}
            onClick={() => setPromptMode('full')}
          >
            完整 Prompt
          </button>
        </div>
      </header>

      {structuredEditable ? (
        <div className="structured-editor">
          {STRUCTURED_FIELDS.map(({ key, label }) => {
            const slotRef = (key === 'face' || key === 'clothing' || key === 'pose' || key === 'scene')
              ? state.selectedAssets[key]
              : undefined
            const isSlot = key === 'face' || key === 'clothing' || key === 'pose' || key === 'scene'
            return (
              <div key={key} className="field">
                <div className="field__label-row">
                  <label className="field__label" htmlFor={`field-${key}`}>{label}</label>
                  {isSlot && (
                    <div className="field__actions">
                      {slotRef && (
                        <button
                          type="button"
                          className="btn btn--ghost btn--xs"
                          title="移除已选素材（不影响素材本身）"
                          onClick={() => clearAssetFromSlot(key as 'face' | 'clothing' | 'pose' | 'scene')}
                        >
                          已选: {slotRef.name} ✕
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn btn--ghost btn--xs"
                        onClick={() => setPickerSlot(key as 'face' | 'clothing' | 'pose' | 'scene')}
                      >
                        选择素材
                      </button>
                    </div>
                  )}
                </div>
                <textarea
                  id={`field-${key}`}
                  className="input input--area"
                  rows={key === 'extra' ? 2 : 2}
                  value={state.structured[key]}
                  onChange={(event) => setStructuredField(key, event.target.value)}
                />
              </div>
            )
          })}
        </div>
      ) : (
        <div className="field">
          <label className="field__label" htmlFor="full-prompt">完整 Prompt</label>
          <textarea
            id="full-prompt"
            className="input input--area"
            rows={12}
            value={state.fullPrompt}
            onChange={(event) => setFullPrompt(event.target.value)}
            placeholder="输入完整正向 Prompt"
          />
        </div>
      )}

      <div className="field">
        <label className="field__label" htmlFor="negative-prompt">Negative Prompt</label>
        <textarea
          id="negative-prompt"
          className="input input--area"
          rows={3}
          value={state.negativePrompt}
          onChange={(event) => setNegativePrompt(event.target.value)}
          placeholder="可选：不希望出现的内容"
        />
      </div>

      <ComposePreview mode={state.promptMode} structured={state.structured} fullPrompt={state.fullPrompt} />

      <div className="pane__footer">
        <button type="button" className="btn btn--primary" onClick={() => setSaveTarget('prompt')}>
          保存为 Prompt
        </button>
        <button type="button" className="btn" onClick={() => setSaveTarget('recipe')}>
          保存为配方
        </button>
      </div>

      {message && (
        <p className={`notice notice--${message.kind}`} role="status">{message.text}</p>
      )}

      {saveTarget && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSaveTarget(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={saveTarget === 'prompt' ? '保存为 Prompt' : '保存为配方'}
            onClick={(event) => event.stopPropagation()}
          >
            <h3 className="modal__title">{saveTarget === 'prompt' ? '保存为 Prompt' : '保存为配方'}</h3>
            <div className="field">
              <label className="field__label" htmlFor="save-name">名称</label>
              <input
                id="save-name"
                className="input"
                value={saveName}
                onChange={(event) => setSaveName(event.target.value)}
                autoFocus
              />
            </div>
            <label className="check">
              <input type="checkbox" checked={saveFavorite} onChange={(event) => setSaveFavorite(event.target.checked)} />
              <span>收藏</span>
            </label>
            <div className="modal__actions">
              <button type="button" className="btn" onClick={() => setSaveTarget(null)}>取消</button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={!saveName.trim() || saving}
                onClick={() => void handleSaveConfirm()}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {pickerSlot && (
        <AssetPickerDrawer
          slot={pickerSlot}
          onClose={() => setPickerSlot(null)}
          onPicked={(promptText: string, ref) => {
            applyAssetToSlot(pickerSlot, promptText, ref)
            setPickerSlot(null)
          }}
        />
      )}
    </div>
  )
}

export type { StructuredPrompt }
