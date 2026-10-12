import { useState } from 'react'
import { ApiRequestError, assetApi } from '../../api/client'
import { Button, Field, Input, Textarea } from '../../components/ui'
import type { AssetDTO } from '../../types/workbench'

interface AssetEditorProps {
  asset: AssetDTO
  onCancel: () => void
  onSaved: () => void
}

/** 素材编辑器：编辑 Prompt / Tags / 备注 / 替换预览图；保存后创建新版本（旧版本保留）。 */
export function AssetEditor({ asset, onCancel, onSaved }: AssetEditorProps) {
  const current = asset.current_version
  const [promptText, setPromptText] = useState(current?.prompt_text ?? '')
  const [notes, setNotes] = useState(current?.notes ?? '')
  const [tags, setTags] = useState((current?.tags ?? []).join('，'))
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(): Promise<void> {
    if (busy) return
    setBusy(true)
    setError(null)
    const formData = new FormData()
    formData.set('prompt_text', promptText)
    formData.set('notes', notes)
    formData.set(
      'tags',
      JSON.stringify(tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean)),
    )
    if (file) formData.set('preview', file)
    try {
      await assetApi.addVersion(asset.id, formData)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="as-edit">
      <h4 className="as-edit__title">编辑（保存后将创建新版本，旧版本保留）</h4>
      <Field label="Prompt">
        <Textarea rows={3} value={promptText} onChange={(event) => setPromptText(event.target.value)} />
      </Field>
      <Field label="Tags（逗号分隔）">
        <Input value={tags} onChange={(event) => setTags(event.target.value)} />
      </Field>
      <Field label="备注">
        <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
      </Field>
      <Field label="替换预览图（可选）">
        <Input
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </Field>
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      <div className="as-actions">
        <Button variant="secondary" onClick={onCancel}>取消</Button>
        <Button variant="primary" disabled={busy} onClick={() => void handleSubmit()}>
          保存为新版本
        </Button>
      </div>
    </div>
  )
}
