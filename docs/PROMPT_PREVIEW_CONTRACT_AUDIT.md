# Prompt Preview 图片字段合同核实（§10 审计）

- 分支：`feature/v0.14.1-fix-hardening`　HEAD：`1e5893e`（v0.14.0）
- 范围：仅核实 Prompt 封面预览图（`Prompt.preview_image_id`）的真实后端合同；本轮**不做 Prompt Card UI、不改前端展示**。
- 最高原则：逐行可追溯；没有的能力写「无」。所有路径相对仓库根。

## 结论速览

| 核实项 | 结论 | 一句话证据 |
|---|---|---|
| 1. Prompt API 稳定返回 preview（列表/详情/归档） | **成立** | `PromptResponse.preview_image_id` 由统一构造函数填充，所有读路径共用 |
| 2. preview 对应 Image 被永久删除时引用保护是否生效 | **成立** | `count_references` 统计 `prompt_preview_ids` 并入 total；物理删除在 `total>0` 时跳过 |
| 3. archived Prompt 仍能读封面 | **成立** | 读路径无 `archived` 门控，归档/恢复复用同一 response 构造 |
| 4. duplicate / copy Prompt 是否复制 preview 语义 | **无该功能** | 后端不存在任何 duplicate/copy Prompt 的端点或服务函数 |
| 5. preview 是否复用 Image 的 rendition（thumb/preview）而非原图 | **成立** | 封面只存 `image_id`，展示走 `/thumbnail`(512)/`/preview`(1536) variant 端点，非 `/content` 原图 |

**总判定：现有实现已完整，本轮不需要任何后端补丁。** 唯一的瑕疵是 `image_reference_service.py` 顶部 docstring 的引用来源清单**漏列了「Prompt 封面预览图」**，但代码本身已覆盖（见 §2）——属文档滞后，非能力缺口，按「不改代码」原则仅在此标注，不动生产文件。

---

## 1. API 是否稳定返回 preview

**成立。**

- 字段定义：`backend/app/models/prompt.py:20`
  `preview_image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)`。
- 响应 schema：`backend/app/schemas/prompt.py`
  - `class PromptResponse` 含 `preview_image_id: str | None`；
  - `prompt_response(prompt, current_version)` 显式赋值 `preview_image_id=prompt.preview_image_id`。
- 所有读路径都经同一构造函数 `prompt_response(...)`，因此 preview 在以下端点一律返回：
  - 列表：`backend/app/api/v1/prompts.py:45-56`（`list_prompts`，`archived` 默认 `False`）；
  - 详情：`prompts.py:73-76`（`get_prompt`）；
  - 创建：`prompts.py:59-70`；
  - 元数据改：`prompts.py:79-84`；
  - 设置/清除封面后回包：`prompts.py:87-98`；
  - 归档/恢复后回包：`prompts.py:134-143`。
- 设置/清除服务：`backend/app/services/prompt_service.py`
  - `set_preview_image`（`:109-115`）：属【元数据】，只写 `prompt.preview_image_id`，**不建 PromptVersion**；写前用 `image_service.get_image` 校验图片存在（不存在 → `IMAGE_NOT_FOUND`）。
  - `clear_preview_image`（`:118-123`）：置 `None`，亦不建版本。

> 说明：归档列表默认 `archived=False`；当调用方传 `archived=None`（含全部）或 `archived=True` 时，返回的 item 仍携带同一 `preview_image_id`（因为构造函数不区分归档态）。

## 2. preview 对应 Image 被永久删除时引用保护是否生效

**成立（端到端保护闭环）。**

引用保护统计：`backend/app/services/image_reference_service.py`
- `count_references(session, image_id)` 在 `:73-76` 专门统计被哪些 Prompt 用作封面：
  ```python
  # 5) Prompt 封面预览图（prompts.preview_image_id 属元数据引用，删除前需识别）
  prompt_preview_ids = sorted(session.execute(
      select(Prompt.id).where(Prompt.preview_image_id == image_id)
  ).scalars().all())
  ```
- 该分类并入返回 dict 的 `references.prompt_preview_ids`（`:85`），并**计入 `total`**（`:87-90` 的求和包含 `len(prompt_preview_ids)`）。

物理删除执行：`backend/app/services/cleanup_service.py`（这是全仓**唯一**的物理删除路径；images API 无单图 DELETE 端点）
- `execute(...)` 真删前逐张调用 `count_references`，`total>0` 即跳过并计入 protected（`:230-233`）：
  ```python
  refs = image_reference_service.count_references(session, image.id)
  if refs["total"] > 0:
      protected_count += 1
      continue
  ```
