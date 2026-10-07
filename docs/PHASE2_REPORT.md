# NSFW Studio V2 — Phase 2 验收报告（Job Execution Core + ComfyUIAdapter + Gallery）

> 日期：2026-10-07 ｜ 版本：0.3.0 ｜ 基线：v0.2.0 (cc8f1b4) ｜ 分支：feature/phase2-execution-gallery
> 执行：TRAE Code Agent（接替开发；2A 段由前序会话完成并已提交 2c63137）

## 一、阶段目标达成

目标链路 **Workbench → Job → 单队列 → WorkflowModule → EngineAdapter → ComfyUI → Image → Gallery**
已全部打通并真实运行：

- 输入 Prompt / 使用配方 → 点击生成 → `POST /api/v1/jobs` → Job + N 个 JobItem 入单队列；
- 单队列 Worker 串行调用**本机真实 ComfyUI**（Qwen-Image 2.1 UC 文生图链）生成；
- WebSocket 进度 + 轮询兜底，右栏实时显示"第 N 张 · xx%"；
- 图片逐张经 Studio temp → 校验 → 原子移动 DataRoot → 数据库登记，中栏逐张显示缩略图；
- 图库按 Job 查看、审核（保留/淘汰）、收藏、Image → 工作台恢复、从图库创建素材。

未开发：高清放大 / 图生图 / 参考图 / ControlNet / 视频 / 手机端 / Agent / 豆包（符合 §六十）。

## 二、三段交付

### Phase 2A — Job / 队列 / Mock / SSE（已提交 2c63137）

- Migration 0005_job：jobs / job_items / job_events；`UNIQUE(source, client_request_id)` 幂等；
- Engine 层：输出获取接口、错误分类（9 类）、瞬态重试 ≤2、MockEngineAdapter、工厂；
- 事件总线 + JobService（创建/状态机/队列排序/续跑剩余）+ 单队列 QueueWorker；
- Job API（§二十四 全量）+ SSE + 磁盘空间检查 + 崩溃恢复；
- Mock 故障测试套件（§五十八 清单）。

### Phase 2B — 本机调查 + ComfyUIAdapter + 第一套真实生图

- **调查**（只读，未破坏环境）：ComfyUI 0.37.0 @ `127.0.0.1:8188`（计划任务 `\AIHome\ComfyUI` 承载），
  Python 3.12 venv、RTX 3060 6GB；可用模型 = Qwen-Image 2.1 UC GGUF 三件套（C:/ComfyUI_models）；
  选型 = nightbatch 已验证的 Qwen 文生图链（§二十八，不自创）；详见 docs/COMFY_ENV_INVENTORY.md、
  docs/WORKFLOW_INVENTORY.md；
- **provider binding**：`workflows/providers/comfyui/basic_generate/v1/`（workflow.json + binding.yaml + README），
  节点 ID 不污染核心（§二十九）；支持 negative prompt；
- **ComfyUIAdapter**：/prompt 提交、WebSocket 进度、/history 核对、/view 字节取回、错误分类、安全取消；
- 真实 health + 首张 832×1216 生图 + /view 取回验证（20261007_00001_.png）。

### Phase 2C — Image / Gallery / Review（本段）

- Migration 0006_image + ImageService（导入流程与失败回滚）+ Gallery API + 前端图库页；
- WorkbenchSnapshot 支持 seed（"使用此图 Seed"）；从图库创建素材（`source_image_id`）；
- 前端：SSE 任务流（jobStore）、Studio ● / Engine ● 双状态、右栏（引擎状态/生成/当前任务/队列）、
  中栏（当前图 + 逐张缩略图，续跑父子合并）、图库（筛选/Grid/详情抽屉/按任务查看）。

## 三、验收门槛核对（规范 §六十三）

