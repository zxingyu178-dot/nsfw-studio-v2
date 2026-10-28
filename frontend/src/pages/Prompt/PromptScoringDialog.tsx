/**
 * PromptScoringDialog（Phase 0.17.3）：人工评分 + 手动淘汰。
 *
 * - 7 个维度（人物/服饰/场景/构图/光影/风格/画质）各 1–5 分，总分 1–5；
 * - 手动设置状态：保留 / 候选 / 已淘汰（低分不会自动淘汰）；
 * - 保存 = 创建一条评估记录（POST evaluations）+ 如状态变化再 POST status。
 */
import { useState } from 'react'
import { promptApi } from '../../api/client'
import { Button, Field, Modal, Textarea, Input } from '../../components/ui'
import {
  PROMPT_EVALUATION_DIMENSIONS,
  PROMPT_STATUS_LABEL,
  type PromptDTO,
  type PromptEvaluationDimension,
  type PromptStatus,
} from '../../types/workbench'

/** v0.37：保存后只回传这次变化的字段，外层卡片原地更新，不整表重载。 */
export interface PromptScorePatch {
  latest_evaluation: PromptDTO['latest_evaluation']
  status: PromptStatus
  status_reason: string
}

interface PromptScoringDialogProps {
  prompt: PromptDTO
  onClose: () => void
  onSaved: (patch: PromptScorePatch) => void
}

const SCORE_MIN = 1
const SCORE_MAX = 5
const STATUSES: PromptStatus[] = ['keep', 'candidate', 'eliminated']

/** 维度默认分：优先用最近一次评估，否则 3 分（中性）。 */
function initialDimensions(prompt: PromptDTO): Record<PromptEvaluationDimension, number> {
  const latest = prompt.latest_evaluation?.dimension_scores ?? {}
  const values = {} as Record<PromptEvaluationDimension, number>
  for (const dimension of PROMPT_EVALUATION_DIMENSIONS) {
    values[dimension.key] = latest[dimension.key] ?? 3
  }
  return values
}

function averageScore(values: Record<PromptEvaluationDimension, number>): number {
  const scores = PROMPT_EVALUATION_DIMENSIONS.map((dimension) => values[dimension.key])
  if (scores.length === 0) return 3
  return Math.min(SCORE_MAX, Math.max(SCORE_MIN, Math.round(scores.reduce((sum, n) => sum + n, 0) / scores.length)))
}

export function PromptScoringDialog({ prompt, onClose, onSaved }: PromptScoringDialogProps) {
  const [dimensions, setDimensions] = useState<Record<PromptEvaluationDimension, number>>(() => initialDimensions(prompt))
  const [overall, setOverall] = useState<number>(() => prompt.latest_evaluation?.overall_score ?? averageScore(initialDimensions(prompt)))
  const [notes, setNotes] = useState<string>(prompt.latest_evaluation?.notes ?? '')
  const [status, setStatus] = useState<PromptStatus>(prompt.status ?? 'candidate')
  const [reason, setReason] = useState<string>(prompt.status_reason ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function setDimension(key: PromptEvaluationDimension, score: number): void {
    const next = { ...dimensions, [key]: score }
    setDimensions(next)
    // 总分跟随维度平均（用户仍可手动改）。
    setOverall(averageScore(next))
  }

  async function handleSave(): Promise<void> {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const evaluation = await promptApi.createEvaluation(prompt.id, {
        overall_score: overall,
        dimension_scores: { ...dimensions },
        notes,
        prompt_version_id: prompt.current_version?.id ?? null,
      })
      if (status !== (prompt.status ?? 'candidate') || reason !== (prompt.status_reason ?? '')) {
        await promptApi.setStatus(prompt.id, { status, reason })
      }
      onSaved({ latest_evaluation: evaluation, status, status_reason: reason })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存评分失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open title={`评分 · ${prompt.name}`} onClose={onClose}>
      <div className="pp-score">
        <p className="muted pp-score__hint">
          评分只作为参考，不会自动淘汰；状态由你手动决定。
        </p>

        <div className="pp-score__status" role="group" aria-label="提示词状态">
          {STATUSES.map((value) => (
            <button
              key={value}
              type="button"
              className={`pp-score__status-btn${status === value ? ' pp-score__status-btn--active' : ''}`}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {PROMPT_STATUS_LABEL[value]}
            </button>
          ))}
        </div>

        <Field label="状态说明（可选）">
          <Input
            value={reason}
            placeholder="例如：出图稳定，保留；人脸崩，淘汰…"
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>

        <Field label="总分（1–5）">
          <ScorePicker value={overall} onChange={setOverall} ariaLabel="总分" />
        </Field>

        <div className="pp-score__dims">
          {PROMPT_EVALUATION_DIMENSIONS.map((dimension) => (
            <div className="pp-score__dim" key={dimension.key}>
              <span className="pp-score__dim-label">{dimension.label}</span>
              <ScorePicker
                value={dimensions[dimension.key]}
                onChange={(score) => setDimension(dimension.key, score)}
                ariaLabel={`${dimension.label}评分`}
              />
            </div>
          ))}
        </div>

        <Field label="备注（可选）">
          <Textarea value={notes} rows={3} placeholder="好在哪 / 差在哪，便于以后迭代" onChange={(event) => setNotes(event.target.value)} />
        </Field>

        {error && <p className="ds-notice ds-notice--error">{error}</p>}

        <div className="pp-score__actions">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button variant="primary" loading={busy} disabled={busy} onClick={() => void handleSave()}>
            保存评分
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ScorePicker({
  value,
  onChange,
  ariaLabel,
}: {
  value: number
  onChange: (score: number) => void
  ariaLabel: string
}) {
  return (
    <div className="pp-score__picker" role="group" aria-label={ariaLabel}>
      {Array.from({ length: SCORE_MAX - SCORE_MIN + 1 }, (_, index) => SCORE_MIN + index).map((score) => (
        <button
          key={score}
          type="button"
          className={`pp-score__score${value === score ? ' pp-score__score--active' : ''}`}
          aria-pressed={value === score}
          aria-label={`${ariaLabel} ${score} 分`}
          onClick={() => onChange(score)}
        >
          {score}
        </button>
      ))}
    </div>
  )
}

export default PromptScoringDialog
