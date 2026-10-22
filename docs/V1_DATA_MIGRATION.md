> **2026-10-22 更新**：迁移已执行并核对完成（98 提示词 + 3 人脸，created=101，备份与映射文件在
> DataRoot/backups）。按用户要求，V1 归档目录 `archive/projects/nsfw-studio-v1` 已**删除**；
> 本文中的源目录路径仅作为历史记录保留，重跑迁移需重新提供 V1 数据。
# V1 提示词库与人脸库迁移

本工具是一次性人工迁移入口，不是服务或新的数据库迁移框架。使用项目 Python 3.11
venv，不新增依赖。只读取 V1 JSON/图片，不执行归档代码。默认 dry-run；真实 apply 由
Lead 在备份后执行。本次开发验收不执行真实 apply。

## 来源与范围

默认源目录：`D:/AIHome_2.0_L1_L2/archive/projects/nsfw-studio-v1`。

| 数据 | 数量 | 用途 |
| --- | ---: | --- |
| `runtime/promptlib.json` | 98 条 | Prompt + PromptVersion |
| `runtime/faces.json` | 3 条 | Asset + AssetVersion |
| `temp/face_input/face_1.jpg` ～ `face_3.jpg` | 3 张 | 原字节复制为资产预览图 |
| `temp/face_input/face_4.jpg` | 1 张 | 没有对应记录，不迁移 |
| `runtime/prompt_cache.json` | 已确认 3258 条 | 不读取、不迁移；后续可选 |
| `runtime/history.json` | 已确认 1 条 | 不读取、不迁移；后续可选 |

人脸映射固定为 `face_001 → face_1.jpg`、`face_002 → face_2.jpg`、
`face_003 → face_3.jpg`，不依赖 JSON 顺序。原 `filename=characters/face_00X.png`
指向的文件已丢失，保留其溯源信息，不尝试读取。真实读取发现提示词第 90–94 条没有 ID，
共 5 条；工具以源记录位置与内容 SHA-256 生成映射键，并保存 `original_id=null`，
不改写归档。其他 93 条保留原 ID 作为映射键。另经解码确认，这 3 个 `.jpg` 文件实际均为
WEBP，目标按真实格式保存为 `preview.webp`，保持原字节，不重编码。
未知 face ID、重复 ID、缺失/损坏图片
或字段类型错误均拒绝整次迁移，不静默丢弃记录。

## 字段映射与幂等策略

| V1 字段 | V2 字段 / 处理 |
| --- | --- |
| prompt `id` | 新 `prm_<uuid4>`；旧 ID 写入映射与迁移标记 |
| prompt `name` | Prompt.name 原文，超过 255 字符截断；完整原名保留 |
| `positive` / `negative` | PromptVersion.positive_prompt / negative_prompt，保留空白与换行 |
| 提示词版本 | `prmv_<uuid4>`、version_no=1、mode=full |
| 提示词迁移标记 | PromptVersion.structured_json 的 `_v1_migration`，包含 source、source_id、original_name |
| face `id` | 新 `ast_<uuid4>`；旧 ID 写入映射与 notes |
| face `name` / `tags` | Asset.name（上限 255）、AssetVersion.tags_json（原数组） |
| 人脸版本 | `astv_<uuid4>`、version_no=1、prompt_text 为空 |
| face 原始元数据 | AssetVersion.notes 的 `_v1_migration.original`，含原 created_at、source、filename 等 |
| 新对象时间 | 项目 `utc_now_iso()` 生成 UTC ISO 8601；原 Unix 时间仅作溯源保留 |
| 源图 | `assets/face/<asset_id>/v0001/preview.<真实格式>`，原字节、相对路径、SHA-256 写入映射 |

主对象的 `current_version_id` 在 INSERT 时直接设置，不通过 UPDATE 回填。
预览图本身即资产源图副本，无重编码或有损缩略；UI 可正常作为预览使用。
本次不新建 Image 或 AssetReferenceImage；预览图不等于生成工作流中的正式 face_reference
输入。若后续需要参考图生成，应通过现有图库导入及参考图绑定流程单独处理。

Prompt 查重必须同时满足：同 V2 name、同 positive、同 negative，且任一历史版本有
`_v1_migration.source=nsfw-studio-v1` 标记。比仅比较 positive 更保守，防止不同负向词被合并。
未标记的同名同内容用户数据不会被误认作迁移记录。迁移后仅增加版本而保留原名，仍可识别；
若用户改名、清除标记或改变原始内容，可能视为新记录，执行前须查看计划。

