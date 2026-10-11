# NSFW Studio V2 — Phase 0.11 阶段完成报告（PHASE_REPORT）

> 阶段：AI Asset Management System（图片资产管理系统）
> 基线：`feature/daily-use-ux-runtime`（f6fad0d）→ 分支 `feature/phase0.11-image-asset-management`
> 原则：**只扩展、不破坏 Daily Use**。

## 1. Git
- 独立 worktree `projects/nsfw-studio-v2-phase011`，分支 `feature/phase0.11-image-asset-management`。
- 共 8 个提交（详见 GIT_COMMITS.md）；最终 commit **`2013f0a21b22d71a8d04f1bbfb2b41e1f7d71829`**。
- 已 push 到 origin（见第 9 节核验）；**未 merge main**，停 feature 分支等待审查。
- 未对主工作树 / Daily Use worktree 做任何 stash/reset/clean/checkout。

## 2. 完成功能（九个模块）
1. **图库性能**：GET /images 标准分页（page/page_size=40/sort，返回 items/total/page/has_next）；
   IntersectionObserver 无限滚动；懒加载（viewport+300px，占位/错误态）。
2. **Thumbnail 系统**：images/thumbnails，512px WebP q80，入库生成 ImageVariant(thumbnail)；
   Grid 只载 thumbnail、Lightbox 载 original；历史缺失按需/回填、不阻塞浏览。
3. **审核状态**：NEW/KEEP/FAVORITE/REJECT/ARCHIVED（REJECT 不立即删）。
4. **Review Mode**：全部/待审核/收藏/归档；大图 + ←/→ + ❌/⭐/✅；快捷键 ←/→/A/D/F/Space；
   打标自动前进、进度与统计；快速连按队列化不丢标。
5. **Job 审核入口**：分组卡片"开始审核"，显示总数/未审核/保留/淘汰统计。
6. **废片清理**：两阶段 NEW→REJECT→批量确认；弹窗数量/占用/释放；删 original+thumbnail+DB；
   删除前 ImageReferenceService 引用保护。
7. **图片→素材**：详情"创建素材"复用 Asset API，记录 source_image_id/preview。
8. **Prompt 联动**：复用 preview_image_id，详情"设为 Prompt 封面"；Prompt 卡片显示缩略图/标题/摘要/复制/使用。
9. **详情增强**：现有 Lightbox 右侧信息栏（尺寸/时间/Seed/Job/模块/Prompt）+ 复制 Prompt/
   重新打开 Workbench/创建素材/删除。

## 3. 数据库
- 迁移 `0015_image_variant_system`：image_variants 表 + 普通索引 + thumbnail 部分唯一索引；变体不污染 images。
- 迁移 `0016_image_review_status`：images 加 status/reviewed_at/review_note + 索引，旧 review_status 回填、旧列保留。
- 新目录 images/thumbnails 登记。详见 DATABASE_CHANGE.md。

## 4. API
- 新增：GET /images（分页）、GET /images/{id}/thumbnail、PATCH /images/{id}/status、
  POST /images/batch-status、POST /images/cleanup-rejected、GET /images/by-job/{id}/summary。
- 复用：POST /assets（source_image_id）、PUT /prompts/{id}/preview-image。未破坏任何现有 API。
- 详见 API_CHANGE.md。

## 5. 测试
- Backend：280 → **312（+32，只增）**；新增 6 个测试文件。
- Frontend：121 → **130（+9，只增）**；新增分页/缩略图/ReviewMode/键盘/详情测试。
- typecheck / build 通过。详见 TEST_REPORT.md。

## 6. 实际验收（真实浏览器目检 + 断言）
- 1000 张合成图：首屏 40（firstPaint≈1.1s）、可滚到底（25 次分页、约 972~980 次缩略图请求）、
  浏览全程 0 次 original、占位/已载并存。
- 清理：预览候选 100/占用 ~886KB/保护 2 → 真删 **98**、保护 **2**、failed=[]；REJECT→2、total→902；
  被删文件+缩略图移除、受保护图 original 保留。
- Job 审核：初始 16/未审16 → 结束 **保留5/淘汰11/未审0**。
- 全局 Review：FAVORITE 10→11。
- 详情：复制 Prompt（剪贴板核验）、创建素材（GET /assets 核验 source_image_id）、
  设封面（GET /prompts 核验 preview_image_id）。
- Lightbox：信息栏、/content original、滚轮缩放（≈2.07×）、100%、下一张新 original。
- 视觉矩阵：1280×720 / 1440×900 / 1920×1080 Dark 全测；1440×900 Light（应用内切换，信息栏随主题）。

## 7. 已知问题 / 限制（如实）
- **Recipe 字段缺失**：当前 Image/Provenance 数据模型未携带 image→recipe 关联，信息栏显示"未直接关联配方快照"；
  其余字段齐全。
- **>100 图 Job 的审核**：startReviewJob 受 page_size≤100 限制，第一版只加载前 100；后续可改为分页拉全。
- 缩略图后端代码因并发提交被卷入前端测试 commit（内容完整全绿，归属混杂，未重写历史）。
- 未在真机做 Lightbox 拖动平移的逐项目检（滚轮缩放/100%/Fit/方向/ESC 已验证）。

## 8. 风险
- 1000 张与 Job 16 张均为**脚本合成图**，未真实生成（RTX3060 单张 12–17min，全真实不现实）；
  后端生成链路非本阶段改动、由既有测试覆盖。真实图像的缩略图解码已用真实 Pillow 解码路径测试。
- 全部写操作在独立临时 DataRoot 进行；正式 DataRoot（530 张/51MB）未做任何写操作。
- 删除操作均经引用保护，但建议正式清理前仍做备份（高风险动作）。

## 9. 同步与交付
- 已 `git push origin feature/phase0.11-image-asset-management`，并以 `git ls-remote` 核验本地=远端（见下）。
- 交付 `NSFW_Studio_Phase0.11_Handoff.zip`（报告/测试结果/Git 信息/核心源码/migration/启动脚本/config template），
  打包前做禁含扫描（无图片/模型/db/config.local.yaml/DataRoot/.venv）。
- 最终工作树 clean；等待审查，未 merge main。
