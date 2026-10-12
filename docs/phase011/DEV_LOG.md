# Phase 0.11 开发日志（DEV_LOG）

> 记录关键开发/决策/缺陷修复，便于交接与追溯。

## 阶段接地
- 从基线 `feature/daily-use-ux-runtime`（f6fad0d）切出 `feature/phase0.11-image-asset-management`，
  独立 worktree `projects/nsfw-studio-v2-phase011`，不污染 Daily Use worktree 与受保护主工作树。
- venv 用基础解释器 Python 3.11.15；安装 requirements-dev + Pillow 12.3.0；前端 npm ci（168 packages）。
- Task0 门禁：Backend 280 / Frontend 121，typecheck/build 绿；写 docs/PHASE011_BASELINE.md。

## 依赖决策
- **新增长期依赖 Pillow>=10**（写入 backend/requirements.txt，带注释）：缩略图/ImageVariant 的图像解码与
  WebP 编码（512px、q80）。属图像处理依赖，非模型 / custom node，理由同 psutil。

## 迁移（0015/0016）
- 0015 image_variants：普通索引 + thumbnail 部分唯一索引（每图至多一个 thumbnail，其它类型可多个）。
  变体不写回 images 表。
- 0016 images 加 status/reviewed_at/review_note + status 索引；旧 review_status 回填，旧列保留不删。
- 同步更新 golden 迁移列表（test_migration_upgrade、test_phase4_backfill）与 EXPECTED_DIRS（test_data_dirs）。
- images/thumbnails 在 config DEFAULT_LAYOUT 与 configs/storage.yaml 登记。

## 功能开发（两个并行子 agent，按冻结 API 契约）
- 后端：thumbnail_service.py、cleanup_service.py；改 images.py、schemas/image.py、image_service.py、ids.py；
  +6 测试文件。
- 前端：ReviewMode.tsx、GalleryThumb 懒加载、无限滚动哨兵、清理 Modal、详情增强、LightboxInfoPanel；
  改 GalleryPage、ImageLightbox、client/types、PromptTab。
- 并发提交导致历史归属混杂（前端 test commit 因共享 index 卷入后端缩略图代码），内容完整全绿，未重写历史。

## 真机走查发现并修复的真实缺陷（均复跑验证）
1. **Job 统计不随新状态变化**：job_gallery_summary 按旧 review_status GROUP BY，而 ReviewMode 写新 status。
   修复：image_service.set_image_status 双写旧 review_status（映射见 API_CHANGE）。
2. **清理残留空目录**：删 original.png 后留下空 per-image 目录。修复：cleanup _delete_one 在目录名==image.id
   且为空时 rmdir（守卫，不误删 originals 根）。
3. **Job 审核打不开（422）**：startReviewJob 请求 page_size=200，撞上后端 page_size≤100。修复：改 page_size=100，
   并注释 >100 图 Job 的第一版限制。
4. **快速连按丢标**：applyStatus 的 busy 守卫丢弃 PATCH 期间的按键（实测 16 张只落 15 标）。
   修复：ReviewMode 打标请求**队列化**（queueRef + processQueue），逐张落标自动前进，快速连按不丢。
5. **Light 信息栏不随主题**：误用不存在的 --surface token 导致信息栏恒暗。修复：改用 --panel/--fg/--fg-muted/--border。
6. flaky 前端测试：Gallery.pagination 在高负载下 waitFor 默认 1000ms 偶发超时；改为 4000ms。

## 真机/性能验收口径
- 用独立临时 DataRoot + 脚本合成 1000 张测试图（scripts/e2e/phase011_seed.py），不碰 530 张正式数据与 51MB 正式库。
- 缩略图目录初始为空（模拟历史无缩略图），验证按需生成。
- "审核 16 张"用合成图挂 demo Job 走查，**未真实生成 16 张**（RTX3060 单张耗时高），报告如实说明，未谎报真实生成。

## 自动化注意（实测）
- 直接"跳到底/scroll_into_view"会让哨兵持续 intersect、在 120/320 等点假停；可靠做法是逐页
  window.scrollTo(0, scrollHeight) 并 wait_for_function 等卡片数增长。
- 分组视图有两个"开始审核"（工具栏全局 + .gal-group 卡片内），Job 审核须 scope 到 .gal-group。
- 应用主题用显式切换（header 按钮），非 prefers-color-scheme；Light 验收需点击切换。
