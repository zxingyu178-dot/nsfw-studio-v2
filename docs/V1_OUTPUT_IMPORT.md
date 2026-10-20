# V1 输出图片导入：调研与交接

本次仅实现工具和隔离测试，并对真实 DataRoot 执行 dry-run。真实 `--apply` 由 Lead 决定，未执行。没有修改归档、现有迁移框架、现有测试，也没有提交、推送、打标签或新增依赖。

## 调研范围与事实

2026-10-21，在 `develop` / v0.26.0 开发目录读取：

- V1：`D:/AIHome_2.0_L1_L2/archive/projects/nsfw-studio-v1/runtime/prompt_cache.json`。
- 输出目录：`D:/AIHome_2.0_L1_L2/projects/comfyui/app/output`。
- V2：`D:/NSFW-Studio-Data/database/studio.db`，SQLite `mode=ro`，没有运行应用初始化或迁移。

3258 条缓存全部位于指定 output 下；2667 个文件仍存在，591 个缺失。缺失示例（相对于 output）：

```text
千问批量/L4半遮_08_酒店走廊/18_第16张_s181815_00001_.png
千问批量/L4半遮_08_酒店走廊/18_第15张_s181814_00001_.png
千问批量/L4半遮_08_酒店走廊/18_第14张_s181813_00001_.png
```

完整缺失清单保存在 dry-run JSON 的 `skipped` 中。不根据同名文件猜测迁移位置。

V2 有 1094 条 Image：1091 条 `source=comfyui`、3 条 `source=import`；不是全部由 V2 生成。1094 个原图文件均可读。只有 3 条有 `sha256` 和 `imported_filename`；后者仅原始文件名，不能回溯 V1 绝对路径。`images.file_path` 是 DataRoot 内的相对路径。现有 metadata 只有生成模块、阶段、provider、binding/workflow hash 和导入文件名/hash 等，没有 V1 原路径。

对 2667 个存在的 V1 文件及 V2 全部 1094 个原图计算实际文件 SHA-256（不只信任数据库哈希）：V1 有 2661 个唯一哈希，6 个额外重复文件；与 V2 相交 33 个唯一哈希，对应 33 个 V1 路径和 33 张 V2 图片。存在文件合计 4,617,305,609 字节。

**不能按路径关联。** 文件名、文件大小只能筛选候选，不能证明内容一致；本次可靠判据是原始文件字节 SHA-256 相等。重编码、PNG 元数据改变或裁剪后的视觉相似图不会被这种判据认定为相同，不能据此断言视觉上完全不重叠。591 个丢失文件无法验证内容。

3258 条的 positive 原文（不 trim、不改大小写、不改标点）去重后 **387 条**。V2 当前 99 个 Prompt 中，98 个当前版本携带 `_v1_migration` 标记，原文均唯一：

- 完全相等：69 个 cache 唯一文本，对应 69 个已迁移文本。
- 严格包含（排除完全相等，任一方向的非空子串）：0 个 cache 文本、0 对。
- 若包含关系允许相等，则为 69 对。

缓存只有时间戳和 positive。不从唯一一条 history 猜配 seed、negative、steps、cfg 等参数。创建的新 Prompt 使用空 negative，并显式标记 `negative_prompt_known=false`；复用 Prompt 仅说明 positive 相等，不声称旧图使用过该 Prompt 的 negative。

## 方案比较

| 方案 | 影响面 | 风险与建议 |
| --- | --- | --- |
| A 导入存在的 V1 图片并创建/复用 Prompt | 新增外部导入 Image、原图、缩略图和必要 Prompt；保存来源及 Prompt 引用 | 推荐。只导入唯一且尚未存在的文件；增加存储占用；不能恢复真实生成 Job/参数 |
| B 仅向已有图写 cache 元数据 | 只能针对 33 个 SHA-256 精确匹配对象讨论回写 | 不能覆盖其余 1061 张；已有生成来源不可覆盖，现有服务也没有通用 metadata 更新入口，本工具只记录匹配并跳过，不执行回写 |
| C 只导出清单 | 仅 DataRoot/backups 增加 JSON | 当前实际执行模式。零业务写入；图片和提示词尚未接入图库，适合 Lead 审查 |

重要产品边界：现有 `prompt_image_service` 通过 `Image.job_id → Job.workbench_snapshot_json.source_prompt_id` 查询提示词生成图。外部导入图没有 Job。本工具把 `prompt_id` / `version_id` 保存到 `Image.metadata_json.v1_output.prompts`，可在图库/API 元数据及清单追溯，但**不会自动显示在 Prompt 页的生成图片列表中**。完整 UI 关系需要另开服务/API/UI 任务；不能伪造 Job 来绕过架构。

## 实现计划与接口

本任务按照用户已指定的方案实施：先完成只读调研；新增 fixture 测试并验证失败；新增独立脚本；运行指定测试和真实 dry-run；检查边界并交接。工具方法 `run(source, output, root, apply=False, limit=None)` 返回与 JSON 清单一致的计划。

