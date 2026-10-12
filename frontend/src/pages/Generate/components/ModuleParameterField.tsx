import { Checkbox, Field, Input, Select, Slider } from '../../../components/ui'
import type { ModuleParameterDTO } from '../../../types/workbench'

/**
 * 按 ParameterSpec 元数据渲染一个可配置参数（float/int/bool/enum）。
 * 值写入 WorkflowModuleRef.config——模块参数唯一事实源。
 *
 * 从 SettingsPane.tsx 纯拆分（Phase 0.12 任务 9：只重构，不改行为 / API）。
 */
export function ModuleParameterField({
  param,
  value,
  onChange,
}: {
  param: ModuleParameterDTO
  value: unknown
  onChange: (value: unknown) => void
}) {
  const resolved = value ?? param.default
  const label = param.title || param.name

  if (param.type === 'bool') {
    return (
      <Field>
        <Checkbox
          checked={Boolean(resolved)}
          onChange={(event) => onChange(event.target.checked)}
          label={label}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  if (param.type === 'enum') {
    return (
      <Field label={label}>
        <Select
          value={String(resolved ?? '')}
          onChange={(event) => onChange(event.target.value)}
          options={(param.enum_values ?? []).map((option) => ({ value: option, label: option }))}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  const numeric = Number(resolved ?? 0)

  if (param.type === 'int') {
    return (
      <Field label={label}>
        <Input
          type="number"
          min={param.min ?? undefined}
          max={param.max ?? undefined}
          step={param.step ?? 1}
          value={numeric}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  if (param.type === 'float') {
    return (
      <Field label={label}>
        <Slider
          min={param.min ?? 0}
          max={param.max ?? 1}
          step={param.step ?? 0.01}
          value={numeric}
          onChange={(v) => onChange(v)}
          ariaLabel={label}
          valueSlot={<span>{numeric.toFixed(2)}</span>}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  return null
}
