/**
 * PromptSlotRow（v0.15 Task 3）：单槽位聚焦编辑。
 * 折叠态：label + 素材 chip + 单行 summary + ＋素材；
 * 展开态：仅当前 active slot 显示 textarea（一次只展开一个结构化 slot）。
 */
import type { ReactNode } from 'react'
import { Textarea } from '../../../components/ui'

export interface PromptSlotRowProps {
  label: string
  value: string
  active: boolean
  /** 自定义展开态输入框占位（默认「输入 {label}描述…」）。 */
  placeholder?: string
  /** 已选素材名称（用于 chip 展示），无则 null。 */
  assetName?: string | null
  /** 素材操作按钮（＋ / 移除），由调用方注入，保持现有 AssetPicker/API 不变。 */
  assetAction?: ReactNode
  onActivate: () => void
  onChange: (value: string) => void
}

export function PromptSlotRow({
  label,
  value,
  active,
  placeholder,
  assetName,
  assetAction,
  onActivate,
  onChange,
}: PromptSlotRowProps) {
  // 标签本身以「描述」结尾时（如「额外描述」）不再拼第二个「描述」，避免出现「额外描述描述」。
  const summaryPlaceholder = `点击添加${label}${label.endsWith('描述') ? '' : '描述'}…`
  return (
    <div
      className={`wb4-slot${active ? ' wb4-slot--active' : ''}${value.trim() ? ' wb4-slot--filled' : ''}`}
    >
      <div className="wb4-slot__top">
        <button
          type="button"
          className="wb4-slot__label"
          aria-expanded={active}
          onClick={onActivate}
        >
          {label}
        </button>
        <span className="wb4-slot__actions">
          {assetName && (
            <span className="wb-chip" title="已选素材（点 × 移除，不影响素材本身）">
              <span className="wb-chip__name">{assetName}</span>
            </span>
          )}
          {assetAction}
        </span>
      </div>
      {active ? (
        <Textarea
          className="wb4-slot__textarea"
          rows={3}
          value={value}
          autoFocus
          placeholder={placeholder ?? `输入${label}描述…`}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <button type="button" className="wb4-slot__summary" onClick={onActivate}>
          {value.trim() || <span className="wb4-slot__placeholder">{summaryPlaceholder}</span>}
        </button>
      )}
    </div>
  )
}

export default PromptSlotRow
