# UI 3.0 共享设计基础层 — 冻结 API（UI3_SPEC）

> Phase 0.14 / NSFW Studio v0.14。
> 本文件是 Lightbox / Generate / Power UI 三个消费方**唯一**的 UI 基础约定。
> 消费方只允许**读**本层，不得修改本层文件（见末尾「共享只读清单」）。
> 目标：三处 UI 不分裂，禁止业务页裸用 `<button>` / `<select>`。

模块根：`frontend/src/components/ui/ui3/`
统一入口：`import { IconButton, PopoverSelect, ... } from '@/components/ui/ui3'`
（相对路径示例：`../../components/ui/ui3`）。样式由 `ui3/index.ts` 自动引入 `ui3.css`。

---

## 0. 硬性规则

1. 业务页面（pages/、components 下的业务组件）**禁止**直接出现裸 `<button>` / `<select>` / `<input type=number>` 原生控件。
   - 唯一例外：本层 `ui3/` 原语**内部**允许使用原生 `<button>`/`<input>` 等。
2. 禁止 emoji / 系统字符作主 icon；一律用本层 `./icons` 的 SVG 组件。
3. 颜色一律引用 CSS token（`themes/tokens.css`），**不得**在组件/业务 CSS 散写色值。
   所有 `var(--x)` 引用由 `themes/design_tokens.test.ts` 守卫，未定义会红。
4. 不得引入 Ant / MUI / Element / Bootstrap 等大 UI 框架。
5. 新增 token 必须同时补 `:root`（Dark）与 `[data-theme='light']`（Light）两套。

---

## 1. 新增 Token（`src/themes/tokens.css`，Dark + Light 双套）

| Token | 用途 |
|---|---|
| `--control-bg` | 控件静止底色（icon 按钮/输入/下拉） |
| `--control-hover` | 控件 hover 底色 |
| `--control-active` | 控件选中/按下底色 |
| `--control-border` | 控件描边 |
| `--canvas-bg` | 中栏画布背景（中性，让图片跳出） |
| `--panel-divider` | 面板内细分隔线 |
| `--action-gradient-start` | 主动作渐变起点 |
| `--action-gradient-end` | 主动作渐变终点 |
| `--glow-accent` | 克制冷色状态光晕 |
| `--icon-muted` | icon 默认色（=fg-muted） |
| `--icon-active` | icon 选中/强调色（=accent-strong） |
| `--icon-success` | icon 成功绿（=ok） |
| `--icon-danger` | icon 危险红（=danger） |
| `--icon-favorite` | icon 收藏琥珀（=favorite） |

> 历史 token（`--accent` / `--ok` / `--danger` / `--favorite` / `--surface-*` / `--radius-*` / `--space-*` / `--text-*` / `--z-*` 等）继续沿用。

---

## 2. SVG Icon 集（`ui3/icons.tsx`）

规格：viewBox 24，`stroke` 风格，`currentColor`，round cap/join；尺寸档 `14 | 16 | 18 | 20`（默认 16），`strokeWidth` 默认 1.6（区间 1.5~1.8）。颜色由父级 `color` / tone 控制。

通用 props：`{ size?: 14|16|18|20; strokeWidth?: number } & SVGProps`。

命名清单（全部从 `./icons` 导出）：

| 类别 | 图标 |
|---|---|
| 电源/运行 | `IconPower` `IconStart` `IconStop` `IconRestart` |
| 导航/视图 | `IconPrev` `IconNext` `IconFit` `IconActualSize` `IconInfo` `IconClose` |
| 图片处置 | `IconFavorite` `IconKeep` `IconReject` `IconZoomIn` |
| 步进/刷新 | `IconPlus` `IconMinus` `IconRefresh` |
| Seed | `IconRandom` `IconSeed` |
| 队列/任务 | `IconQueue` `IconPause` `IconResume` `IconCancel` |
| 状态 | `IconCheck` `IconWarning` |
| 触发器 | `IconChevronDown` |

> 用法：`<IconPrev size={16} />`。不要在业务页内联 `<svg>` 或复制路径。

---

## 3. 通用原语（`ui3/`，共 11 个）

### 3.1 Tooltip
```ts
interface TooltipProps { content: ReactNode; children: ReactNode; side?: 'top'|'bottom'|'left'|'right'; className?: string }
```
悬停/聚焦显示，`role="tooltip"`，`aria-describedby` 关联；`content` 为空则透传 children。

### 3.2 IconButton
```ts
type IconButtonTone = 'muted'|'active'|'success'|'danger'|'favorite'
type IconButtonSize = 'sm'|'md'|'lg'
interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode; label: string; tone?: IconButtonTone; size?: IconButtonSize;
  active?: boolean; loading?: boolean; tooltip?: ReactNode /* null 关闭浮层 */; tooltipSide?: TooltipSide
}
```
统一 icon 按钮，内嵌 Tooltip；`label` 同时作 `aria-label`。

### 3.3 ToolbarIcon
```ts
interface ToolbarIconProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode; label: string; selected?: boolean; disabled?: boolean; tooltipSide?: TooltipSide
}
```
工具栏图标项，`selected` 给选中底色，`aria-pressed`。

