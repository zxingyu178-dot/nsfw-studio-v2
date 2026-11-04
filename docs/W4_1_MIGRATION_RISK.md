# W4.1 Gate 0 — 迁移风险与回滚方案

> 范围：W4.1 全部会改动正式资产的动作（0023、Hash 规范化、图片存储迁移、SHA256 回填、
> Prompt/模型/工作流 Manifest 接入）。原则：先备份、再演练、最后正式迁移；
> 复制 + SHA256 校验，禁止未校验的跨盘移动。

---

## 1. 风险登记表

| # | 风险 | 触发条件 | 影响 | 等级 | 必须的控制措施 |
|---|---|---|---|---|---|
| R1 | CRLF/LF 双指纹 | 开发树/部署树换行不同 | 新 Job 身份不稳定；历史 Job 恢复误判 `WORKFLOW_HASH_MISMATCH` | 高 | 新增 `.gitattributes`；Hash 同时计算 raw + LF；`load_binding` 接受两种；新旧算法明确标识；历史 Job 保留 raw 值 |
| R2 | `mobile_image_events` 旧结构 | 旧库保留 `event TEXT NOT NULL` | 新事件写入失败（所有新图受影响） | 高 | 0023 以 `PRAGMA table_info` 识别；重建表、保留 `seq`/行数/索引；已修复库安全跳过；旧库与 W4.0 库副本各跑一遍 |
| R3 | 图片存储迁移 14.65 GB / 18,346 文件 | 复制到 `assets/images` + `cache` | 复制中断、Hash 不一致、DB 更新后文件缺失 | 高 | 逐文件 Copy → SHA256 → 比对；分批执行；失败即停该批；数据库先副本演练；旧目录不删除；保留全量备份 |
| R4 | 4,524 张生成图无 SHA256 | 历史上只对导入图算 Hash | 资产完整性统计不完整 | 中 | 迁移时逐张计算；写入 `images.sha256`；失败记录待处理清单，不伪造 |
| R5 | 13 个 INTERRUPTED Job | 依赖 Anima / 旧 Qwen VAE 等归档模型 | 误恢复会失败或误删模型 | 中 | 保持 Job 记录；标记不可续跑；归档模型不删除；不修改 `job_stages` |
| R6 | Prompt 字段标准差异 | 现字段 `face/pose/composition` vs 目标 `character/action/camera` | 误改历史 Prompt 文本 | 中 | 只读映射；原始 `structured_json` 不改；无版本记录者标记 `legacy_import`（当前 0 条） |
| R7 | 11 组重复缩略图 | 同内容不同 Image 的缓存 | 误删缓存导致图片无法显示 | 低 | 缓存去重只做读取复用；以 `image_id` 为缓存键；不删除现有文件 |
| R8 | 模型文件在 DataRoot 外 | `C:\ComfyUI_models`、`projects/comfyui/app/models` | 迁移误搬模型导致引擎失效 | 高 | 模型文件不进入 DataRoot；Manifest 只登记，不移动；归档目录不在搜索路径 |
| R9 | 两份注册真源 | `registry/` Manifest 与 `release_manifest.yaml` 冲突 | 前端显示与后端执行不一致 | 高 | `registry/` 管定义/版本/Hash；`release_manifest.yaml` 只管放行证据；两者字段不重复；Validator 交叉校验 |
| R10 | `mobile_image_events.seq` 丢失 | 0023 重建表时未保留 seq | 手机增量同步断档/重复 | 高 | 显式 INSERT 原 `seq`；重建后校验 `count`、`max(seq)`、`event_id` 唯一；恢复 `sqlite_sequence` |
| R11 | 导入图无 Job | 3,209 张 import 图 | 误判为“孤立”或强行关联 Prompt | 中 | 标记 `import/unlinked`；保留 metadata 关联；不伪造 Job |
| R12 | 旧 G3 证据被误当新证据 | Manifest 直接复制旧结果 | 验收失真 | 高 | 新旧 binding 证据分离；G3/G4 必须真实新跑；`default_profile_verified` 只在 G4 后置 true |
| R13 | 迁移脚本重复执行 | 中断后重跑 | 重复建资产/重复插入 | 中 | 幂等键 = `(image_id, target_path)`；先查再写；DB 唯一约束；执行日志 |
| R14 | 磁盘空间 | 全量备份 + 新资产副本 | 复制中途空间不足 | 中 | 迁移前确认 D 盘剩余 > 40 GB；旧文件在新资产验收前不删除 |
| R15 | 服务运行中迁移 | Studio/ComfyUI 仍监听 8000/8188 | 数据库锁、上传/生成写入冲突 | 高 | 迁移与 0023 前停止 Studio/ComfyUI；确认端口释放；迁移后重启并做真实 HTTP probe |
| R16 | WAL 残留 | 直接复制数据库文件 | 备份损坏 | 高 | 只用 SQLite backup API；回滚时同时清理 `-wal/-shm` |

---

## 2. 迁移阶段与门禁

### 阶段 A：只读盘点（已完成）

- 五份 Gate 0 文档 + 文件清单 CSV；
- 数据库快照、DataRoot 副本；
- 判定：无缺失、无孤立、无 Hash 不一致。

### 阶段 B：标准与 Schema（Gate 1）

