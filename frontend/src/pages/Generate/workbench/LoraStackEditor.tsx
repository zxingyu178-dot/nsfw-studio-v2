import { Input } from '../../../components/ui'
import { PopoverSelect } from '../../../components/ui/ui3'

export interface LoraEntry {
  name: string
  strength_model: number
  strength_clip: number
}

/** 任务级 LoRA 栈：默认一行，选中后出现第二行（binding 上限 2 条）。 */
export function LoraStackEditor({
  loras,
  options,
  onChange,
}: {
  loras: LoraEntry[]
  options: string[]
  onChange: (next: LoraEntry[]) => void
}) {
  const rows = loras.length >= 1 ? [0, 1] : [0]
  const update = (index: number, entry: LoraEntry | null) => {
    const next = loras.slice()
    if (entry === null) {
      next.splice(index, 1)
    } else if (index < next.length) {
      next[index] = entry
    } else {
      next.push(entry)
    }
    onChange(next)
  }

  return (
    <div className="wb-param">
      <span className="wb-param__label">LoRA</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
        {rows.map((index) => {
          const entry = loras[index]
          return (
            <div
              key={index}
              style={{ display: 'flex', gap: 8, alignItems: 'center', width: '100%' }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <PopoverSelect
                  value={entry?.name ?? ''}
                  onChange={(name) => {
                    if (!name) {
                      update(index, null)
                      return
                    }
                    update(index, {
                      name,
                      strength_model: entry?.strength_model ?? 0.8,
                      strength_clip: entry?.strength_clip ?? 0.8,
                    })
                  }}
                  ariaLabel={`LoRA ${index + 1}`}
                  options={[
                    { value: '', label: index === 0 ? '不使用 LoRA' : '不使用第二条' },
                    ...options.map((name) => ({ value: name, label: name })),
                  ]}
                />
              </div>
              {entry && (
                <Input
                  type="number"
                  min={-2}
                  max={2}
                  step={0.05}
                  value={entry.strength_model}
                  aria-label={`LoRA ${index + 1} 强度`}
                  style={{ width: 72 }}
                  onChange={(event) => {
                    const strength = Number(event.target.value)
                    update(index, {
                      ...entry,
                      strength_model: strength,
                      strength_clip: strength,
                    })
                  }}
                />
              )}
            </div>
          )
        })}
      </div>
      <span className="wb-param__label">最多 2 条 · 强度 -2～2</span>
    </div>
  )
}
