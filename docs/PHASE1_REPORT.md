# NSFW Studio V2 — Phase 1 验收报告（Prompt / Asset / Recipe Core）

> 日期：2026-10-07 ｜ 版本：0.2.0 ｜ 基线：v0.1.2 (c3bd120) ｜ 执行：ZCode Agent

## 一、阶段目标达成

核心链路 **Asset → Prompt → Workbench → Recipe → 重新打开 → 100% 恢复** 已打通并实测验证。
未接入 ComfyUI / 实际模型 / 真实 Workflow JSON / Job Worker / 生成队列 / 豆包 / Agent / 手机端；
工作台"生成"按钮明确显示**"生成引擎尚未接入"**，无任何假生成结果。

## 二、交付清单

| 模块 | 内容 |
| --- | --- |
| Migration | 0002_prompt / 0003_asset / 0004_recipe（未动 0001；v0.1.2 库升级测试 + 真实库先备份后迁移） |
| 数据模型 | 9 张表；TEXT 主键 + 前缀化 uuid4；UTC ISO 8601；FK/UNIQUE/CHECK 全量约束 |
| Prompt | 双模式（结构化八栏 / 完整）、Negative 独立、版本 immutable、恢复=复制为新版、软删除 |
| 合成 | PromptComposer 后端权威 + `POST /api/v1/prompts/compose`（前端预览同源，UI≠保存 不可能） |
| Asset | 四分类、预览图上传（四重校验）、temp→原子移动→提交（双向失败安全）、相对路径入库、防穿越 |
| Recipe | Prompt 快照+FK 双存、slot 级素材版本快照（UNIQUE）、generation_settings（model_ref 占位）、workflow 预留 |
| Service | PromptService / AssetService / RecipeService（单事务、冲突 409、不建冗余版本） |
| API | 三组全套端点 + 统一错误 `{"error":{code,message}}` + 列表统一参数 |
| 前端 | WorkbenchStore、生成三栏、提示词三 Tab（我的/配方/历史）、素材页、三条"打开工作台"注入路径 |
| 文档 | DATA_MODEL_V1.md、WORKBENCH_STATE.md + 既有文档同步 |

## 三、验收门槛核对（规范 §六十五）

| 项目 | 要求 | 结果 |
| --- | --- | --- |
| Prompt | CRUD、结构化/完整、Negative、版本历史正常 | ✅ 测试 + 浏览器实测 |
| Asset | 四分类、预览图、版本、归档正常 | ✅（上传自动化受 IAB 限制，逻辑由 API 测试全覆盖） |
| Recipe | Prompt + Asset 快照正确 | ✅ 含"老素材升级老配方不变"专项测试 |
| Workbench | 三栏形成，状态可保存/恢复 | ✅ 三条注入路径复用 WorkbenchSnapshot |
| Version | 旧版本不可修改，恢复产生新版本 | ✅ 测试守护（immutable + 线性恢复） |
| Storage | 所有素材文件位于 DataRoot，相对路径入库 | ✅ 断言无盘符、无绝对路径 |
| Migration | 从 v0.1.2 正常升级 | ✅ 测试 + 真实库（备份先行） |
| Backend | pytest 全绿 | ✅ **68 passed** |
| Frontend | npm run build 通过 | ✅ tsc + vite |
| CI | develop/main 全绿 | ✅ 见 GitHub Actions |
| Engine | 仍未接入任何实际生成模型 | ✅ workflow.yaml provider=unbound；无 Adapter 实现 |
| Git | main/develop 同步，tag v0.2.0 | ✅ |
| 文档 | DATA_MODEL_V1 + WORKBENCH_STATE + 原有文档同步 | ✅ |

## 四、实测发现并修复（开发期间）

1. 0004 迁移缺 `recipe_asset_snapshots.created_at` 列（测试暴露；迁移未发布，直接修正 DDL）。
2. `StorageManager.path` 白名单不含父目录 → `resolve_under("assets", ...)` 被拒；允许登记目录父目录。
3. 结构化合成最初只在路由层 → 下沉为 Service 权威逻辑（prompt/recipe 一致、幂等）。
4. 升级路径测试的 monkeypatch 恢复写法错误（自我赋值）→ 修正测试本身。
5. 环境事故：残留 vite 进程占 5173 缓存旧 CSS 造成"整页无样式"假象 → netstat 定位清理；
   教训记入 DEV_LOG（TaskStop 不杀 node 子进程）。

## 五、限制与说明

- 素材上传的**浏览器文件选择**自动化受 IAB 沙箱限制（不支持 file chooser），上传/校验/版本逻辑
  由 API 测试全链路覆盖，人工验证以 API 预置素材 + UI 展示/选择流程完成。
- 配方创建入口当前只在生成工作台（符合规范 §四十八）；配方页支持查看/恢复/归档/收藏。
- `assets.source_image_id` / `recipes.cover_image_id` / `reference_images_json` 为预留列，未启用。

## 六、下一步（Phase 2 预告）

EngineAdapter 首个实现（ComfyUIAdapter）与 Job/Queue/图库——合同要求 Phase 1 期间未开发，
相关接入点已在 DATA_MODEL_V1.md §8 预留。