Asset 按 `type=face + 同 name + 当前版本同 tag 集合` 查重，tag 顺序和重复项不影响集合。
按任务约定，即使同键既有资产的预览图不同，也复用该资产，不覆盖图片；Lead 须核对映射。
归档对象同样参与查重，不自动恢复。源文件内相同查重键也只创建一次。
重复 apply 输出 `created=0 skipped=101`（未被其他操作改变的完整 98+3 数据集）。
固定的 3 类未迁移项另列为 `omitted`，不混入幂等 `skipped` 数量。

## 实现与安全边界

实施顺序：临时 fixture 测试 → 只读源校验与计划 → 单事务 apply →
真实 dry-run → 测试、diff、编码验收。只交付脚本、专用测试、本文件。

- 参数：`--source`、`--data-root`、互斥的 `--dry-run / --apply`、`--force`。
- DataRoot 优先级：显式参数 > `NSFW_STUDIO_DATA_ROOT` >
  项目 `configs/config.local.yaml` 顶层 `data_root` > `D:/NSFW-Studio-Data`。
  最终回退按本次用户任务指定；不改变项目通用配置默认值。
- 目标为 `DataRoot/database/studio.db`。必须已存在；工具不建库、不运行 schema migration。
- dry-run 使用 SQLite `mode=ro` 和 `query_only`，不写业务数据、资产或迁移映射。
  SQLite WAL 只读连接仍可能创建空 `-wal` / `-shm` 辅助文件并维护共享内存读锁；
  这不是业务写入。不能用 `immutable=1` 忽略现存 WAL，否则计划会漏读未 checkpoint 数据。
- apply 要求 `backups/studio-*.db` 为非空文件且 mtime 位于过去一小时，未来时间不接受。
  同时拒绝当前数据库的链接/硬链接，检查 SQLite quick_check、foreign_key_check，
  以及四张目标表和 migration 表的结构一致性，拒绝文本伪备份、损坏库和异构库。
  同结构的另一套数据库仍可能通过，门禁不能证明备份来源；必须使用官方 `backup_db.py`
  为明确的同一 DataRoot 生成，不替代备份恢复演练。
  `--force` 只绕过该门禁，始终输出危险警告，不隐含 apply，不绕过其他校验。
- apply 用 `BEGIN IMMEDIATE` 先取写锁再查重，两次迁移不会同时插入重复记录；
  与其他写入竞争超时则失败，由 Lead 择空闲窗口重试。
- SQL 授权器只允许读取及四张目标表的直接 INSERT；拒绝 UPDATE、DELETE、
  DDL 及触发器额外写入。数据表的版本与既有记录均不更新。
- 所有源图先完整解码校验，再使用相同内存字节落盘；路径必须在所属根目录内。
  目标文件使用 `xb` 独占创建并 fsync，既有文件永不覆盖。
- 提交前先独占创建并刷盘 `backups/v1-migration-map-<UTC微秒时间>.json`，
  包含 prompt/asset ID 映射、版本 ID、原名、截断名、新文件路径与哈希、跳过项及备份路径。
  映射不包含正负提示词正文。
- 映射是**预提交意向记录**，固定标注 `prepared`，其存在不能作为成功证明。
  数据库提交成功后打印成功输出；遇到断电/终端输出失败，必须按映射 ID 查库判定。
- 任意文件写入或 SQL 错误发生在提交前，回滚全部数据库 INSERT。
  已写入的意向映射/图片保留，不自动物理删除；因此失败可留下可追踪的孤立文件。

## 执行步骤（Lead）

在项目根目录 PowerShell 执行。先选择空闲维护窗口，避免备份后产生额外业务写入；
如需停止服务，只能使用已有 ControlHub 官方入口，此脚本不管理服务生命周期。

```powershell
# 用环境变量让备份与迁移指向同一个目标；只改变当前 shell。
$env:NSFW_STUDIO_DATA_ROOT = "D:/NSFW-Studio-Data"
.venv\Scripts\python scripts\backup_db.py
if ($LASTEXITCODE -ne 0) { throw "备份失败，停止迁移" }

.venv\Scripts\python scripts\migrate_v1_legacy.py --dry-run
if ($LASTEXITCODE -ne 0) { throw "计划校验失败，停止迁移" }

# 核对 98 prompts / 3 faces、待新增/跳过数量及 DataRoot 后，由 Lead 执行：
.venv\Scripts\python scripts\migrate_v1_legacy.py --apply
if ($LASTEXITCODE -ne 0) { throw "迁移未确认成功，请按映射核查数据库" }

.venv\Scripts\python scripts\migrate_v1_legacy.py --dry-run
```

核查事项：

1. 保存 stdout 和映射。最后一次 dry-run 应显示 `待新增=0 skipped=101`。
2. 按映射核对 ID / current_version_id / version_no=1、原文、标签及相对预览路径；
   三张图的 SHA-256 应与映射一致。
