# UI 设计系统（UI Design System）

> 项目：NSFW Studio V2 · 分支：`feature/ui-v1-redesign`
> 原则：**先扩展、不推翻**。保留 `themes/tokens.css` 现有变量名与深色 / 浅色双主题，补齐语义色、层级、焦点、动效与组件规格，使全站组件有唯一来源。

---

## 1. 设计原则

1. **信息层级优先**：标题、区块、控件三级清晰；主任务（生成 / 审阅）始终是视觉焦点。
2. **克制的配色**：中性色承载结构，强调色只用于主操作、当前状态与关键反馈；状态色（成功 / 警告 / 危险 / 信息）语义固定。
3. **一致的密度与节奏**：4px 基准间距网格，同类控件同高，同类区块同圆角。
4. **状态可见**：所有交互控件具备 hover / active / focus / disabled；加载、空、错误均有明确反馈。
5. **可访问**：可见焦点、非颜色信息、键盘可达、对比度达标；浮层关闭后焦点回到触发处。
6. **深色 / 浅色对等**：每个语义 Token 都有双主题取值，不允许某主题下硬编码颜色。

---

## 2. 色彩 Token

### 2.1 保留的现有变量（不改名）

`--bg` `--bg-soft` `--panel` `--border` `--fg` `--fg-muted` `--accent` `--accent-strong` `--ok` `--warn` `--offline`

### 2.2 新增语义色（双主题）

| Token | 用途 | Dark | Light |
|---|---|---|---|
| `--danger` | 错误 / 失败 / 危险操作主色 | `#e06060` | `#d34242` |
| `--danger-strong` | danger hover / 强调 | `#ff7878` | `#b82f2f` |
| `--danger-bg` | 危险弱底色（带透明） | `rgba(224,96,96,.14)` | `rgba(211,66,66,.10)` |
| `--info` | 信息提示 | `#5aa8e0` | `#2f7fb8` |
| `--info-bg` | 信息弱底色 | `rgba(90,168,224,.14)` | `rgba(47,127,184,.10)` |
| `--success-bg` | 成功弱底色 | `rgba(62,207,142,.14)` | `rgba(46,160,110,.10)` |
| `--warn-bg` | 警告弱底色 | `rgba(224,164,55,.14)` | `rgba(190,135,40,.12)` |
| `--accent-bg` | 强调弱底色（当前项 / 选中） | `rgba(138,170,255,.16)` | `rgba(74,108,226,.10)` |

> 弱底色统一"前景色 + 低透明度"模式，不再各自硬编码 rgba；状态文字与底色成对使用。

### 2.3 表面层级（Surface / Elevation）

| Token | 用途 | Dark | Light |
|---|---|---|---|
| `--surface-1` | 页面底层（= `--bg`） | 同 `--bg` | 同 `--bg` |
| `--surface-2` | 卡片 / 面板（= `--panel`） | 同 `--panel` | 同 `--panel` |
| `--surface-3` | 内嵌 / 输入框 / 浮层（= `--bg-soft`） | 同 `--bg-soft` | 同 `--bg-soft` |
| `--overlay` | 遮罩 | `rgba(0,0,0,.55)` | `rgba(0,0,0,.45)` |

层级关系固定：`surface-1（底） < surface-2（卡片） < surface-3（内嵌/浮层）`，配合阴影表达抬升。

---

## 3. 字体与字号

字体栈（沿用现有，含中文回退）：

```
'Segoe UI', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif
```

| Token | 值 / 字号 / 行高 | 用途 |
|---|---|---|
| `--font-family-base` | 如上 | 全站 |
| `--text-xs` | 11px / 1.5 | 徽标、辅助元信息 |
| `--text-sm` | 12px / 1.5 | 表单标签、卡片次要文本 |
| `--text-base` | 13px / 1.6 | 正文、控件（桌面密度） |
| `--text-md` | 14px / 1.6 | 导航、Tab |
| `--text-lg` | 16px / 1.5 | 区块 / 抽屉标题 |
| `--text-xl` | 20px / 1.4 | 页面标题 |
| `--text-2xl` | 24px / 1.35 | 空状态 / 强调标题 |
| `--font-medium` | 500 | — |
| `--font-semibold` | 600 | 当前项、标题 |

