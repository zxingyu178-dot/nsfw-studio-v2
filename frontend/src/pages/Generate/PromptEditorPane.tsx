import { useRef, useState, type ChangeEvent } from 'react'
import { ApiRequestError, imageApi, promptApi, recipeApi } from '../../api/client'
import { ComposePreview } from '../../components/ComposePreview'
import { ImagePickerDrawer } from '../../components/ImagePickerDrawer'
import { STRUCTURED_FIELDS, imageContentUrl, type StructuredPrompt } from '../../types/workbench'
import {
  applyAssetToSlot,
  clearAssetFromSlot,
  clearInputImage,
  setFullPrompt,
  setInputImage,
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
  const [imagePickerOpen, setImagePickerOpen] = useState(false)
  const [saveTarget, setSaveTarget] = useState<SaveTarget>(null)
  const [saveName, setSaveName] = useState('')
  const [saveFavorite, setSaveFavorite] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const structuredEditable = state.promptMode === 'structured'
  const inputImage = state.inputImages[0] ?? null

  /** §七：上传新图片 → 先正式导入 Gallery（hash 去重）→ 再选择该 Image（只使用 image_id） */
  async function handleUploadFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0] ?? null
    event.target.value = '' // 允许重复选择同一文件
    if (!file || uploading) return
    setUploading(true)
    setMessage(null)
    try {
      const result = await imageApi.importFiles([file])
      if (result.imported_count > 0) {
        setInputImage(result.imported[0].image.id)
        setMessage({ kind: 'ok', text: '已上传并导入图库，已设为输入图片' })
      } else if (result.duplicate_count > 0) {
        setInputImage(result.duplicates[0].image_id)
        setMessage({ kind: 'ok', text: '该图片已经存在，已直接引用图库中的图片' })
      } else {
        setMessage({ kind: 'error', text: result.failed[0]?.message ?? '导入失败' })
      }
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof ApiRequestError ? error.message : '导入失败' })
    } finally {
      setUploading(false)
    }
  }

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

      {/* ===== 输入图片（Phase 5 §七：独立区域，不塞进八栏 Prompt；仅"图片生成"模式） ===== */}
      {state.mode === 'image' && (
        <section className="input-image" aria-label="输入图片">
          <div className="field__label-row">
            <span className="field__label">输入图片</span>
            <span className="muted">（{inputImage ? '1 / 1' : '0 / 1'}）</span>
          </div>
          {inputImage ? (
            <div className="input-image__body">
              {inputImage.missing ? (
                <div className="input-image__missing">输入图片已丢失（请移除后重新选择）</div>
              ) : (
                <img
                  className="input-image__thumb"
                  src={imageContentUrl(inputImage.image_id)}
                  alt="当前输入图片"
                />
              )}
              <div className="field__actions">
                <button type="button" className="btn btn--sm" onClick={() => setImagePickerOpen(true)}>
                  更换
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={clearInputImage}>
                  移除
                </button>
              </div>
            </div>
          ) : (
            <div className="field__actions">
              <button type="button" className="btn btn--sm" onClick={() => setImagePickerOpen(true)}>
                从图库选择
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? '导入中…' : '上传新图片'}
              </button>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp"
            hidden
            onChange={(event) => void handleUploadFile(event)}
          />
        </section>
      )}

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

      {imagePickerOpen && (
        <ImagePickerDrawer
          onClose={() => setImagePickerOpen(false)}
          onPicked={(image) => {
            setInputImage(image.id)
            setImagePickerOpen(false)
          }}
        />
      )}
    </div>
  )
}

export type { StructuredPrompt }
