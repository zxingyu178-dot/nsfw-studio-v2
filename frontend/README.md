# frontend

NSFW Studio V2 前端壳：React 18 + TypeScript + Vite 5。

## 运行

```bash
# 项目根目录执行（自动使用 AIHome 统一 Node 环境）
scripts\dev_frontend.bat

# 或手动（Node ≥ 18）
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5173>。

## 结构

| 目录 | 职责 |
| --- | --- |
| `src/app/` | 应用根组件与全局样式 |
| `src/pages/` | 页面：Generate / Gallery / Prompt / Assets / Settings（Phase 0 均为空状态壳） |
| `src/components/` | TopNav、EngineStatus（后端健康指示）、ThemeToggle、EmptyState |
| `src/layouts/` | MainLayout（顶栏 + 内容区） |
| `src/themes/` | ThemeProvider + tokens.css（深/浅主题变量，`data-theme` 驱动） |
| `src/api/` | 后端 HTTP 封装（仅封装，不做业务） |
| `src/stores/` | 极简 store（themeStore，localStorage 持久化） |
| `src/utils/` | 通用工具 |

## 说明

- 主题：默认深色，可切换浅色；选择持久化在 `localStorage`（键 `nsfw-studio-theme`）。
- Engine 指示：轮询 `/api/v1/health`（15s）；开发期由 Vite 代理到 `http://127.0.0.1:8000`，可用环境变量 `NSFW_STUDIO_API_URL` 覆盖（仅后端地址，不涉及生成引擎）。
- 构建：`npm run build`（tsc 类型检查 + vite 构建）。
