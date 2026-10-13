/**
 * UI 3.0 统一 SVG Icon 集（Phase 0.14 共享设计基础层）
 *
 * 规格（任务书 §二十四 / UI3_SPEC）：
 * - stroke 风格 React 组件，viewBox 24x24；
 * - 尺寸档 14 / 16 / 18 / 20（默认 16）；
 * - strokeWidth 默认 1.6（区间 1.5~1.8）；
 * - round cap / round join，currentColor 描边；
 * - 颜色由消费方通过 CSS color 控制（引用 --icon-muted / --icon-active 等 token）；
 * - 禁止 emoji / 系统字符作主 icon。
 *
 * 这是冻结 API：后续 Lightbox / Generate / Power UI 一律从 './icons' 取 icon，
 * 不得在业务页内联 <svg> 或复制路径。
 */
import type { SVGProps } from 'react'

export type IconSize = 14 | 16 | 18 | 20

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'strokeWidth'> {
  /** 尺寸档：14 / 16 / 18 / 20，默认 16。 */
  size?: IconSize
  /** 描边宽度，默认 1.6（规格区间 1.5~1.8）。 */
  strokeWidth?: number
}

function base({ size = 16, strokeWidth = 1.6, ...rest }: IconProps): SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
    focusable: false,
    ...rest,
  }
}

/* ---------- 电源 / 运行控制 ---------- */

/** 电源符号（顶部竖线 + 半圆）。 */
export const IconPower = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="12" y1="3.5" x2="12" y2="11" />
    <path d="M6.5 6.6a8 8 0 1 0 11 0" />
  </svg>
)

/** 启动 / 播放（实心三角描边轮廓）。 */
export const IconStart = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M7 5.5v13l11-6.5-11-6.5z" />
  </svg>
)

/** 停止（方形）。 */
export const IconStop = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="7" y="7" width="10" height="10" rx="1.5" />
  </svg>
)

/** 重启 / 重跑（环形箭头）。 */
export const IconRestart = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="21 12 21 7 16 7" />
    <path d="M3 12a9 9 0 0 1 15-6.7L21 7" />
    <polyline points="3 12 3 17 8 17" />
    <path d="M21 12a9 9 0 0 1-15 6.7L3 17" />
  </svg>
)

/* ---------- 导航 / 视图 ---------- */

/** 上一张。 */
export const IconPrev = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="14.5 5.5 8.5 12 14.5 18.5" />
  </svg>
)

/** 下一张。 */
export const IconNext = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="9.5 5.5 15.5 12 9.5 18.5" />
  </svg>
)

/** 适应窗口（四角向内括号）。 */
export const IconFit = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 9V6a2 2 0 0 1 2-2h3" />
    <path d="M15 4h3a2 2 0 0 1 2 2v3" />
    <path d="M20 15v3a2 2 0 0 1-2 2h-3" />
    <path d="M9 20H6a2 2 0 0 1-2-2v-3" />
  </svg>
)

/** 100% 实际尺寸（四角向外箭头）。 */
export const IconActualSize = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="4 9 4 4 9 4" />
    <polyline points="20 9 20 4 15 4" />
    <polyline points="4 15 4 20 9 20" />
    <polyline points="20 15 20 20 15 20" />
  </svg>
)

/** 信息。 */
export const IconInfo = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <line x1="12" y1="11" x2="12" y2="16" />
    <circle cx="12" cy="8" r="0.6" fill="currentColor" stroke="none" />
  </svg>
)

/** 关闭。 */
export const IconClose = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="6" y1="6" x2="18" y2="18" />
    <line x1="18" y1="6" x2="6" y2="18" />
  </svg>
)

/* ---------- 图片处置 ---------- */

/** 收藏（心形）。 */
export const IconFavorite = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 20.5c-4.6-3-8-6.2-8-10.1A4.6 4.6 0 0 1 12 7.1a4.6 4.6 0 0 1 8 3.3c0 3.9-3.4 7.1-8 10.1z" />
  </svg>
)

/** 保留（对勾）。 */
export const IconKeep = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="5 12.5 10 17.5 19 7" />
  </svg>
)

/** 淘汰（圆圈 ×）。 */
export const IconReject = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <line x1="9" y1="9" x2="15" y2="15" />
    <line x1="15" y1="9" x2="9" y2="15" />
  </svg>
)

/** 放大 / 放大查看（放大镜 +）。 */
export const IconZoomIn = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="10.5" cy="10.5" r="6" />
    <line x1="15" y1="15" x2="20" y2="20" />
    <line x1="10.5" y1="8" x2="10.5" y2="13" />
    <line x1="8" y1="10.5" x2="13" y2="10.5" />
  </svg>
)

/* ---------- 步进 / 刷新 ---------- */

/** 加号。 */
export const IconPlus = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
)

/** 减号。 */
export const IconMinus = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
)

/** 刷新。 */
export const IconRefresh = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="21 12 21 7 16 7" />
    <path d="M3 12a9 9 0 0 1 15-6.7L21 7" />
    <polyline points="3 12 3 17 8 17" />
    <path d="M21 12a9 9 0 0 1-15 6.7L3 17" />
  </svg>
)

/* ---------- Seed ---------- */

/** 随机 seed（洗牌）。 */
export const IconRandom = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="16 3 21 3 21 8" />
    <line x1="4" y1="20" x2="21" y2="3" />
    <polyline points="21 16 21 21 16 21" />
    <line x1="15" y1="15" x2="21" y2="21" />
    <line x1="4" y1="4" x2="9" y2="9" />
  </svg>
)

/** 固定 seed（标签 / 芯片）。 */
export const IconSeed = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 7a2 2 0 0 1 2-2h8.5L20 12.5v4.5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
    <circle cx="9" cy="12" r="1.6" />
  </svg>
)

/* ---------- 队列 / 任务 ---------- */

/** 队列（列表行）。 */
export const IconQueue = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="4" y1="7" x2="20" y2="7" />
    <line x1="4" y1="12" x2="20" y2="12" />
    <line x1="4" y1="17" x2="14" y2="17" />
  </svg>
)

/** 暂停。 */
export const IconPause = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="9" y1="5.5" x2="9" y2="18.5" />
    <line x1="15" y1="5.5" x2="15" y2="18.5" />
  </svg>
)

/** 继续（与启动同形，语义别名）。 */
export const IconResume = (p: IconProps) => <IconStart {...p} />

/** 取消（禁止圈）。 */
export const IconCancel = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <line x1="5.6" y1="5.6" x2="18.4" y2="18.4" />
  </svg>
)

/* ---------- 状态 ---------- */

/** 检查 / 通过。 */
export const IconCheck = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="5 12.5 10 17.5 19 7" />
  </svg>
)

/** 警告（三角）。 */
export const IconWarning = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3.5 2.5 20h19L12 3.5z" />
    <line x1="12" y1="10" x2="12" y2="14" />
    <circle cx="12" cy="17.2" r="0.6" fill="currentColor" stroke="none" />
  </svg>
)

/** 下拉箭头（PopoverSelect 触发器用）。 */
export const IconChevronDown = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="6.5 9.5 12 15 17.5 9.5" />
  </svg>
)
