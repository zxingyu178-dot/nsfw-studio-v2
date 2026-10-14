# GLASS_DESIGN_SYSTEM — v0.15.0（Task 2/15：毛玻璃 Token + 性能守卫）

## 1. 设计原则

毛玻璃**统一但不滥用**：只用于浮在内容之上的容器（TopNav、WorkbenchBar、TaskDock、
HUD、Popover），图片舞台、输入槽位、控件一律不撒 blur，保证图片为视觉中心且性能可控。

## 2. Token（`themes/tokens.css`，Dark/Light 双主题）

| Token | Dark | Light |
|---|---|---|
| `--glass-bg` | `rgba(24,28,38,0.62)` | `rgba(255,255,255,0.66)` |
| `--glass-bg-strong` | `rgba(20,24,33,0.82)` | `rgba(255,255,255,0.86)` |
| `--glass-border` | `rgba(255,255,255,0.09)` | `rgba(28,35,51,0.10)` |
| `--glass-highlight` | `rgba(255,255,255,0.14)` | `rgba(255,255,255,0.55)` |
| `--glass-shadow` | `0 10px 30px rgba(0,0,0,0.42)` | `0 10px 30px rgba(28,35,51,0.16)` |
| `--glass-blur` | `16px` | `16px` |
| `--glass-saturate` | `1.35` | `1.25` |
| `--glass-fallback` | `var(--panel)` | `var(--panel)` |

## 3. 原语

- `.glass`：常规毛玻璃容器；
- `.glass--strong`：更强不透明度（弹层、HUD 等需更高可读性处）；
- 组件统一引用 class，**不允许在业务 CSS 里散落写 `backdrop-filter`**。

## 4. 回退（保证可读与性能）

- `@supports not (backdrop-filter)` → 背景改 `--glass-fallback`（较不透明 panel），关闭滤镜；
- `@media (prefers-reduced-transparency: reduce)` → 同样回退不透明；
- `@media (prefers-reduced-motion: reduce)` → 动画时长降为 0.01ms。

## 5. Canvas 恒定深色哑光

- 新增主题无关 `--canvas-stage-bg: #0b0d11` / `--canvas-stage-fg` /
  `--canvas-stage-fg-muted` / `--canvas-stage-border`；
- `.wb4-stage`、`.canvas-viewport__stage` 恒定深色、opaque、**绝不 backdrop-filter**；
- Light 主题下舞台仍深色，空态透明底、浅字。

## 6. 性能守卫（`glassPerformanceGuard.test.tsx`）

静态扫描 CSS，强制：

1. glass token 与 `.glass/.glass--strong` 存在；
2. 存在 `@supports not` 回退；
3. **Canvas（`.wb4-stage` / `.canvas-viewport__stage`）不含 backdrop-filter**，
   背景为 opaque `var(--canvas-stage-bg*)`；
4. Prompt 槽位 / 输入控件不含 backdrop-filter；
5. 全代码库 `.glass` 玻璃层数量 **≤ 8**（超出即失败，防止滥用）。

## 7. 实际落地的玻璃容器

TopNav、WorkbenchBar、TaskDock（含展开态）、ProgressHUD、Power popover / 保存下拉。
数量受守卫约束在阈值内。

## 8. 验证

- `glassPerformanceGuard.test.tsx` 4 用例全绿；
- 浏览器 Dark/Light 多分辨率截图确认玻璃质感统一、Canvas 不被模糊、文字可读；
- 不支持 backdrop-filter 的环境由 `@supports` 自动回退，不出现透明底看不见字。