- 建立 `registry/schemas/*.schema.json`、四类 Manifest、Agent 提交模板；
- 所有 Hash 同时记录 `raw` / `lf-normalized`；
- Validator 先在只读模式运行，输出 `checked / errors / warnings`。

### 阶段 C：代码与 0023（不触碰正式图片）

1. 新增 Hash 规范化模块与 `.gitattributes`；
2. 新增 0023（`mobile_image_events` 兼容重建）；
3. 在**旧结构 DB 副本**上执行迁移，验证事件行数、`seq`、写入；
4. 在 **W4.0 快照副本**上执行迁移，验证安全跳过；
5. 正式库执行 0023（停 Studio；先再备份；执行；只读校验；重启）。

### 阶段 D：图片迁移演练（数据库副本 + 文件副本）

1. Dry-run：扫描 7,733 张图 + 10,613 个变体，生成旧路径 → 新 `storage_key` 映射；
2. 目标路径：
   - 原图/派生图：`assets/images/<YYYY>/<MM>/<image_id>/<kind>.<ext>`
   - 缩略图：`cache/thumbnails/<image_id>/thumbnail.webp`
   - 预览图：`cache/previews/<image_id>/preview.webp`
3. 复制 100 张样本 + 全部 15 张 upscaled + 12 张 processed + 32 张父子图；
4. 用数据库副本更新 `images.file_path` / `image_variants.path`；
5. 副本上启动只读图库查询验证；
6. 样本验收通过后才进入全量。

### 阶段 E：全量迁移（正式库 + 正式文件）

1. 停 Studio/ComfyUI；
2. 再备份数据库（迁移前快照）；
3. 分批复制（每批 ≤ 2,000 文件），逐文件 SHA256；
4. 单事务更新数据库路径；失败整批回滚；
5. 校验：
   - 文件数、总字节、缺失数、Hash 不一致数；
   - `images` / `image_variants` 计数不变；
   - `kind/source/status` 分布不变；
   - 父子关系 32 条不变；
6. 启动 Studio，真实 HTTP 验证图库、详情、缩略图、Prompt 关联、手机同步；
7. 验收通过后，把旧 `images/originals|upscaled|processed|thumbnails|previews` 移入
   `DataRoot/archive/images-legacy-20261104/`（移动不删除）；确认新路径稳定后再决定是否清理。

### 阶段 F：Manifest 与 API 接入

1. 6 个活动模型 + 24 个归档模型 Manifest；
2. 4 个活动工作流 + 5 个历史 Binding Manifest（upscale 归档记录）；
3. `/api/v1/registry/*` 只读 API；`/modules` 继续作为工作台唯一入口；
4. Validator 拒绝：缺字段、重复 ID、未知依赖、Hash 错误、覆盖历史版本、路径穿越。

### 阶段 G：验收

- 后端全量 pytest、前端 build、G0、GitHub CI；
- 四条工作流 G3 真实出图；
- G4 冷/热启动、模型加载、采样、GPU/RAM 峰值、OOM/失败率；
- 手机端回归（独立测试 DataRoot）；
- 交付 `NSFW_Studio_W4.1_Review_Package.zip` 后停止。

---

## 3. 演练与回滚

### 3.1 数据库回滚

```text
1. 停止 Studio / ComfyUI；
2. 保留现场 studio.db、studio.db-wal、studio.db-shm 到 temp/rollback-<时间>/；
3. 用迁移前快照覆盖 database/studio.db；
4. 删除 -wal/-shm；
5. 启动并核对 counts / gallery。
```

### 3.2 图片回滚

- 迁移只复制、不删除；回滚 = 数据库恢复 + 继续使用旧 `images/originals` 路径；
- 新 `assets/images` 可保留或移入 temp，不影响旧数据；
- 旧目录只有在“新资产验收 + 备份确认”后才允许归档，禁止直接删除。

### 3.3 0023 回滚

- 迁移前快照保留；
- 0023 不删除事件行，只重建结构；回滚用快照覆盖即可；
- 已修复库安全跳过，不允许重复重建。

---

## 4. 迁移验收硬指标

| 指标 | 通过标准 |
|---|---|
| 图片文件缺失 | 0 |
| 图片 Hash 不一致 | 0（全量逐文件校验） |
| 数据库计数变化 | `images` 7,733、`image_variants` 10,613、Prompt 294/294、Job 946 不变 |
| 父子关系 | 32 条不减少、不悬空 |
| 事件表 | 行数 8,006 不减；`max(seq)` 不减；`event_id` 唯一 |
| 迁移重复执行 | 第二次执行 0 新增、0 修改 |
| 图库 API | 列表/详情/缩略图/预览 200，分页稳定 |
| Prompt 关联 | 2,736 条链接不减；254 个 Prompt 仍有图 |
| 手机同步 | 历史增量与新事件均可读；幂等回执正常 |
| G3 | 四条工作流各至少 1 张真实新图 |
| G4 | 四条工作流冷/热启动与资源峰值有实测记录 |

---

## 5. 当前阻断项（进入阶段 E 前必须解决）

1. Studio（8000）与 ComfyUI（8188）仍在运行 → 迁移/0023 前停止；
2. 全量 DataRoot 备份仍在复制 → 完成并核对文件数后才能开始迁移；
3. 0023 尚未在旧结构副本上演练；
4. 图片迁移脚本尚未实现；
5. `.gitattributes` 尚未添加，LF 规范化 Hash 尚未进入执行链。
