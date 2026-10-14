/**
 * UI3 DisclosureButton —— 可折叠分组标题按钮（语义化 disclosure）。
 *
 * 原生 <button> + aria-expanded / aria-controls（WAI-ARIA disclosure pattern），
 * 替代业务页原先自造的 div[role="button"][tabindex]。
 * 本组件位于 ui3 primitive 层，是允许使用原生 <button> 的豁免目录；
 * 业务页一律通过本组件收口，不再手写 role=button。
 */
import type { ButtonHTMLAttributes } from 'react'

export interface DisclosureButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'aria-expanded' | 'aria-controls'> {
  /** 展开态（对应 aria-expanded）。 */
  expanded: boolean
  /** 受控展开面板 id（对应 aria-controls）。 */
  controlsId: string
  type?: 'button' | 'submit' | 'reset'
}

export function DisclosureButton({
  expanded,
  controlsId,
  type = 'button',
  className = '',
  ...rest
}: DisclosureButtonProps) {
  return (
    <button
      type={type}
      className={className}
      aria-expanded={expanded}
      aria-controls={controlsId}
      {...rest}
    />
  )
}