- 两阶段预览 `preview(...)` 同样把被引用图排除在「可释放字节」外（`:109-115`）。
- protected 原因映射 `_REASON_KEYS` 含 `"prompt_preview_ids": "prompt_preview"`（`:73`），因此被封面引用的图会在 `protected_items[].reasons` 里报告为 `prompt_preview`（`:83-92`）。

引用类型枚举（`count_references` 实际覆盖的全部分类键，`cleanup_service.py:72-80` / `image_reference_service.py:78-86`）：
`prompt_preview_ids`、`reference_asset_ids`、`source_asset_ids`、`recipe_ids`、`stage_item_ids`、`job_ids`、`derived_image_ids`（外加 `active_job_ids` 作为活跃 Job 原因）。

> 结论：**只要某 Image 被任一 Prompt 设为封面，它在 cleanup 阶段就永远 `total>0` → 被保护、不会被物理删除**，因此不会出现「封面悬空指向已删图」。删除路径 `_purge_image_rows`（`cleanup_service.py:138-150`）只在 total==0 时才执行，此时 prompt_preview 必然为空，逻辑自洽。
>
> 文档滞后提示：`image_reference_service.py:6-11` 的模块 docstring 列举引用来源时**未列出** Prompt 封面预览，但实现已覆盖（`73-76`）。这是注释与代码不同步，不影响运行时保护。

## 3. archived Prompt 是否仍能读封面

**成立。**

- 读详情 `get_prompt`（`prompt_service.py:24-28`）只做存在性校验，**没有任何 `archived` 门控**——归档态 Prompt 仍可读取，且其 `preview_image_id` 经 `prompt_response` 正常返回。
- 归档（`/archive`）与恢复（`/restore`）端点（`prompts.py:134-143`）调用 `set_archived` 后同样返回 `prompt_response(...)`，封面字段不丢。
- 列表传 `archived=True/None` 时，item 结构与未归档完全一致（同一 schema/构造函数）。

## 4. duplicate / copy Prompt 是否复制 preview 语义

**无该功能。**

- `backend/app/api/v1/prompts.py` 全部端点：compose / 列表 / 创建 / 详情 / 元数据改 / 设封面 / 清封面 / 版本增删查恢复 / 归档 / 恢复——**没有 duplicate 或 copy 端点**。
- 全仓 grep `duplicate|copy_prompt|def copy`（限定 `backend/app`）仅命中**图片导入去重**（`image_service.py:253+` 的 sha256 去重）与 Recipe/Asset 相关，**无任何 Prompt 复制函数**。
- 因此「duplicate/copy 是否复制 preview」在当前代码库**不存在对应行为**，如实记为「无」。未来若新增复制语义，需要明确 `preview_image_id` 是否随复制一并拷贝（建议：复制 Prompt 时连同 `preview_image_id` 一并复制，且因封面是元数据引用、被引用图受 §2 保护，不会被误删）。

## 5. preview 是否复用 Image 的 rendition（thumb/preview）而非原图

**成立。**

- 封面只存一个 `image_id`（`prompt.py:20`），后端**不为 Prompt 单独存封面文件**，也没有「prompt preview 专用 rendition」。
- 该 Image 的展示复用既有 rendition 端点（`backend/app/api/v1/images.py`）：
  - `/images/{id}/thumbnail`（`:217-230`）：512px WebP q80，缺失按需生成并落 `ImageVariant`；
  - `/images/{id}/preview`（`:231-243`）：长边 1536 WebP q85，渐进加载用；
  - `/images/{id}/content`（`:206-215`）：原图文件流——**封面默认不走这个**。
- rendition 落地表 `backend/app/models/image_variant.py`：`VARIANT_TYPES = ("thumbnail", "preview", "upscaled", "processed")`，封面缩略即 `thumbnail` variant。

> 即：Prompt 封面 = 引用某 Image + 该 Image 自己的 thumbnail/preview variant，天然复用 rendition、避免为封面重复存储大图。

---

## 是否需要后端补丁

**不需要。** 逐项核对结果为「成立 / 无该功能」，未发现「API 不返回 preview」或「引用保护缺口」。按任务边界（「若现有实现已完整则不改代码」）本轮**不新增后端逻辑、不新增 migration、不新增测试文件**。

后续若要补强（非本轮范围，仅记录建议）：
1. 同步 `image_reference_service.py:6-11` docstring，把「Prompt 封面预览图」补进引用来源清单（文档级，零运行时风险）。
2. 未来新增 Prompt duplicate/copy 时，明确并测试 `preview_image_id` 的复制语义。
