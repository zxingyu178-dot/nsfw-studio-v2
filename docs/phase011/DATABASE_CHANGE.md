# Phase 0.11 数据库变更说明（DATABASE_CHANGE）

> 阶段：NSFW Studio V2 — Phase 0.11 AI Asset Management System
> 基线：`feature/daily-use-ux-runtime`（最新迁移 `0014_prompt_preview_image`）
> 本阶段新增迁移：**0015 / 0016**，单一事实源 `backend/app/database/migrations.py`，沿用现有升级 / 恢复机制。

## 总览

| 迁移 | 版本 | 类型 | 说明 |
|---|---|---|---|
| `0015_image_variant_system` | 1.1.0 | 建表 + 索引 | 新增 `image_variants`，同一 Image 的 original/thumbnail/未来 4K 等都作为 variant，**不污染 images 表** |
| `0016_image_review_status` | 1.1.0 | 加列 + 索引 + 回填 | `images` 增 `status / reviewed_at / review_note`，新审核体系，并从旧 `review_status` 回填 |

---

## 0015_image_variant_system

### 设计原则
- **变体不写回 Image 表**：`images` 表保持代表"一张图片"的逻辑主体；original/thumbnail/preview/upscaled/processed
  等所有派生文件统一作为该 Image 的 variant 记录在 `image_variants`。
- 第一版只落地 `thumbnail`；`preview / upscaled / processed` 为预留类型（CHECK 已放行，暂不生成）。

### 表结构 `image_variants`

| 列 | 类型 | 约束 | 含义 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 变体 ID（前缀 `iv_`） |
| `image_id` | TEXT | NOT NULL, REFERENCES images(id) | 所属 Image |
| `variant_type` | TEXT | NOT NULL, CHECK ∈ thumbnail/preview/upscaled/processed | 变体类型 |
| `path` | TEXT | NOT NULL | 相对 DataRoot 的存储路径 |
| `width` | INTEGER | 可空 | 变体像素宽 |
| `height` | INTEGER | 可空 | 变体像素高 |
| `format` | TEXT | 可空 | 文件格式（如 webp/png） |
| `created_at` | TEXT | NOT NULL | 创建时间 ISO |

### 索引
- `idx_image_variants_image`：普通索引，`image_id`（按图查变体）。
- `uq_image_variants_thumbnail`：**部分唯一索引**，`UNIQUE(image_id) WHERE variant_type='thumbnail'`
  —— 每张 Image 至多一个 thumbnail；其它类型允许多个。

### 存储布局
- 新增目录 `images/thumbnails`（与 `originals / processed / temp / upscaled` 平级），
  已在 `backend/app/core/config.py` DEFAULT_LAYOUT 与 `configs/storage.yaml` 登记。
- 缩略图规格：**512px、WebP、quality 80**（长边缩到 512，保持宽高比）。

---

## 0016_image_review_status

### 新增列（`images`）

| 列 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| `status` | TEXT | NOT NULL DEFAULT 'NEW'，CHECK ∈ NEW/KEEP/FAVORITE/REJECT/ARCHIVED | 审核状态 |
| `reviewed_at` | TEXT | 可空 | 首次审核时间（除 NEW 外置值） |
| `review_note` | TEXT | NOT NULL DEFAULT '' | 审核备注 |

### 索引
- `idx_images_new_status`：`status`，支撑审核筛选与统计。

### 状态语义

| 状态 | 含义 |
|---|---|
| `NEW` | 默认，未审核 |
| `KEEP` | 普通保留 |
| `FAVORITE` | 精品，用于素材 / 封面 / Reference（同时同步旧 `favorite=1`） |
| `REJECT` | 淘汰，**不立即删除**，进入两阶段废片清理 |
| `ARCHIVED` | 长期保存 |

### 旧数据回填（关键，避免语义丢失）
- `review_status='KEPT'` → `status='KEEP'`
- `review_status='REJECTED'` → `status='REJECT'`
- 其余（UNREVIEWED / 空）→ 保持默认 `NEW`
- **旧列 `review_status` 保留不删**：应用层在写新 `status` 时双写旧列（NEW→UNREVIEWED、
  KEEP/FAVORITE/ARCHIVED→KEPT、REJECT→REJECTED），保证按旧列聚合的 Job 统计口径一致。

---

## 回滚 / 恢复
- 迁移机制沿用 `migration` 记录表与现有失败恢复：单迁移失败记录 `failed`，修复后重试，
  重试前清除该迁移历史记录避免主键冲突。
- 回滚为手动 DROP（SQLite 不支持事务内 DROP COLUMN 的自动 reverse）：
  - 0015：`DROP INDEX uq_image_variants_thumbnail; DROP INDEX idx_image_variants_image; DROP TABLE image_variants;`
  - 0016：`DROP INDEX idx_images_new_status;` 并重建 `images`（SQLite 删列需重建表）；
    因旧列保留，0016 回滚后旧审核语义仍在。
- 升级与回填正确性由测试覆盖：`test_migration_upgrade`、`test_phase4_backfill`（golden 列表已追加两条），
  并以"先只升到 0014 → 插旧状态图 → 再升 0015/0016"的脚本验证回填。

## 受影响测试
- `tests/backend/test_migration_upgrade.py`、`tests/backend/test_phase4_backfill.py`：golden 迁移 id 列表追加 0015/0016。
- `tests/backend/test_data_dirs.py`：EXPECTED_DIRS 追加 `images/thumbnails`。