| 项目 | 结果 |
| --- | --- |
| Job / JobItem 数据模型正确 | ✅ 0005 迁移 + 约束测试 + 升级测试 |
| 单 Worker 串行 | ✅ test_job_lifecycle_serial_completion（8 张串行） |
| 队列排序正确 | ✅ 优先插队 / 拖拽全量校验测试 |
| Pause / Cancel / Resume 语义正确 | ✅ Item 边界暂停、已完成图保留、完成后不重跑 |
| client_request_id 幂等 | ✅ 重复请求返回原 Job（idempotent_replay） |
| SSE 正常 | ✅ 真实 uvicorn 线程流式读取测试 + 前端 jobStore |
| MockEngine 故障测试通过 | ✅ §五十八 清单 14 场景（含瞬态网络重试 / Workflow 错误） |
| 本机 ComfyUI 环境调查、未破坏环境 | ✅ docs/COMFY_ENV_INVENTORY.md（未升级/未装节点/未动模型） |
| ComfyUIAdapter 可真实调用 | ✅ health / submit / history / view 全链路真实运行 |
| basic_generate Workflow 可工作 | ✅ 真实生成成功（1/3/8 张测试） |
| 1 / 3 / 8 张真实生成测试通过 | ✅ 3 passed（12 张图片全部入库） |
| 图片正式导入 DataRoot | ✅ 断言相对路径 + content 可读 + 元数据 |
| Image 元数据完整 | ✅ seed / 尺寸 / source / workflow_hash 溯源 |
| Gallery 可查看 | ✅ 图库页 + API 测试 |
| 审核状态 / 收藏正常 | ✅ review / favorite 测试 + 汇总统计含收藏数 |
| Image → Workbench 恢复正常 | ✅ 快照恢复 + 使用此图 Seed 测试 |
| 全部 pytest GREEN | ✅ 91 passed（快速套件）+ 3 passed（真实 ComfyUI 集成） |
| 前端 build GREEN | ✅ tsc + vite build |
| develop / main CI GREEN | ✅ GitHub Actions：develop 9da5821 success、main 9da5821 success |
| 未提前开发高清/图生图等 | ✅ 未开发（禁止清单逐项未触碰） |

## 四、真实运行实测记录

- 真实集成测试（本机 ComfyUI）：`test_real_generation[1] / [3] / [8]` 全部通过；
  640×960 每张约 102–118 秒（模型已在显存）；当天首张 832×1216 含模型加载约 300 秒；
- 固定 Seed 模式验证：`seed = base + item_index`（第二次运行前 3 张与第一次同 Seed 结果一致）；
- 顺序执行验证：engine_job_id 各不相同、逐张进入 Gallery、completed_count 逐个递增；
- Workflow Snapshot 验证：Job 快照完整（structured_prompt / seed_mode / 尺寸）。

## 五、开发期间发现并修复（本段）

1. `configs/workflow.yaml` 注释混入真实地址 `127.0.0.1:8188` → 触发公共配置守卫断言；改为占位说明；
2. 集成测试夹具作用域错误（module 级夹具依赖 function 级 settings）→ 改函数级；
3. `workflow_hash` 未写入 Job（§五十五 要求）→ `module_identity()` 从 provider binding 读取
   binding_version + workflow_hash；
4. §五十八 缺口补齐：Mock 增加瞬态网络模拟 + 新增"网络断开恢复"与"Workflow 错误"测试；
5. `by-job summary` 缺"收藏"计数（§四十九 示例含收藏 N）→ 补充 favorites 统计；
6. 交接打包脚本会把本机私有 `config*.local.yaml` 打进 ZIP → 增加私有配置排除守卫。

## 六、限制与说明

- 前端未做浏览器端到端自动化（IAB 限制）；交互逻辑以 API 测试 + 构建 + 本地 dev 运行验证为准；
- 真实集成测试依赖本机 ComfyUI 在线（离线自动 skip，不污染 CI）；
- 队列"暂停"是内存态：应用重启后队列自然恢复（Job 状态不受影响，符合设计）；
- 续跑（resume-remaining）使用新随机 Seed（未完成 Item 的旧 Seed 不复用，符合 §三十八）。