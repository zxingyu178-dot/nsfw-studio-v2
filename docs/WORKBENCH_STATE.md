# WORKBENCH_STATE — 工作台状态契约（Phase 1 + Phase 2 + Phase 3，v0.4.0）

> 更新：2026-10-08。统一工作台快照是 Phase 1 的核心设计点；Phase 2 打通生成链路后
> 快照同时是 Job 的固化输入（§十）与 Image → Workbench 的恢复载体（§四十七）；
> Phase 3 起 `workflow_modules` 由"② 高清放大"开关决定（§十五/§十六）。

## 1. WorkbenchSnapshot

前后端共用同一个结构（后端 `app/schemas/workbench.py`，前端 `src/types/workbench.ts`，
字段名双侧镜像，禁止各自另起）：

```jsonc
{
  "prompt_mode": "structured",          // structured | full
  "structured_prompt": {                 // 八部分，顺序永久固定
    "style": "", "face": "", "clothing": "", "pose": "",
    "scene": "", "composition": "", "lighting": "", "extra": ""
  },
  "full_prompt": "",                     // 完整模式正向（结构化模式下为合成预览，仅参考）
  "negative_prompt": "",
  "selected_assets": {                   // slot -> 素材版本引用（保存配方时固化为快照）
    "clothing": { "asset_id": "ast_...", "asset_version_id": "astv_...", "name": "白衬衫" }
  },
  "width": 1024, "height": 1024,
  "count": 1,
  "seed_mode": "random",                 // random | fixed（"使用此图 Seed"，仅单张，§0.4）
  "seed": null,                          // fixed 时的 Seed；仅 count=1 允许（多张自动切回 random）
  "workflow_modules": [],                // Phase 3：开启高清 = [basic_generate, upscale]；关闭 = []
  "source_prompt_id": null,              // 来源追溯（可选）
  "source_prompt_version_id": null
}
```

**异步与合成原则**：结构化模式下，`full_prompt` 的权威值由后端 PromptComposer 合成；
前端预览调用 `POST /api/v1/prompts/compose`（与保存同源），UI 不允许直接编辑拼接结果。

## 2. 注入路径（全部复用同一结构）

| 来源 | 方式 | 恢复内容 |
| --- | --- | --- |
| Prompt → Workbench | 提示词页"在生成工作台打开"：以当前版本构造快照，经路由 state 注入 | prompt_mode / 结构化字段 / 完整 Prompt / Negative；尺寸数量回默认 |
| Asset → Workbench | 素材页"用于生成"：`GET /api/v1/assets/{id}/workbench` 返回快照（structured[slot]=prompt_text，selected_assets 记录引用） | 素材 Prompt 填入对应 slot（素材在前），用户可继续编辑；**绝不回写 AssetVersion** |
| Recipe → Workbench | 配方页"在生成工作台打开"：由 RecipeVersion + asset_snapshots 构造快照注入 | **100% 恢复**：Prompt / Negative / 结构化字段 / 素材引用 / 尺寸 / 数量 / Workflow 快照（含高清开关，§十六） |
| Image → Workbench（§四十七） | 图库详情"在生成工作台中打开"：`GET /api/v1/images/{id}/workbench` 返回 **Job 当时的工作台快照**；"使用此图 Seed" 额外把 `seed_mode=fixed, seed=该图 Seed, count=1` 写入快照（§0.4） | Prompt / Negative / 结构化字段 / 素材引用 / 尺寸 / 数量；Seed 默认 random |
| （预留）Agent → Workbench | Agent 生成/修改快照后注入 | — |

**Job 固化（§十）**：提交生成时 `snapshotFromState()` 的快照按原样存入
`jobs.workbench_snapshot_json`，同时派生 positive/negative/structured 快照列；
之后 Prompt / Recipe / Asset 的任何修改都不影响已创建的 Job。

前端实现：`src/stores/workbenchStore.ts`（统一 WorkbenchStore，规范 §五十一），
`hydrateWorkbench(snapshot)` 全量注入；路由 state 契约见
`src/pages/Generate/workbenchNavigation.ts`（`{workbench, sourceRecipeId, replace}`）。

## 3. 状态归属

- WorkbenchStore 管理：promptMode / structuredPrompt / fullPrompt / negativePrompt /
  selectedAssets / width / height / count / seedMode / workflowModules；
- 组件不各自持有工作台状态；Phase 2 起生成按钮 = `snapshotFromState()` → `POST /api/v1/jobs`
  （JobService 固化快照），前端绝不直连引擎；
- 保存为 Prompt（POST /prompts）与保存为配方（POST /recipes）都从
  `snapshotFromState()` 取当前快照。

## 4. 版本历史

- 2026-10-07（v0.2.0）：初版，定义 WorkbenchSnapshot 与三条注入路径。
- 2026-10-07（v0.3.0）：新增 `seed / seed_mode=fixed`；Image → Workbench 正式接通；
  生成按钮改为 `POST /api/v1/jobs`（前端不直连引擎）。