> 桌面工具采用偏紧凑密度，正文基准 13–14px；长文本（Prompt / 备注）行高放宽到 1.6。

---

## 4. 间距、圆角、阴影、层级、动效

### 4.1 间距（4px 基准，扩展现有 `--space-*`）

| Token | 值 |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |

控件内边距、栅格间隙统一取上述 Token，不出现任意像素值。

### 4.2 圆角

| Token | 值 | 用途 |
|---|---|---|
| `--radius-sm` | 6px | 小元素、缩略图、输入内嵌 |
| `--radius-md` | 8px | 控件（按钮 / 输入 / 徽标） |
| `--radius-lg` | 12px | 卡片 / 面板 / 抽屉内区块 |
| `--radius-xl` | 16px | 大面板、模态 |
| `--radius-pill` | 999px | 胶囊徽标、开关 |

（保留现有 `--radius` 作为 `--radius-lg` 的别名，避免一次性破坏旧引用。）

### 4.3 阴影 / 抬升

| Token | 用途 |
|---|---|
| `--shadow-sm` | 卡片静态（极轻） |
| `--shadow` | 顶栏 / 常规抬升（沿用现有） |
| `--shadow-md` | 抽屉、下拉、弹出 |
| `--shadow-lg` | 模态 |

### 4.4 z-index 层级

| Token | 值 |
|---|---|
| `--z-nav` | 100 |
| `--z-dropdown` | 200 |
| `--z-drawer` | 400 |
| `--z-modal` | 500 |
| `--z-toast` | 600 |
| `--z-tooltip` | 700 |

### 4.5 动效

| Token | 值 |
|---|---|
| `--dur-fast` | 0.12s |
| `--dur-base` | 0.2s |
| `--dur-slow` | 0.3s |
| `--ease-out` | `cubic-bezier(.2,.7,.3,1)` |
| `--ease-in-out` | `ease-in-out` |

- 动效仅用于解释状态 / 空间关系（淡入、位移、进度、展开）；
- 尊重 `prefers-reduced-motion`：降级为瞬时或仅透明度变化。

### 4.6 焦点

| Token | 值 |
|---|---|
| `--focus-ring` | `0 0 0 2px var(--bg), 0 0 0 4px var(--accent)` |

所有可聚焦元素在 `:focus-visible` 下显示统一焦点环，不依赖浏览器默认描边被背景吞没。

---

## 5. 布局基元（Layout Primitives）

| 基元 | 职责 |
|---|---|
| `PageContainer` | 页面外层，控制最大宽度与内边距；提供 `width: wide/normal` |
| `PageHeader` | 页面标题 + 描述 + 右侧操作区 |
| `Section` / `Panel` | 内容区块（标题 + 主体 + 可选页脚） |
| `Stack`（H/V） | 基于间距 Token 的纵向 / 横向排列 |
| `Grid` | auto-fill 自适应网格（图库 / 素材 / 卡片） |
| `Divider` | 区块分隔 |
| `ScrollArea` | 限定高度滚动区（抽屉、队列、缩略图条） |

---

## 6. 组件规格（UI-0 交付清单）

每个组件统一：**变体（variant）+ 尺寸（size）+ 状态（state）**，并具备 `className` 透传与必要的 `aria`。

### 6.1 Button
- Variants：`primary`（主操作，accent 实心）、`secondary`（默认，surface-3 + border）、`ghost`（无背景）、`danger`（危险，danger 描边 / 实心按场景）。
- Sizes：`xs / sm / md / lg`。
- States：default / hover / active / focus-visible / disabled / loading（显示 spinner，禁用并防重复提交）。
- 规则：一个区块一个 primary；危险动作（删除 / 拒绝 / 取消任务）用 danger 并需确认。

### 6.2 Input / 6.3 Textarea
- 外观：surface-3 背景 + border，focus 时 border→accent + 焦点环。
- 支持：`invalid`（danger 边框 + 错误文案）、`disabled`、前缀 / 后缀槽位、字符计数（可选）。
- Textarea：`resize: vertical`，最小高度，等宽字体可选（Prompt 长文本仍用默认字体保证中文可读）。

### 6.4 Select
- 原生 `<select>` 封装（保证键盘 / 一致性），右侧统一箭头；支持占位、disabled、option 分组。
- 复杂选择（素材 / 图片）使用 `Drawer + Grid`，不用自制下拉。

