/**
 * PromptConsole 4.0（v0.15 Task 3）：左栏「生成什么」。
 * 8 栏业务语义不变；交互改为单槽位聚焦（一次只展开一个 slot，compact row 显示单行摘要）。
 * 默认 active：上次记忆（localStorage）→ 第一个有内容的 slot → 风格。
 * Negative / Prompt Preview 继续折叠，不常驻占高度。保存入口移到 WorkbenchBar「保存 ▾」。
 * 输入图片上传/素材选择逻辑与 API 全部沿用，不改业务。
 */
import { useRef, useState, type ChangeEvent } from 'react'
import { ApiRequestError, imageApi } from '../../../api/client'
import { ComposePreview } from '../../../components/ComposePreview'
import { ImagePickerDrawer } from '../../../components/ImagePickerDrawer'
import { Button, Field, SegmentedControl, Textarea } from '../../../components/ui'
import { IconButton, IconChevronDown, IconClose, IconPlus } from '../../../components/ui/ui3'
import { STRUCTURED_FIELDS, imageThumbUrl, type AssetType } from '../../../types/workbench'
import { resolveActiveSlot } from './resolveActiveSlot'
import {
  applyAssetToSlot,
  clearAssetFromSlot,
  clearInputImage,
  inputRoleLabel,
  requiredInputSlot,
  setFullPrompt,
  setInputImage,
  setNegativePrompt,
  setPromptMode,
  setStructuredField,
  useWorkbench,
} from '../../../stores/workbenchStore'
import { AssetPickerDrawer } from '../AssetPickerDrawer'
import { CollapsibleSection } from '../components/CollapsibleSection'
import { Pane } from '../Pane'
import { PromptSlotRow } from './PromptSlotRow'

const SLOT_KEYS: AssetType[] = ['face', 'clothing', 'pose', 'scene']
const ACTIVE_SLOT_KEY = 'workbench.activePromptSlot'

function isSlotKey(key: string): key is AssetType {
  return (SLOT_KEYS as string[]).includes(key)
}

export function PromptConsole({ onCollapse }: { onCollapse?: () => void } = {}) {
  const state = useWorkbench()
  const [pickerSlot, setPickerSlot] = useState<AssetType | null>(null)
  const [imagePickerOpen, setImagePickerOpen] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const structuredEditable = state.promptMode === 'structured'
  const inputImage = state.inputImages[0] ?? null

  // 默认 active slot：记忆（须为合法 slot key）→ 第一个有内容 → 风格。
  // v0.15.1：localStorage 非法值（旧值/手工值如 "foo"）不对应任何 slot，会导致 8 个 slot 全不 active，
  // 因此读取后交给 resolveActiveSlot 校验，非法值一律回退。
  let storedSlot: string | null = null
  try {
    storedSlot = typeof localStorage !== 'undefined' ? localStorage.getItem(ACTIVE_SLOT_KEY) : null
  } catch {
    storedSlot = null
  }
  const initialActive = resolveActiveSlot(state.structured, storedSlot)
  const [activeSlot, setActiveSlot] = useState<string>(initialActive)

  function activateSlot(key: string): void {
    setActiveSlot(key)
    try {
      localStorage.setItem(ACTIVE_SLOT_KEY, key)
    } catch {
      /* ignore */
    }
  }

  async function handleUploadFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0] ?? null
    event.target.value = ''
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

  const primaryModuleId = state.workflowModules[0]?.module_id
  const primaryCapabilities = state.moduleCatalog.find((m) => m.module_id === primaryModuleId)
  const required = requiredInputSlot(primaryCapabilities)
  const inputTitle = required ? inputRoleLabel(required.role) : '输入图片'
  const mismatch = inputImage && required && inputImage.role !== required.role

  return (
    <Pane
      title="PROMPT"
      actions={
        <div className="wb-pane__actions-row">
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
          {onCollapse && (
            <IconButton
              icon={<IconChevronDown size={14} className="wb-pane__collapse-icon wb-pane__collapse-icon--left" />}
              label="收起 Prompt 栏"
              onClick={onCollapse}
            />
          )}
        </div>
      }
    >
      {/* 输入图片（仅图片生成模式），逻辑沿用原 PromptEditorPane。 */}
      {state.mode === 'image' && (
        <section className="wb-input" aria-label="输入图片">
          <div className="wb-input__label-row">
            <span className="ds-field__label">{inputTitle}</span>
            <span className="muted">（{inputImage ? '1 / 1' : '0 / 1'}）</span>
          </div>
          {required?.description && <p className="muted wb-input__desc">{required.description}</p>}
          {mismatch && (
            <p className="ds-notice ds-notice--warning" role="alert">
              当前工作流需要「{inputRoleLabel(required.role)}」，当前输入为「{inputRoleLabel(inputImage.role)}」，已自动重映射；如不符请重新选择。
            </p>
          )}
          {inputImage ? (
            <div className="wb-input__body">
              {inputImage.missing ? (
                <div className="wb-input__missing">输入图片已丢失（请移除后重新选择）</div>
              ) : (
                <img className="wb-input__thumb" src={imageThumbUrl(inputImage.image_id)} alt="当前输入图片" />
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
        <div className="wb4-slots">
          {STRUCTURED_FIELDS.map(({ key, label }) => {
            const slotKey = isSlotKey(key) ? key : null
            const slotRef = slotKey ? state.selectedAssets[slotKey] : undefined
            return (
              <PromptSlotRow
                key={key}
                label={label}
                value={state.structured[key]}
                active={activeSlot === key}
                assetName={slotRef?.name ?? null}
                onActivate={() => activateSlot(key)}
                onChange={(value) => setStructuredField(key, value)}
                assetAction={
                  slotKey ? (
                    <span className="wb4-slot__asset">
                      {slotRef && (
                        <IconButton
                          icon={<IconClose size={14} />}
                          label={`移除已选素材 ${slotRef.name}`}
                          size="sm"
                          onClick={() => clearAssetFromSlot(slotKey)}
                        />
                      )}
                      <IconButton
                        icon={<IconPlus size={14} />}
                        label={`选择${label}素材`}
                        onClick={() => setPickerSlot(slotKey)}
                      />
                    </span>
                  ) : undefined
                }
              />
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

      <CollapsibleSection id="negative" title="Negative Prompt" defaultOpen={false}>
        <Textarea
          rows={3}
          value={state.negativePrompt}
          onChange={(event) => setNegativePrompt(event.target.value)}
          placeholder="可选：不希望出现的内容"
        />
      </CollapsibleSection>

      <CollapsibleSection id="preview" title="最终 Prompt Preview" defaultOpen={false}>
        <ComposePreview mode={state.promptMode} structured={state.structured} fullPrompt={state.fullPrompt} />
      </CollapsibleSection>

      {message && (
        <p className={`ds-notice ds-notice--${message.kind === 'ok' ? 'success' : 'error'}`} role="status">
          {message.text}
        </p>
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
    </Pane>
  )
}

export default PromptConsole
