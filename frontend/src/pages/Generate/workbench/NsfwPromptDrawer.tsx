import { useState } from 'react'
import { Button } from '../../../components/ui/Button'
import { Drawer } from '../../../components/ui/Drawer'
import {
  NSFW_LEVELS,
  NSFW_MODEL_LABEL,
  NSFW_TAG_GROUPS,
  buildLevelNegative,
  buildLevelPrompt,
  tagDetailLevel,
  tagPayload,
  type NsfwLevel,
  type NsfwModelSystem,
} from './nsfwPresets'

export interface NsfwPromptDrawerProps {
  /** 当前输入模式，用于提示模板会切到完整 Prompt。 */
  mode: 'structured' | 'full'
  /** 标签追加目标（如「完整 Prompt」「结构化 · 风格」）。 */
  targetLabel: string
  /** 打开时定位的分级（快捷条会传入）。 */
  initialLevel?: NsfwLevel
  onClose: () => void
  onApplyTemplate: (positive: string, negative: string) => void
  onAppendTag: (tag: string) => void
}

/**
 * v0.37.7：分级词库升级为「模型体系 + 分级页签 + 多场景模板 + 分类标签页」。
 * 模板 = 质量词 + 评级词 + 场景标签；负向固定带未成年压制词，不提供移除入口。
 */
export function NsfwPromptDrawer({
  mode,
  targetLabel,
  initialLevel = 'L1',
  onClose,
  onApplyTemplate,
  onAppendTag,
}: NsfwPromptDrawerProps) {
  const [model, setModel] = useState<NsfwModelSystem>('miao')
  const [level, setLevel] = useState<NsfwLevel>(initialLevel)
  const [groupId, setGroupId] = useState<string>(NSFW_TAG_GROUPS[0].id)

  const levelMeta = NSFW_LEVELS.find((item) => item.level === level) ?? NSFW_LEVELS[0]
  const activeGroup = NSFW_TAG_GROUPS.find((group) => group.id === groupId) ?? NSFW_TAG_GROUPS[0]
  const templateCount = NSFW_LEVELS.reduce((total, item) => total + item.variants.length, 0)
  const tagCount = NSFW_TAG_GROUPS.reduce((total, group) => total + group.tags.length, 0)

  return (
    <Drawer open onClose={onClose} title="NSFW 分级模板与词库" width="wide">
      <div className="nsfw-lib">
        <p className="ds-notice ds-notice--warning">
          仅用于成年虚构角色。负向固定包含 child / loli / toddler / young / aged down，模板不提供移除入口。
        </p>

        <section className="nsfw-lib__section">
          <div className="nsfw-lib__section-head">
            <h3 className="nsfw-lib__title">模型体系</h3>
            <span className="muted">当前动漫工作流使用 MiaoMiao v14</span>
          </div>
          <div className="nsfw-lib__models" role="group" aria-label="模型体系">
            {(Object.keys(NSFW_MODEL_LABEL) as NsfwModelSystem[]).map((key) => (
              <button
                key={key}
                type="button"
                className={`nsfw-lib__model${model === key ? ' is-active' : ''}`}
                aria-pressed={model === key}
                onClick={() => setModel(key)}
              >
                {NSFW_MODEL_LABEL[key]}
              </button>
            ))}
          </div>
        </section>

        <section className="nsfw-lib__section">
          <div className="nsfw-lib__section-head">
            <h3 className="nsfw-lib__title">分级模板 · {templateCount} 套</h3>
            <span className="muted">套用后切到完整 Prompt 并同步负向</span>
          </div>
          <div className="nsfw-lib__tabs" role="tablist" aria-label="分级">
            {NSFW_LEVELS.map((item) => (
              <button
                key={item.level}
                type="button"
                role="tab"
                aria-selected={level === item.level}
                className={`nsfw-lib__tab${level === item.level ? ' is-active' : ''}`}
                onClick={() => setLevel(item.level)}
              >
                {item.label}
                <span className="nsfw-lib__tab-count">{item.variants.length}</span>
              </button>
            ))}
          </div>
          <p className="muted nsfw-lib__level-desc">{levelMeta.description}</p>
          <div className="nsfw-lib__levels">
            {levelMeta.variants.map((variant) => (
              <article className="nsfw-lib__level" key={variant.id}>
                <header className="nsfw-lib__level-head">
                  <strong>{variant.label}</strong>
                  <span className="muted">{variant.id}</span>
                </header>
                <p className="muted">{variant.description}</p>
                <p className="nsfw-lib__preview" title={buildLevelPrompt(level, model, variant.id)}>
                  {buildLevelPrompt(level, model, variant.id)}
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    onApplyTemplate(
                      buildLevelPrompt(level, model, variant.id),
                      buildLevelNegative(model),
                    )
                  }
                >
                  套用
                </Button>
              </article>
            ))}
          </div>
          {mode === 'structured' && (
            <p className="muted nsfw-lib__hint">当前是结构化模式；套用模板会切换为完整模式，已填写的结构化字段不会丢失。</p>
          )}
        </section>

        <section className="nsfw-lib__section">
          <div className="nsfw-lib__section-head">
            <h3 className="nsfw-lib__title">标签库 · {tagCount} 个</h3>
            <span className="muted">点击追加到：{targetLabel}</span>
          </div>
          <div className="nsfw-lib__tabs nsfw-lib__tabs--wrap" role="tablist" aria-label="标签分类">
            {NSFW_TAG_GROUPS.map((group) => (
              <button
                key={group.id}
                type="button"
                role="tab"
                aria-selected={groupId === group.id}
                className={`nsfw-lib__tab${groupId === group.id ? ' is-active' : ''}`}
                onClick={() => setGroupId(group.id)}
              >
                {group.label}
                <span className="nsfw-lib__tab-count">{group.tags.length}</span>
              </button>
            ))}
          </div>
          <div className="nsfw-lib__group">
            <div className="nsfw-lib__group-head">
              <span>{activeGroup.label}</span>
              {activeGroup.hint && <span className="muted">{activeGroup.hint}</span>}
              <span className="nsfw-lib__legend">背景越深 = 提交的提示词越详细</span>
            </div>
            <div className="nsfw-lib__chips">
              {activeGroup.tags.map((item) => {
                const depth = tagDetailLevel(item)
                const payload = tagPayload(item, model)
                return (
                  <button
                    key={item.tag}
                    type="button"
                    className={`nsfw-lib__chip nsfw-lib__chip--d${depth}`}
                    title={`${item.label} — ${payload}`}
                    data-tip={item.note}
                    onClick={() => onAppendTag(payload)}
                  >
                    <span>{item.label}</span>
                    <code>
                      {item.expand
                        ? `+${item.expand.split(',').filter((part) => part.trim()).length} 标签`
                        : payload}
                    </code>
                  </button>
                )
              })}
            </div>
          </div>
        </section>
      </div>
    </Drawer>
  )
}
