# Prompt Preview Contract（Prompt 封面预览契约）

> 适用：NSFW Studio V2「日用化」阶段。本文档冻结 **Prompt 封面预览图（preview image）** 的数据模型、
> API、引用检查与前端行为。后端见 `backend/app/models/prompt.py`、`backend/app/services/prompt_service.py`、
> `backend/app/api/v1/prompts.py`、`backend/app/services/image_reference_service.py`；
> 前端见 `frontend/src/pages/Prompt/PromptTab.tsx`。

---

## 1. 核心语义：封面是 Prompt 的“元数据”，不是新版本

- 每个 Prompt 可有**一张封面预览图**，仅用于在 Prompt 列表卡片上直观识别该 Prompt。
- **设置 / 更换 / 移除封面都只改 `Prompt.preview_image_id`，绝不创建 `PromptVersion`。**
  - PromptVersion 是不可变的创作版本历史；封面属于展示元数据，与版本无关。
- 封面图本身仍是 Image 资产（位于图库 / DataRoot），Prompt 通过 `preview_image_id` 引用它。

---

## 2. 数据模型与迁移

- `prompts` 表新增可空列 **`preview_image_id`**（字符串，逻辑外键指向 `images.id`）。
- 由本轮**唯一**新增迁移 **`0014_prompt_preview_image`** 引入（自研极简迁移框架，
  见 `backend/app/database/migrations.py`，按 migration_id 升序追加在 0013 之后；非 Alembic）。
- 不新增其他后端字段，不改变 Recipe / Job schema。

---

## 3. HTTP API

挂在 `/api/v1` 下：

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| PUT | `/api/v1/prompts/{prompt_id}/preview-image` | `{"image_id": "<image id>"}`（`PreviewImageRequest`） | 设置 / 更换封面 |
| DELETE | `/api/v1/prompts/{prompt_id}/preview-image` | — | 移除封面（置空） |

- `PreviewImageRequest`：`image_id: str`（必填）。
- 服务层：
  - `set_preview_image(session, prompt_id, image_id)`：校验 Prompt 与 Image 均存在 →
    赋值 `prompt.preview_image_id` → commit；**不构造 / 插入 PromptVersion**。
  - `clear_preview_image(session, prompt_id)`：`preview_image_id = None` → commit；不建版本。
- 响应：返回更新后的 `PromptResponse`（含 `preview_image_id` 与 `current_version`）。
- Prompt 或图片不存在时按现有 404 / 校验错误信封返回。

---

## 4. 图片引用检查（删除图片前识别封面引用，不留悬空 ID）

- `image_reference_service.count_references(session, image_id)` 新增引用分类
  **`prompt_preview_ids`**：
  ```text
  select Prompt.id where Prompt.preview_image_id == image_id
  ```
- 结果并入：
  - `references["prompt_preview_ids"]`；
  - `total`（计入这些 Prompt 引用数）。
- 效果：
  - 设置某图为封面后，该图引用 `total + 1` 且 references 含对应 Prompt；
  - 移除封面 / 更换为其他图后，引用回落、不再含该 Prompt；
  - **删除图片前能识别 prompt_preview 引用**，从而阻止误删或提示用户，避免 `preview_image_id` 指向已删图片（悬空 ID）。

---

## 5. 前端契约

### 5.1 类型与 API

- `PromptDTO` 新增 `preview_image_id: string | null`。
- `promptApi.setPreviewImage(id, imageId)` → PUT；`promptApi.clearPreviewImage(id)` → DELETE。

### 5.2 Prompt 卡片（列表）

- 有封面：渲染 `img.pp-card__cover`，**`loading="lazy"`**（懒加载，避免一次拉全库原图）。
- 无封面：渲染占位 `div.pp-card__cover--empty`（“无封面”）。
- 卡片正文显示标题与摘要（`pp-card__excerpt`，UI 摘要）。
- 卡片底部含一键**复制**按钮（`pp-card__copy`）：
  - 复制的是 **`current_version.positive_prompt` 全文（后端 `compose_structured` 合成后的完整文本）**，
    **不是** UI 摘要；
  - 点击时 `stopPropagation() / preventDefault()`，**不得触发打开编辑 Drawer**。
- 点击卡片其他区域 → 打开编辑 Drawer。

### 5.3 编辑 Drawer 的“封面”区块

- 显示当前封面（或空态），按钮：
  - 无封面：**设置封面**；有封面：**更换封面**；以及 **移除封面**。
- 设置 / 更换封面**复用现有 `ImagePickerDrawer`**（不新写选择器），标题“选择封面图片”；
  选中图片后调 `setPreviewImage`，随后刷新详情；移除封面调 `clearPreviewImage`。
- 封面操作不产生新版本。

---

## 6. 测试覆盖

- 后端 `tests/backend/test_prompt_preview_image.py`：
  - 设置封面：`preview_image_id` 更新、引用 total +1 且含该 Prompt；
  - 更换 / 清除封面：引用回落、无悬空；
  - **设置 / 更换 / 清除后 `PromptVersion` 数量恒定**（断言不建版本）；
  - 删除图片前引用检查能识别 prompt_preview。
- 两个既有迁移 golden-list 测试（`test_migration_upgrade.py`、`test_phase4_backfill.py`）
  的期望迁移列表追加 `0014`（仅追加，不削弱断言）。
- 前端 `pages/Prompt/PromptTab.cover.test.tsx`：卡片封面 lazy、设置封面走 ImagePickerDrawer、
  一键复制内容为后端合成 positive 且不打开 Drawer、移除封面。

---

## 7. 边界与红线

- 不把图片、db、DataRoot 提交 Git；封面仅存 ID 引用。
- 不在前端预载全库原图（卡片 lazy、Lightbox 只载当前张）。
- 封面与 PromptVersion 严格解耦；本轮不做完整 Reference UI。