- 默认与 `--dry-run` 都只读库、扫描源图并写一份 `backups/v1-outputs-plan-<UTC time>.json`，不复制图片。
- `--limit N` 限制本轮新增的唯一图片数量，N 必须为正整数；不是仅扫描前 N 条，因此统计仍覆盖整个 cache。已有重复不会消耗额度。同字节的所有 cache 来源及不同 positive 都保留在同一组。
- 正文完全相等时复用未归档 Prompt 当前版本；不匹配历史版本、不模糊匹配。多个候选按 ID 稳定选择，清单记录版本 ID。已有匹配图片一律跳过，不改其 metadata。
- SHA-256 用实际原图计算；数据库登记的导入 hash 若与文件不一致则拒绝，不静默重复导入。现有文件缺失时记录 ID，已登记 hash 仍阻止重复。
- 源路径必须在指定 output 范围，符号链接解析后再次校验；源目录、输出目录、DataRoot 不能相互包含。不存在的数据库不会自动新建。
- apply 复用 `migrate_v1_legacy.recent_backup`：一小时内非空 `studio-*.db`，quick_check、外键和相关 schema 校验；扫描前、写入前各检查一次；没有 `--force`。
- 门禁与原迁移脚本一致，不能密码学证明备份由 `backup_db.py` 生成，也不能替代恢复演练。操作流程必须使用现有备份脚本。
- 业务写入只调用 `prompt_service.create_prompt`、`image_service.prepare_import_image` 和 `image_service.import_outputs_transaction`。不直接 SQL 写业务表、不改现有 service/schema，不新增常驻服务。
- 外层 `BEGIN IMMEDIATE` 串行化写入，服务 commit 限定在 SAVEPOINT 中；锁内重新检查图片与 Prompt，整轮业务事务统一提交。失败回滚业务表。
- 文件系统不具备 SQLite 事务性。工具禁止物理删除，失败/崩溃可能保留原图或临时文件；导入前持久化每图意向日志，记录分配的 Image ID 和相对文件路径。失败后由 Lead 核查，不自动清理。不承诺文件与数据库整体原子回滚。
- 逐图读取校验与复制使用同一份字节；扫描后 SHA-256 变化会拒绝。缩略图按现有服务 best-effort 生成，失败不等于原图导入失败。

## 执行步骤（仅供 Lead 后续决定）

在开发项目根目录，先审查清单：

```powershell
.venv\Scripts\python scripts/import_v1_outputs.py --dry-run --data-root D:/NSFW-Studio-Data
.venv\Scripts\python scripts/import_v1_outputs.py --dry-run --data-root D:/NSFW-Studio-Data --limit 5
```

本次不运行以下 apply。Lead 批准后，在维护窗口避免生成和其他写入：

```powershell
$env:NSFW_STUDIO_DATA_ROOT = 'D:/NSFW-Studio-Data'
.venv\Scripts\python scripts/backup_db.py
.venv\Scripts\python scripts/import_v1_outputs.py --apply --limit 5
```

先检查少量导入图、Prompt 元数据、结果清单与磁盘空间。全量导入前重新备份，再由 Lead 决定去掉 limit；整轮写锁可能暂时阻塞正在运行的 Studio 写入。不要把开发目录未发布的脚本误认为已经部署到日用实例。

清单包含本机源路径与原始提示词，按私有运行数据留在 DataRoot，不上传 Git。清单存在只证明计划写出，apply 成败查看结果文件与数据库；若提交后结果清单写出失败，应重新 dry-run 核查，而不是假设回滚。

## 验证记录

命令 `.venv\Scripts\python -m pytest tests/backend/test_import_v1_outputs.py -q`：**9 项通过，退出码 0**。现有环境有一条 Starlette/httpx 弃用警告，未新增依赖或修改既有测试。指定测试全部在临时 DataRoot 中调用 apply 方法，未对真实 DataRoot 使用 `--apply`。覆盖 dry-run 不改库/图片、创建和复用 Prompt、重复 apply、缺失/过期备份、limit、重复内容多提示词、生成图实际哈希判重、缺失/越界/非法文件、服务失败整轮业务回滚、扫描后源文件变化拒绝、清单写入失败阻止 apply。

额外启动的完整后端 pytest 已中止，没有完整结果；本次仅声称定向验证通过，不声称项目全量后端验收通过。Python AST、UTF-8 无 BOM 与 Registry JSON 检查通过。

本次独立子智能体工具两次返回会话不存在，未能获得独立子智能体审查；由主执行者复核后交 Lead 审查。工作期间出现他人对 `frontend/src/pages/Prompt/PromptTab.cover.test.tsx`、`PromptTab.tsx`、`prompt.css` 的修改，未修改或回退；后续检查这些修改已由其他执行者提交，HEAD 为 `aeec4f3`。本执行者没有执行 Git commit/push/tag。
