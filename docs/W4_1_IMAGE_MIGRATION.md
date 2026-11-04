# W4.1 — 历史图片资产迁移报告

> 执行日期：2026-11-04 · 方式：复制 + SHA256 校验 + 批量数据库事务
> 工具：`scripts/migrate_assets_w41.py` · 服务状态：Studio / ComfyUI / Mobile Bridge 全部停止
> 迁移前快照：`D:\NSFW-Studio-Data\backups\studio-20261104-125925.db`

---

## 1. 迁移目标结构

```text
DataRoot/
├── assets/images/YYYY/MM/<image_id>/<kind>.<ext>
├── cache/thumbnails/<image_id>/thumbnail.webp
├── cache/previews/<image_id>/preview.webp
├── images/originals|upscaled|processed|thumbnails|previews（旧结构，保留只读）
```

---

## 2. 迁移结果

| 项 | 结果 |
|---|---:|
| 计划迁移图片 | 7,733 |
| 计划迁移变体 | 10,613 |
| 实际复制文件 | 17,190 |
| 已存在且 Hash 一致（跳过复制） | 156 |
| 缺失源文件 | 0 |
| 复制/校验错误 | 0 |
| 迁移后 `images` | 7,733（不变） |
| 迁移后 `image_variants` | 10,613（不变） |

### 2.1 完整性验证（`temp/w41_migration_verify.json`）

| 指标 | 结果 |
|---|---|
| `images` 在新资产根下 | 7,733 / 7,733 |
| 旧路径残留 | 0 |
| 图片文件缺失 | 0 |
| 图片 SHA256 不一致 | 0 |
| 无 SHA256 的图片 | 0 |
| 变体文件缺失 | 0 |
| `assets/images` 孤立文件 | 0 |
| 父子关系 | 32 条，迁移前后一致 |
| Prompt | 294 / 294 |
| Job / JobItem / JobStage | 946 / 6,720 / 954（不变） |
| `mobile_image_events` | 8,006 行；`max(seq)=8006`（不变） |

### 2.2 迁移前后计数对比

```json
{
  "before": {"images":7733,"variants":10613,"prompts":294,"prompt_versions":294,
             "jobs":946,"job_items":6720,"job_stages":954,"parents":32,
             "events":8006,"max_seq":8006},
  "after":  {"images":7733,"variants":10613,"prompts":294,"prompt_versions":294,
             "jobs":946,"job_items":6720,"job_stages":954,"parents":32,
             "events":8006,"max_seq":8006}
}
```

---

## 3. 执行方式

1. 停止 Studio / ComfyUI / Mobile Bridge（端口 8000 / 8188 / 8877 全部释放）；
2. SQLite backup API 生成迁移前快照；
3. `migrate_assets_w41.py --dry-run` → 7,733 图片 + 10,613 变体，0 缺失；
4. 数据库副本演练 100 张：路径更新、Hash 校验、计数不变；
5. 正式执行：
   - 逐文件读取源 → 同时写入临时文件 → 写入流 Hash → 目标文件 Hash 复核；
   - 源 Hash 与数据库 `sha256` 不一致立即中止；
   - 每 200 文件一个 `BEGIN IMMEDIATE` 事务更新 `images.file_path` / `image_variants.path`；
6. 校验脚本对全部文件重新计算 SHA256。

**未使用**：跨盘移动、直接删除旧文件、覆盖原图、修改 Job/Prompt 内容。

---

## 4. 旧文件处理

- 旧 `images/originals|upscaled|processed|thumbnails|previews` 全部保留，当前未删除、未移动；
- 迁移验收通过后，可按 `W4_1_MIGRATION_RISK.md` 阶段 E 把旧目录移入
  `DataRoot/archive/images-legacy-20261104/`（移动而非删除）；本报告不声称该归档已完成；
- 全量 DataRoot 备份：`D:\NSFW-Studio-Data-Backup-20261104`（20,992 文件 / 14.487 GB）。

---

## 5. 回滚

1. 停止服务；
2. 用 `studio-20261104-125925.db` 覆盖 `database/studio.db`，清理 `-wal/-shm`；
3. 数据库恢复为旧 `images/...` 路径，旧文件仍在原位；
4. 新 `assets/images` 与 `cache` 可保留或移入 temp，不影响旧数据。

---

## 6. 已知限制

- 迁移为单进程机械盘复制，耗时较长；未并行化（避免 IO 争抢与 Hash 顺序不一致）。
- 旧目录仍占用约 14 GB；归档动作在正式验收后单独执行。
- 本报告不包含 G3/G4 出图结果，见 `W4_1_REPORT.md`。
