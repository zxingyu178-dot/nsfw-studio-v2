# NSFW Studio V2 — Phase 2.1 验收报告（Stable Execution & Pipeline Contract Closure）

> 日期：2026-10-07 ｜ 版本：0.3.1 ｜ 基线：v0.3.0 (78571af) ｜ 分支：fix/phase2-stable-execution
> 执行：TRAE Code Agent。本阶段不新增产品功能，只修复执行漏洞并把真实运行链接回 WorkflowModule 架构。

## 一、修复清单（对应合同章节）

| 章节 | 缺陷 | 修复 |
| --- | --- | --- |
| §一（P0） | 无图片却 COMPLETED（取输出/导入失败仍继续） | 完成条件收紧：engine succeeded → 取回输出 → ≥1 个合法输出 → 成功导入 Studio Image → 才 COMPLETED；任何一步失败 → Item FAILED + Job FAILED + completed_count 不增加 + image_id=null；恢复路径同样收紧 |
| §二 | ComfyUI 掉线后永久 RUNNING（history 网络异常返回 None） | `_history_state` 区分"请求失败"与"任务未完成"：ConnectError → ENGINE_OFFLINE（系统性 + 队列暂停）；其他网络错误 → ENGINE_NETWORK(transient) 有限重试；history 可达但任务缺失 → /queue + 实时层新鲜度判定，超容忍（10 次）才 unknown（引擎丢失任务）；WS 实时层带新鲜度时间戳，stale 不掩盖掉线 |
| §三 | Worker 硬编码 basic_generate 参数 | 新增 BasicGenerateModule（标准输入/引擎请求/校验）+ ModuleRegistry + PipelineExecutor；Worker 只做 `pipeline.build_engine_request(job, item, seed)`，源码级断言不含模块参数名（新增测试） |
| §四 | workflow_snapshot.modules 与实际执行不一致 | Job 创建/续跑时由 module_identity 构造 `modules:[{module_id,module_version,provider,binding_version,workflow_hash}]`；数据库快速查询字段保留 |
| §五 | Resume 复用 fixed seed（1000/1001/…） | resume_remaining 生成新快照：`count=remaining, seed_mode=random, seed=null`（workbench + generation_settings 同步）；原 Job 快照只读不动（回归测试：父 fixed→子 random，且子 Seed 不与父集合重合） |
| §六 | priority 永久越过拖拽顺序 | queue_position 成为唯一执行顺序事实源：Worker 领取、GET /queue、reorder 三处统一 `ORDER BY queue_position, created_at`；`queue_mode=next` 仅通过插入位置实现；priority 字段保留但不再参与排序（回归测试：next Job 拖后 → 队列与实际执行顺序都遵守拖拽） |
| §七 | ComfyUIAdapter 硬编码 `basic_generate/v1` | binding 目录由 `module_id + binding_version` 解析（`workflows/providers/comfyui/<module>/<version>/`）；新增错误类型 BINDING_NOT_FOUND（系统性）；测试：v1 可加载、v2 fixture 可切换、不存在版本明确报错 |
| §八 | JobCreateRequest.snapshot 过宽 | 直接复用 WorkbenchSnapshotModel：width/height 64–4096、count 1–64、seed 0–2147483647、prompt_mode/selected_assets/workflow_modules 结构校验（422）；Prompt 长度上限（结构化字段 ≤2000/正向 ≤10000/负向 ≤8000，400 PROMPT_TOO_LONG） |
| §九 | Cancel 请求异常导致进程级异常/错误终态 | 取消请求 try/except 隔离：失败只记警告，当前 Item 允许完成，完成后边界检查落 CANCELLED（回归测试：cancel 抛网络异常 → 任务仍安全 CANCELLED） |
| §十 | Handoff ZIP（无 .git）pytest 失败 | gitignore 断言改为 .gitignore 文本规则；存在 .git 时才附加 git check-ignore 核对；并实际把交接 ZIP 解压后跑快速套件验证（见 §三） |

## 二、验证结果

```
快速套件（CI 同口径，无 ComfyUI）：120 passed
  其中 Phase 2.1 新增：test_phase21_stability.py 22 例 + test_comfyui_resilience.py 7 例
真实 ComfyUI smoke（1 张，ComfyUI 在线时运行）：PASSED（见下）
前端 npm run build：通过（tsc + vite）
交接 ZIP 解压独立运行快速套件：通过（无 .git 环境）
develop CI：见 GitHub Actions（推送后记录）
main CI：见 GitHub Actions（推送后记录）
```

真实 smoke 链路：Workbench → POST /jobs → BasicGenerateModule（PipelineExecutor 解析）
→ ComfyUIAdapter（module_id/binding_version 解析 binding）→ 图片导入 DataRoot → Gallery 读取；
断言 Item.image_id 非空、workflow_snapshot.modules 记录真实模块、图片 content 可读。

## 三、关键行为契约（修复后的固定语义）

```text
Item COMPLETED 的充要条件：
  engine succeeded
  ∧ get_job_outputs 成功且非空
  ∧ output_importer 成功且返回 ≥1 个 image_id
  → image_id 必非空；否则 Item FAILED（OUTPUT_MISSING / STORAGE_ERROR / 分类错误）

引擎不可达（history/queue 请求 ConnectError）：
  → ENGINE_OFFLINE → 当前 Job FAILED + 队列暂停（不重试）
瞬时网络错误（timeout 等）：
  → ENGINE_NETWORK(transient) → 提交/轮询各有限重试 ≤2
history 可达但任务缺失：
  → 在 /queue 或 WS 新鲜 → running；两者皆无且超容忍 → unknown（任务丢失）
队列顺序：
  → queue_position 唯一事实源；priority 只记录不排序
续跑：
  → 新随机 Seed（random/null），父 Job 快照永不修改
provider binding：
  → workflows/providers/comfyui/<module_id>/<binding_version>/；缺失 → BINDING_NOT_FOUND
```

## 四、开发期间发现并修复（本阶段）

1. 测试自身缺陷：worker 源码断言最初直接搜索字符串，会连注释一起命中 → 改为 tokenize 去注释/字符串后断言。
2. Mock 适配器此前 `get_job_outputs()` 恒返回空 —— 在新完成条件下会导致所有 Mock 用例 FAILED；
   改为返回 1×1 PNG fixture（`source=mock` 标识，符合 §二十二"Mock 只允许 fixture"），
   同时把"成功必须导入"变成所有 Mock 用例的隐含回归。
3. `_finish_job` 顺带把首个 FAILED Item 的 error_type/message 落到 Job，便于 UI 展示失败原因。

## 五、范围声明

- 本阶段未新增高清 / 图生图 / 参考图 / 视频 / 手机端 / Agent / 新模型；
- 未改动前端交互结构（生成/队列/图库 UI 与 v0.3.0 一致），仅受益于后端语义修复；
- 真实 ComfyUI 只跑 1 张 smoke（合同 §十二），未重跑 1/3/8 整套。

## 六、限制与说明

- ComfyUI 必须在线才能跑 smoke / 集成测试（离线自动 skip，不污染 CI）；
- 队列"暂停"仍为内存态（重启自然恢复，Job 状态不受影响，设计如此）；
- `priority` 字段保留用于历史/显示，任何排序逻辑不得再引用它（QUEUE_SPEC 已固化）。