# Phase 0.11 任务清单与状态（TASKS）

> 图例：✅ 完成并验证；⛔ 本阶段明确不做；⚠️ 部分验证（见 PHASE_REPORT）。

## Task 0 — 环境与基线
- ✅ 独立 worktree `projects/nsfw-studio-v2-phase011`，分支 `feature/phase0.11-image-asset-management`（从 f6fad0d 切出）。
- ✅ venv（Python 3.11.15）+ requirements-dev + Pillow；前端 npm ci。
- ✅ 基线门禁：Backend 280 / Frontend 121，typecheck/build 通过；产出 `docs/PHASE011_BASELINE.md`。

## 数据库
- ✅ 迁移 0015 image_variants（表 + 普通索引 + thumbnail 部分唯一索引）。
- ✅ 迁移 0016 images status/reviewed_at/review_note + 索引 + 旧状态回填。
- ✅ images/thumbnails 目录登记（config + storage.yaml）。

## 九个功能模块
1. ✅ 图库性能：GET /images 标准分页（page/page_size=40/sort，items/total/page/has_next）；
   前端 IntersectionObserver 无限滚动；图片懒加载（viewport+300px，占位/错误态）。
2. ✅ Thumbnail 系统：images/thumbnails，512px WebP q80，入库生成 ImageVariant(thumbnail)；
   Grid 只载 thumbnail、Lightbox 载 original；历史缺失按需/回填、不阻塞浏览。
3. ✅ 图片审核状态：NEW/KEEP/FAVORITE/REJECT/ARCHIVED（REJECT 不立即删）。
4. ✅ Review Mode：全部/审核/收藏/归档；大图 + ←/→ + ❌/⭐/✅；快捷键 ←/→/A/D/F/Space。
5. ✅ Job 审核入口：分组/任务"开始审核"，显示总数/未审核/保留/淘汰统计。
6. ✅ 废片清理：两阶段 NEW→REJECT→批量确认；弹窗数量/空间/释放；删 original+thumbnail+DB；
   删除前 ImageReferenceService 引用保护。
7. ✅ 图片→素材：详情"创建素材"复用 Asset API，记录 source_image_id / preview。
8. ✅ Prompt 联动：复用 preview_image_id，详情"设为 Prompt 封面"；Prompt 卡片显示缩略图/标题/摘要/复制/使用。
9. ✅ 图片详情增强：现有 Lightbox 右侧信息栏（尺寸/时间/Seed/Prompt/Job/模块）+
   复制 Prompt/重新打开 Workbench/创建素材/删除。
   ⚠️ Recipe 字段：当前数据模型 Image/Provenance 未携带 image→recipe 关联，信息栏显示"未直接关联"（已知限制）。

## API
- ✅ GET /images（分页）、PATCH /images/{id}/status、POST /images/batch-status、
  POST /images/cleanup-rejected、GET /images/{id}/thumbnail、GET /images/by-job/{id}/summary。
- ✅ 创建素材复用 POST /assets；设封面复用 PUT /prompts/{id}/preview-image。未破坏现有 API。

## 测试
- ✅ Backend 新增 6 个测试文件，280 → 312（+32）。
- ✅ Frontend 新增 GalleryPagination/ThumbnailLoading/ReviewMode/KeyboardReview/ImageDetail，121 → 130（+9）。
- ✅ typecheck / build 通过。

## 真机 / 性能验收
- ✅ 1000 张合成图：首屏 40、可滚到底、分页+缩略图+懒加载、浏览 0 次 original。
- ✅ Review Mode 快捷键走查；Job 审核结束 保留5/淘汰11/未审0。
- ✅ 约 100 张 REJECT 清理：删 98、保护 2，文件+记录删除、被引用图保护。
- ✅ 优秀图创建素材，Asset 正常引用 source_image_id。
- ✅ 视觉矩阵 1280×720/1440×900/1920×1080 Dark 全测、Light 1440×900。

## 明确不做（保护红线）
- ⛔ Engine/ComfyUI Runtime/Adapter 改动；Queue Job State/暂停恢复；PromptVersion；Recipe 快照；推翻 Lightbox。
- ⛔ 新 AI 能力 / 新模型 / Anime 正式化 / FaceID / IPAdapter / ControlNet / 自动评分 / 自动标签 / 手机端。
- ⛔ merge main（停 feature 分支等待审查）。