### 3.4 ActionButton
```ts
type ActionButtonVariant = 'default'|'danger'|'primary'
interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ActionButtonVariant; icon?: ReactNode; loading?: boolean; block?: boolean; children?: ReactNode
}
```
次级/通用文字动作按钮；`primary` 走 `--action-gradient-*` + 克制 glow。

### 3.5 ActionDock
```ts
interface ActionDockProps { children: ReactNode; className?: string; label?: string }
```
底部浮动图标坞，`role="toolbar"`；圆角浮层、克制背景，内部放若干 IconButton。Lightbox 与 Generate 中栏共用。

### 3.6 PopoverSelect（替代原生 select）
```ts
interface PopoverOption<T extends string = string> { value: T; label: ReactNode; icon?: ReactNode; disabled?: boolean; searchText?: string }
interface PopoverSelectProps<T extends string = string> {
  value: T; onChange: (v: T) => void; options: PopoverOption<T>[];
  placeholder?: ReactNode; leadingIcon?: ReactNode; disabled?: boolean; ariaLabel?: string
}
```
ARIA：trigger `button[aria-haspopup=listbox][aria-expanded]` + `role=listbox` + `role=option[aria-selected]`。
键盘：`↑/↓` 高亮、`Enter` 选中、`Esc` 关闭、可打印字符 typeahead 前缀匹配；点击外部关闭。受控。

### 3.7 ChoiceTile
```ts
type ChoiceShape = '1:1'|'3:4'|'4:3'|'9:16'|'16:9'|'2:3'
interface ChoiceTileProps { shape: ChoiceShape; selected?: boolean; onSelect?: () => void; label?: ReactNode; disabled?: boolean }
```
以 `aspect-ratio` 形状预览，而非纯文字。

### 3.8 ChoiceGrid
```ts
interface ChoiceGridProps { children: ReactNode; columns?: number; label?: string }
```
ChoiceTile 容器网格；`columns` 固定列数，缺省 auto-fill。

### 3.9 NumberStepper
```ts
interface NumberStepperProps {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number;
  chips?: number[] /* 如 [1,2,4,6,8] */; disabled?: boolean; ariaLabel?: string
}
```
`-`/数值/`+`；步进与直接输入都按 min/max 钳制；Enter 提交、Esc 还原；可选快捷 chips。

### 3.10 PowerButton
```ts
type PowerStatus = 'off'|'starting'|'on'|'error'
interface PowerButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> { status?: PowerStatus; label?: string; stateText?: string }
```
顶部电源：icon + 短状态文本，不开大按钮框。

### 3.11 StatusPill
```ts
type StatusTone = 'online'|'offline'|'starting'|'external'|'conflict'|'error'
interface StatusPillProps { tone?: StatusTone; children: ReactNode; pulse?: boolean }
```
状态点 + 短词胶囊。

---

## 4. useOverlayScrollLock（`src/hooks/useOverlayScrollLock.ts`）

```ts
useOverlayScrollLock(locked: boolean): void
```
- `locked=true` 时锁定 `html` / `body` / `.app-shell__main` 三层 `overflow`，并记录 main 的 `scrollTop`；
- 模块级 **ref-count**：嵌套 overlay（Lightbox→Confirm）内层关闭不提前解除外层锁，计数归 0 才恢复；
- 关闭/卸载时恢复加锁前的 `overflow` 与 `scrollTop`。
- 注意：真正滚动容器是 `.app-shell__main`，只锁 body 不够。

---

## 5. 暗色适配约定

- 本层组件 CSS 只引用 token，Dark/Light 由 `data-theme` 自动切换，组件内**不写**颜色。
- icon 颜色默认 `currentColor`，由父级 tone / token 控制：
  默认 `--icon-muted`，active `--icon-active`，成功 `--icon-success`，危险 `--icon-danger`，收藏 `--icon-favorite`。
- 浮层背景统一 `--control-bg` / `--surface-3`，边框 `--control-border`，禁止自定义玻璃拟态/满屏边框。

---

## 6. 共享只读清单（后续消费方**不得修改**）

以下文件为本层冻结产物，消费方只 import、不改写：

```
frontend/src/components/ui/UI3_SPEC.md
frontend/src/components/ui/ui3/index.ts
frontend/src/components/ui/ui3/ui3.css
frontend/src/components/ui/ui3/icons.tsx
frontend/src/components/ui/ui3/Tooltip.tsx
frontend/src/components/ui/ui3/IconButton.tsx
frontend/src/components/ui/ui3/ToolbarIcon.tsx
frontend/src/components/ui/ui3/ActionButton.tsx
frontend/src/components/ui/ui3/ActionDock.tsx
frontend/src/components/ui/ui3/PopoverSelect.tsx
frontend/src/components/ui/ui3/ChoiceTile.tsx
frontend/src/components/ui/ui3/ChoiceGrid.tsx
frontend/src/components/ui/ui3/NumberStepper.tsx
frontend/src/components/ui/ui3/PowerButton.tsx
frontend/src/components/ui/ui3/StatusPill.tsx
frontend/src/hooks/useOverlayScrollLock.ts
frontend/src/themes/tokens.css   # 新增 token 追加段（Phase 0.14 段），不得改名/删改历史段
```

> 需要新原语/新 token 时，先与基础层维护者对齐再追加，禁止在消费方页面另起样式。
