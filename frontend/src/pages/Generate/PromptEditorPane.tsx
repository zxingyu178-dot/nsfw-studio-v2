import { useRef, useState, type ChangeEvent } from 'react'
import { ApiRequestError, imageApi, promptApi, recipeApi } from '../../api/client'
import { ComposePreview } from '../../components/ComposePreview'
import { ImagePickerDrawer } from '../../components/ImagePickerDrawer'
import {
  Button,
  Checkbox,
  Field,
  Input,
  Modal,
  SegmentedControl,
  Textarea,
} from '../../components/ui'
import { STRUCTURED_FIELDS, imageContentUrl, type AssetType, type StructuredPrompt } from '../../types/workbench'
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
import { Pane } from './Pane'

type SaveTarget = 'prompt' | 'recipe' | null
const SLOT_KEYS: Array<'face' | 'clothing' | 'pose' | 'scene'> = ['face', 'clothing', 'pose', 'scene']

export function PromptEditorPane() {
  const state = useWorkbench()
  const [pickerSlot, setPickerSlot] = useState<AssetType | null>(null)
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
        setMessage({ kind: 'ok', text: '已保存为 Prompt（可在“提示词”页查看）' })
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

  const saveTitle = saveTarget === 'prompt' ? '保存为 Prompt' : '保存为配方'

  return (
    <Pane
      title="Prompt 编辑"
      actions={
        <SegmentedControl
          size="sm"
          value={state.promptMode}
          onChange={(m) => setPromptMode(m as typeof state.promptMode)}
          options={[
            { value: 'structured', label: '结构化' },
            { value: 'full', label: '完整 Prompt' },
          ]}
          ariaLabel="Prompt 编辑模式"
        />
      }
    >
      {/* ===== 输入图片（§七：独立区域，仅“图片生成”模式） ===== */}
      {state.mode === 'image' && (
        <section className="wb-input" aria-label="输入图片">
          <div className="wb-input__label-row">
            <span className="ds-field__label">输入图片</span>
            <span className="muted">（{inputImage ? '1 / 1' : '0 / 1'}）</span>
          </div>
          {inputImage ? (
            <div className="wb-input__body">
              {inputImage.missing ? (
                <div className="wb-input__missing">输入图片已丢失（请移除后重新选择）</div>
              ) : (
                <img
                  className="wb-input__thumb"
                  src={imageContentUrl(inputImage.image_id)}
                  alt="当前输入图片"
                />
              )}
              <div className="wb-input__actions">
                <Button size="sm" onClick={() => setImagePickerOpen(true)}>更换</Button>
                <Button size="sm" variant="ghost" onClick={clearInputImage}>移除</Button>
              </div>
            </div>
          ) : (
            <div className="wb-input__actions">
              <Button size="sm" onClick={() => setImagePickerOpen(true)}>从图库选择</Button>
              <Button size="sm" variant="ghost" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
                {uploading ? '导入中…' : '上传新图片'}
              </Button>
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
        <div className="wb-structured">
          {STRUCTURED_FIELDS.map(({ key, label }) => {
            const isSlot = (SLOT_KEYS as string[]).includes(key)
            const slotRef = isSlot ? state.selectedAssets[key as 'face'] : undefined
            return (
              <div key={key} className="wb-structured-field">
                <div className="wb-structured-field__top">
                  <span className="ds-field__label">{label}</span>
                  {isSlot && (
                    <span className="wb-structured-field__actions">
                      {slotRef && (
                        <Button
                          size="xs"
                          variant="ghost"
                          title="移除已选素材（不影响素材本身）"
                          onClick={() => clearAssetFromSlot(key as 'face')}
                        >
                          已选: {slotRef.name} ✕
                        </Button>
                      )}
                      <Button size="xs" variant="ghost" onClick={() => setPickerSlot(key as AssetType)}>
                        选择素材
                      </Button>
                    </span>
                  )}
                </div>
                <Textarea
                  rows={2}
                  value={state.structured[key]}
                  onChange={(event) => setStructuredField(key, event.target.value)}
                />
              </div>
            )
          })}
        </div>
      ) : (
        <Field label="完整 Prompt">
          <Textarea
            rows={12}
            value={state.fullPrompt}
            onChange={(event) => setFullPrompt(event.target.value)}
            placeholder="输入完整正向 Prompt"
          />
        </Field>
      )}

      <Field label="Negative Prompt">
        <Textarea
          rows={3}
          value={state.negativePrompt}
          onChange={(event) => setNegativePrompt(event.target.value)}
          placeholder="可选：不希望出现的内容"
        />
      </Field>

      <ComposePreview mode={state.promptMode} structured={state.structured} fullPrompt={state.fullPrompt} />

      <div className="wb-footer">
        <Button variant="primary" onClick={() => setSaveTarget('prompt')}>保存为 Prompt</Button>
        <Button variant="secondary" onClick={() => setSaveTarget('recipe')}>保存为配方</Button>
      </div>

      {message && (
        <p className={`ds-notice ds-notice--${message.kind === 'ok' ? 'success' : 'error'}`} role="status">
          {message.text}
        </p>
      )}

      <Modal
        open={saveTarget !== null}
        onClose={() => setSaveTarget(null)}
        title={saveTitle}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSaveTarget(null)}>取消</Button>
            <Button variant="primary" disabled={!saveName.trim() || saving} onClick={() => void handleSaveConfirm()}>
              保存
            </Button>
          </>
        }
      >
        <Field label="名称">
          <Input value={saveName} onChange={(event) => setSaveName(event.target.value)} autoFocus />
        </Field>
        <Checkbox
          label="收藏"
          checked={saveFavorite}
          onChange={(event) => setSaveFavorite(event.target.checked)}
        />
      </Modal>

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
    </Pane>
  )
}

export type { StructuredPrompt }
