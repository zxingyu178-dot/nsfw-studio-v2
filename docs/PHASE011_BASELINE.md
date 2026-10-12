# Phase 0.11 基线记录（AI Asset Management System）

> 分支：`feature/phase0.11-image-asset-management`（worktree `projects/nsfw-studio-v2-phase011`）
> 基线来源：`feature/daily-use-ux-runtime` @ `f6fad0d36599e17e6d2dce4ae63845ebec3fbd97`
> （最新迁移 `0014_prompt_preview_image`）。本轮**停在本 feature 分支、不 merge main**。

## 1. Worktree / 分支

- 经 `git worktree add projects/nsfw-studio-v2-phase011 -b feature/phase0.11-image-asset-management f6fad0d` 建立。
- 不污染 Daily Use worktree 与受保护主工作树；未对任何现有工作树 stash/reset/clean/checkout。

## 2. 环境

- venv：基础解释器 `C:\Espressif\tools\python\python.exe`（3.11.15）→ worktree `.venv`。
- 已装 `backend/requirements-dev.txt`；**新增运行时依赖 Pillow（>=10）**：用于缩略图 / ImageVariant
  的解码与 WebP 编码（512px、quality 80），属图像处理依赖、非模型 / custom node；理由同 psutil 记录。
- 前端：`npm ci`（168 packages）。

## 3. 基线门禁结果（Task0，真实执行）

| 门禁 | 命令 | 结果 |
|---|---|---|
| Backend pytest | `--ignore=tests/backend/test_comfyui_integration.py` | **280 passed**（约 114s） |
| Frontend typecheck | `tsc --noEmit` | ✅ exit 0 |
| Frontend vitest | `--run` | **121 passed / 18 files** |
| Frontend build | `vite build` | ✅ exit 0 |

> 与合同给定基线值（Backend 280 / Frontend 121）一致，门禁通过，方可进入功能开发。
> 真实生图 `test_comfyui_integration.py` 按既有约定不纳入门禁（当前无 ComfyUI 运行）。

## 4. 端口 / DataRoot 策略

- 端口事实：8000 空闲、**8001 被无关 ESP-IDF uvicorn（pid 168204）占用——不动、不使用**、
  8002 空闲、8188 空闲。本阶段后端使用 **8002**。
- 性能 / 清理验收使用**独立临时 DataRoot + 脚本合成测试图**，不触碰正式 DataRoot（530 张、51MB 库）。
