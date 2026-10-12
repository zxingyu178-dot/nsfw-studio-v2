# Phase 0.11 变更日志（CHANGELOG）

## [0.11.0] — 2026-10-12 — AI Asset Management System（图片资产管理系统）

> 基于 Daily Use（`feature/daily-use-ux-runtime`）**只扩展、不破坏**。

### 新增（数据库）
- 迁移 `0015_image_variant_system`：`image_variants` 表（id/image_id/variant_type/path/width/height/format/created_at），
  普通索引 + thumbnail 部分唯一索引；变体不污染 images 表。
- 迁移 `0016_image_review_status`：images 增 `status / reviewed_at / review_note`（默认 NEW）+ status 索引，
  旧 review_status 回填（KEPT→KEEP、REJECTED→REJECT），旧列保留。
- 新存储目录 `images/thumbnails`（config DEFAULT_LAYOUT + storage.yaml 登记）。

### 新增（后端）
- 标准分页 `GET /images`：page/page_size(40)/sort(created_desc/created_asc/favorite/size)/status，
  返回 `{items,total,page,page_size,has_next}`；旧 limit/offset 调用方兼容。
- `GET /images/{id}/thumbnail`：512px WebP q80，缺失按需生成并落 ImageVariant；`backfill_missing_thumbnails` 回填。
- `PATCH /images/{id}/status`、`POST /images/batch-status`：审核状态流转 / 批量审核；双写旧 review_status。
- `POST /images/cleanup-rejected`：两阶段废片清理（预览/真删），逐张 ImageReferenceService 引用保护，
  清空 Job 输出指针，按外键顺序删除，移除空目录。
- `GET /images/by-job/{job_id}/summary`：Job 审核统计。
- 新增依赖 Pillow>=10（缩略图解码/WebP 编码，非模型/custom node）。

### 新增（前端）
- Gallery 无限滚动（IntersectionObserver 哨兵，首屏 40、到底追加）。
- 缩略图懒加载 `GalleryThumb`（viewport+300px rootMargin，脉冲占位 + 错误态）；Grid 只载 thumbnail。
- 审核 Tabs（全部/待审核/收藏/归档）+ 状态子筛选（保留/淘汰）+ 4 种排序。
- 摄影选片式 `ReviewMode`：大图 + ←/→ + ✅保留(A)/⭐收藏(F)/❌淘汰(D)/Space 放大/ESC，
  打标自动前进，顶部进度与统计；**打标请求队列化，PATCH 期间快速连按不丢标**。
- Job 分组视图（按任务查看）：分组卡片 + Job 审核入口 + 统计。
- 两阶段废片清理 Modal（候选数量/占用空间/被引用保护）。
- Lightbox 右侧信息栏 `LightboxInfoPanel`（尺寸/时间/Seed/Job/模块/Prompt + 复制 Prompt/
  重新打开 Workbench/创建素材/设封面/删除），在现有 Lightbox 上扩展、不推翻。
- 图片详情（抽屉）增强：创建素材、设为 Prompt 封面、删除（引用保护）。
- Prompt 卡片封面改用 thumbnail（lazy）。

### 安全 / 红线
- 未改 Engine/ComfyUI Runtime/Adapter、Queue Job State/暂停恢复、PromptVersion、Recipe 快照、现有 Lightbox 本体。
- 未新增 AI 能力 / 模型 / Anime 正式化 / FaceID / IPAdapter / ControlNet / 自动评分 / 自动标签 / 手机端。
- 删除一律先经 ImageReferenceService 引用检查，被 Prompt/Asset/Recipe 引用的图禁止删除。

### 测试
- Backend：280 → **312**（+32，只增）。
- Frontend：121 → **130**（+9，只增）；typecheck / build 通过。
- 真机 E2E：1000 张合成图分页/懒加载/滚动、约 100 张 REJECT 清理（删 98/保护 2）、
  Job 审核（保留5/淘汰11/未审0）、素材/封面联动、视觉矩阵 1280×720/1440×900/1920×1080（Dark 全测、Light 1440×900）。
