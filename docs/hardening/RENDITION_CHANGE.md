# Rendition 变更说明（Phase 0.11.1）

> 面向交接。本文说明 thumbnail / preview 两套 rendition 的规格、存储目录、并发安全、
> 主动生成与历史回填，以及 `image_variants` 的语义收紧。

## 1. 两套 rendition

| variant_type | 最长边 | WebP quality | 存储文件 | 用途 |
| --- | --- | --- | --- | --- |
| `thumbnail` | 512px | 80 | `images/thumbnails/<image_id>/thumbnail.webp` | 图库网格 |
| `preview` | 1536px（落在 1280~1600） | 85 | `images/previews/<image_id>/preview.webp` | Review Mode / Lightbox 渐进加载 |

共同约束：

- **仅下采样**：原图最长边 ≤ 目标值时保持原尺寸，绝不放大小图；
- 保持宽高比；
- **保留 alpha**（P 模式先转 RGBA，WebP 原生支持透明）；
- 原图损坏/无法解码 → `ValidationError(THUMBNAIL_FAILED)`，绝不把 PIL OSError 泄漏成 500。

## 2. 存储布局

新增登记目录 `images/previews`（与 `images/thumbnails` 并列），已在：

- `backend/app/core/config.py` 的 `DEFAULT_LAYOUT`；
- `configs/storage.yaml` 的 `storage.layout`；
- `tests/backend/test_data_dirs.py` 的 `EXPECTED_DIRS`；

登记。**这是布局扩展，不需要 DB 迁移**（`0015` 的 `image_variants.variant_type`
CHECK 已含 `preview`，模型 `VARIANT_TYPES` 同样含 preview）。

## 3. 并发安全（P1-4）

`thumbnail_service.get_or_create_variant()` 对 thumbnail 与 preview 都并发安全：

- 进程内 **per-(image_id, variant_type) 的 `threading.Lock` 字典**（带全局守卫锁）；
  获锁后做 **double-checked**（重新查 variant/文件是否已存在），命中即返回；
  任务完成后清理锁字典条目，避免锁泄漏；
- **写文件原子化**：先在目标目录写临时文件（`.tmp-<uuid>.webp`，同卷），
  flush + fsync 后用 `os.replace`（`StorageManager.atomic_move_into`）原子替换正式文件；
  临时文件在 `finally` 中清理，杜绝半写 WebP；
- **DB 竞争**：INSERT 撞唯一索引（`IntegrityError`）→ `rollback` 后**重新查询**已存在
  variant 并返回（不抛 500）；variant 行存在但文件丢失时安全重建并更新该行；
- `original` 文件缺失维持 `NotFoundError(IMAGE_FILE_MISSING)`。

## 4. 新图入库主动生成（P1-3）

`image_service.import_outputs_transaction()` 在事务 commit 成功后，
**best-effort、同步且轻量**地基于**已在内存的输出字节**（不重新读盘）生成 thumbnail：

- 失败仅 `log.warning`，**绝不向调用方抛错、绝不回滚/拖慢 Job 或 import**；
- preview **不在入库时同步生成**（留给按需/回填，避免每张大图额外开销）；
- 保证"新图进入 Gallery 时优先已有 thumbnail"。

## 5. 历史回填（P1-3）

单 worker、低并发（worker 内逐张处理，并发度 1）：

- 后台任务由 FastAPI lifespan 管理的单一 `ThumbnailBackfillRunner`（线程，
  与现有 engine_runtime 单例互不干扰）；app 关闭时干净停止；
- **不占 GPU**（纯 Pillow CPU）；Studio 重启后再次调用可重算缺失
  （状态在进程内，无持久化任务要求）；
- 同一时间只允许一个回填任务；重复调用返回当前任务、不重复起；
- 单张失败跳过不阻断（计入 `failed`）。

## 6. ImageVariant 语义收紧

`image_variants` 本轮**只表示同一逻辑 Image 的展示/缓存 rendition**：

- 第一版：`thumbnail`、`preview`；
- **不得**把 `upscaled` / `processed` 派生 Image 塞进 `variants`。

创作内容的派生关系已由 `images.kind`（original/upscaled/processed）+
`images.parent_image_id` 表达，不要再用 variants 做双重表示。
DB CHECK 中保留的 `upscaled`/`processed` 仅是历史枚举占位，业务层不写入。