### 6.5 Slider
- 轨道 + 填充 + 手柄，键盘可调（方向键），同步显示当前值；可与数字 Input 组合（尺寸 / 数量 / 参数）。

### 6.6 Switch
- 开关（pill + 滑块），带 `role="switch"` 与 `aria-checked`；布尔设置使用，配合文字标签。

### 6.7 Checkbox
- 多选（模块启用、筛选）；支持 `indeterminate`（半选）。

### 6.8 RadioGroup / SegmentedControl
- Radio：单选项（主题、生成模式）；
- Segmented：紧凑分段切换（结构化 / 完整、普通 / 插队、网格 / 瀑布），`role="radiogroup"`，当前项非颜色可辨。

### 6.9 Tabs
- 顶部下划线 Tab，当前项 accent 下划线 + 半粗体；支持键盘左右切换、`aria-selected`。

### 6.10 Badge
- 胶囊小标签：中性 / accent / 状态色；用于模式、版本、来源。

### 6.11 StatusBadge / StatusDot
- **Job / 审查 / 收藏状态**：文字 + 状态色 + 可选图标；颜色不作为唯一信息（始终带文字，如"运行中 / 已保留 / 已拒绝"）。
- StatusDot：Engine 在线 / 检查中 / 离线，带脉冲（在线）与文字。

### 6.12 Drawer
- 右侧滑入（宽 480 / 640 两档），遮罩 + ESC 关闭 + 焦点陷阱；标题 + 关闭按钮 + 滚动主体。
- 用于详情（图片 / 素材 / 配方 / 历史）与选择器（素材 / 图片）。

### 6.13 Modal
- 居中对话框（确认、编辑器）；遮罩 + ESC + 焦点陷阱；标题 / 主体 / 操作（主操作右置）。
- 确认型 Modal 用于不可逆动作（拒绝、删除、归档）。

### 6.14 Toast
- 右上角短时反馈（成功 / 错误 / 信息），自动消失 + 手动关闭；错误可附带重试。
- 不承载关键决策，仅反馈结果。

### 6.15 Tooltip
- 悬浮 / 聚焦显示的简短说明，用于图标按钮与被截断文本；不承载唯一信息，键盘聚焦也可触发。

### 6.16 状态集合组件
- `EmptyState`：图标 / 徽标 + 标题 + 描述 + 主动作；
- `ErrorState`：错误标题 + 详情（可折叠）+ 重试按钮；
- `Skeleton`：文本 / 卡片 / 图片占位骨架，脉冲动画，结构与真实内容一致；
- `ProgressBar`：确定进度（0–1，百分比），accent 填充，`aria-valuenow`；
- `Spinner`：不确定进度（加载中）。

---

## 7. 图标

- 使用一套轻量内联 SVG 图标（stroke 线性风格，16/20px），不引入重型图标库；
- 图标按钮必须带 `aria-label` 与 Tooltip；
- 状态图标与状态色成对，但始终有文字或 `aria-label` 兜底。

---

## 8. 可访问性检查单

- [ ] 对比度：正文 ≥ 4.5:1，大文本 / 控件 ≥ 3:1（双主题分别核对）；
- [ ] 所有交互元素可 Tab 到达，`:focus-visible` 焦点环清晰；
- [ ] 浮层（Drawer/Modal/Dropdown）打开时焦点进入、ESC 关闭、关闭后焦点回到触发元素；
- [ ] 状态不仅靠颜色（图标 / 文字双编码）；
- [ ] 图标按钮有 `aria-label`；表单控件有 `label`（或 `aria-label`）；
- [ ] 进度条 / 开关 / Tab 使用正确 ARIA；
- [ ] 尊重 `prefers-reduced-motion`；
- [ ] 长文本可换行（`overflow-wrap:anywhere` 兜底超长串），不产生横向滚动。

---

## 9. 深色 / 浅色主题落地

- Token 全部在 `:root`（浅色默认）与 `[data-theme='dark']` 两处定义；
- 组件样式只引用语义 Token，禁止组件内写死十六进制 / rgba（遮罩等已 Token 化的除外）；
- 切换无闪烁：`ThemeProvider` 在首次绘制前按 localStorage / 系统设置 `data-theme`。
