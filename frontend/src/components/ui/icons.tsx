import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function base(p: IconProps) {
  const { size = 16, strokeWidth = 2, ...rest } = p
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: strokeWidth as number,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
    ...rest,
  }
}

export const IconPlay = (p: IconProps) => (
  <svg {...base(p)}>
    <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none" />
  </svg>
)

export const IconQueue = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="4" y1="7" x2="20" y2="7" />
    <line x1="4" y1="12" x2="20" y2="12" />
    <line x1="4" y1="17" x2="14" y2="17" />
  </svg>
)

export const IconPause = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="6" y="5" width="4" height="14" fill="currentColor" stroke="none" />
    <rect x="14" y="5" width="4" height="14" fill="currentColor" stroke="none" />
  </svg>
)

export const IconX = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="6" y1="6" x2="18" y2="18" />
    <line x1="18" y1="6" x2="6" y2="18" />
  </svg>
)

export const IconCheck = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="4 12 10 18 20 6" />
  </svg>
)

export const IconStar = (p: IconProps) => (
  <svg {...base(p)}>
    <polygon points="12 3 14.7 8.9 21 9.7 16.4 14 17.6 20.3 12 17.1 6.4 20.3 7.6 14 3 9.7 9.3 8.9 12 3" />
  </svg>
)

export const IconUpscale = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="15 4 20 4 20 9" />
    <polyline points="9 20 4 20 4 15" />
    <line x1="20" y1="4" x2="14" y2="10" />
    <line x1="4" y1="20" x2="10" y2="14" />
  </svg>
)

export const IconImage = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="8.5" cy="9.5" r="1.5" />
    <polyline points="21 16 15 10 9 16" />
  </svg>
)

export const IconRefresh = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="21 12 21 7 16 7" />
    <path d="M3 12a9 9 0 0 1 15-6.7L21 7" />
    <polyline points="3 12 3 17 8 17" />
    <path d="M21 12a9 9 0 0 1-15 6.7L3 17" />
  </svg>
)

export const IconUpload = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 16V4" />
    <polyline points="7 9 12 4 17 9" />
    <line x1="4" y1="20" x2="20" y2="20" />
  </svg>
)

export const IconGrid = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4" y="4" width="7" height="7" />
    <rect x="13" y="4" width="7" height="7" />
    <rect x="4" y="13" width="7" height="7" />
    <rect x="13" y="13" width="7" height="7" />
  </svg>
)

export const IconMasonry = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4" y="4" width="7" height="10" />
    <rect x="13" y="4" width="7" height="6" />
    <rect x="13" y="12" width="7" height="8" />
    <rect x="4" y="16" width="7" height="4" />
  </svg>
)

export const IconChevronDown = (p: IconProps) => (
  <svg {...base(p)}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
)

export const IconAlert = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3 2 20h20L12 3z" />
    <line x1="12" y1="10" x2="12" y2="14" />
    <circle cx="12" cy="17.2" r="0.6" fill="currentColor" />
  </svg>
)

export const IconInfo = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <line x1="12" y1="11" x2="12" y2="16" />
    <circle cx="12" cy="8" r="0.6" fill="currentColor" />
  </svg>
)

export const IconSave = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5 3h11l3 3v15H5z" />
    <rect x="8" y="3" width="8" height="6" />
    <rect x="8" y="13" width="8" height="8" />
  </svg>
)

export const IconArrowLeft = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="19" y1="12" x2="5" y2="12" />
    <polyline points="10 17 5 12 10 7" />
  </svg>
)

export const IconArrowRight = (p: IconProps) => (
  <svg {...base(p)}>
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="14 7 19 12 14 17" />
  </svg>
)

export const IconDrag = (p: IconProps) => (
  <svg {...base(p)} strokeWidth={1.5}>
    <circle cx="9" cy="6" r="1" fill="currentColor" />
    <circle cx="15" cy="6" r="1" fill="currentColor" />
    <circle cx="9" cy="12" r="1" fill="currentColor" />
    <circle cx="15" cy="12" r="1" fill="currentColor" />
    <circle cx="9" cy="18" r="1" fill="currentColor" />
    <circle cx="15" cy="18" r="1" fill="currentColor" />
  </svg>
)