3. 未有并发变更且首次计划全部新增时，原有 1 prompt / 1 asset 应变为 99 / 4；
   实际以迁移前只读计数和新增数量为准。1094 张历史生成图不在本次迁移范围。
4. 在 V2 UI 检查提示词库、人脸库和预览展示；本次代码验收不代替真实 apply/UI 验收。

## 回滚

提交前失败由 SQLite 自动回滚；如果进程中断，重新打开数据库后核对意向映射对应的 ID。
不要把意向映射中的 `skip` 记录视为本次新增，更不要删除其对应资产。

提交后需由 Lead 安排维护窗口、通过官方生命周期入口停止所有目标数据库写入者，
先使用 SQLite backup API 为当前状态另存一份安全快照（新文件名，不覆盖旧备份）。
随后使用 SQLite backup API 将映射所指的迁移前备份恢复到目标数据库，
核对完整性与迁移前计数后再启动。**不得直接复制正在写入的 DB，也不得只替换主 DB
而忽略 WAL。**恢复前先在临时 DataRoot 演练；本工具不提供自动恢复命令。

整库恢复会丢失备份之后的其他业务修改，因此必须冻结写入或先人工处理这部分差异。
本工具不使用 DELETE 做选择性回滚，也不自动移除新增资产文件；恢复后它们可能成为
孤立文件，保留映射与文件以供 Lead 后续审查，另行授权清理。V1 始终不变。

## 后续建议

`prompt_cache.json` 的 3258 条路径需要先与 V2 Image 路径/哈希核对，再设计独立回填；
不根据路径猜测或覆盖现有提示词关系。`history.json` 与 `face_4.jpg` 单独评估归属，
不要自动补造人脸身份。正式人脸参考图绑定也作为后续任务处理。

## 验收记录

测试命令：`.venv\Scripts\python -m pytest tests/backend/test_migrate_v1_legacy.py -q`。
2026-10-20 最终专项 19 项通过（退出码 0）。存在 1 条现有 Starlette/httpx 弃用警告，无新增依赖。
临时 fixture 覆盖 dry-run、apply、幂等、备份门禁、force、配置优先级、图片损坏、
事务失败、映射失败、INSERT-only 约束、缺失源 ID、扩展名与内容格式不一致，
以及临时数据库 backup API 恢复。最终测试结果见本次交付汇报；
真实 apply、生产恢复演练、真实 UI 验收均未执行。

2026-10-20 真实归档 dry-run 输出（退出码 0）：

```text
源目录：D:\AIHome_2.0_L1_L2\archive\projects\nsfw-studio-v1
DataRoot：D:\NSFW-Studio-Data
迁移计划：prompts=98 faces=3 待新增=101 skipped=0
名称截断：0（最多 255 字符，完整名称保留在映射中）
缺失提示词 ID：5（使用源记录位置＋内容哈希作为映射键）
人脸预览格式：face_001→preview.webp, face_002→preview.webp, face_003→preview.webp（按实际格式命名，原字节复制）
未迁移项：3
  - temp/face_input/face_4.jpg：没有对应的人脸记录，暂不迁移
  - runtime/prompt_cache.json：历史路径提示词缓存，后续可选
  - runtime/history.json：历史记录，后续可选
dry-run：只读检查完成；未写数据库、图片或映射文件。
```

另一次 dry-run 前后，目标数据库主文件及已有 WAL 内容的 SHA-256 对比一致。

额外执行 `.venv\Scripts\python -m pytest`：541 passed、2 failed、3 skipped，
耗时 1063.72 秒。本轮不是全绿：现有 `test_job_queue.py` 中
`test_priority_next_inserts_after_running` 等待 RUNNING 时已是 COMPLETED；
`test_queue_reorder` 返回 400，缺失 `queued`。未修改现有队列实现或测试。
全量执行期间专项用例仍在补充，最终迁移专项结果单独列出，不能视为最终版本单轮全量全绿。
上述两项队列测试单独复跑仍失败；独立只读审查已复核最终备份门禁。

本会话末次真实 dry-run 发现外部状态已变化，输出变为
`prompts=98 faces=3 待新增=0 skipped=101`，只读计数为 99 prompts / 4 assets；
出现映射 `v1-migration-map-20261020T135425300651Z.json`。
本实施会话没有执行真实 apply 或 commit/push/tag，不能把该外部迁移记作本会话执行。
上文 `待新增=101 skipped=0` 是较早时点的真实计划，二者不是同一时点的数据。

本会话测试临时目录清理请求被自动审批策略拒绝（`blocked by policy`），未绕过，
临时 fixture 数据保留，不涉及生产数据或其他 Agent 文件。
