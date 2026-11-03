# W4.0 — 工作流与模型收敛验收报告

> 项目：`nsfw-studio-v2` · 日期：2026-11-03 · 分支：`main`
> 基线：`80ba41b199424a0fcb9edc2f3b76643790a7a84d`
> 状态：四个正式工作流收敛完成；upscale 已下线；模型资产已归档；四条 G3 真实出图与 carrier 三周期验收通过。

---

## 1. 最终四个正式工作流

`default_registry().ids()` = `anime_generate` / `basic_generate` / `img2img` / `reference_generate`。
`GET /api/v1/modules` 只返回这四个模块（`upscale` 已不再注册、不可解析、不可提交）。

| module_id | 标题 | 绑定 | 能力 |
|---|---|---|---|
| `basic_generate` | 文生图 | `v2` | 无输入图，Qwen-Image 2.1 |
| `anime_generate` | 动漫生图（MiaoMiao） | `v2` | 无输入图，miaomiaoHarem v14 |
| `img2img` | 图生图 | `v3` | 1 张 source 输入 |
| `reference_generate` | 参考图生成 | `v2` | 1 张 reference 输入 |

普通用户工作台只显示以上四个工作流，不展示历史 Binding 版本。

## 2. 四套默认 Binding

运行时真实指纹（以部署运行树 `nsfw-studio-v2-app` 为准，由 `/engine/preflight` 与 JobStage 记录）：

| 模块/版本 | workflow_hash | binding_hash | 模型 | 默认参数 |
|---|---|---|---|---|
| `basic_generate/v2` | `9da86110a20db1ed` | `e34bf33b8451ec81` | qwen-image-2.1-UC-Q4_0.gguf、qwen3vl_8b_w4a8、texture_fix VAE、turbo8 LoRA、f23gg LoRA | 832×1216 / 12 步 / cfg 1.0 / euler simple |
| `anime_generate/v2` | `144a4b9f63e8dc67` | `a0aa56fb921178b0` | miaomiaoHarem_v14.safetensors（CheckpointLoaderSimple） | 832×1216 / 30 步 / cfg 4.0 / er_sde simple / denoise 1.0 |
| `img2img/v3` | `d8fac1d3b2e9c627` | `8ed91f6860c51cb4` | 同上 Qwen 三件套 + texture_fix VAE | denoise 0.8 / 25 步 / cfg 1.0 / euler simple |
| `reference_generate/v2` | `65dbbd6ca22eb9e7` | `4ac3b58b16203412` | 同上 Qwen 三件套 + texture_fix VAE | 25 步 / cfg 1.0 / euler simple；参考图结构不变（仍上限 1 张） |

- `configs/workflow.yaml` 已切到上述四个默认 binding；`module_version` 与 `binding_version` 保持独立。
- `workflows/release_manifest.yaml` 已更新：四个新 binding `dependencies_ready=true`、`real_gate_passed=true`，`default_profile_verified=false`（G4 未测，未虚标）。
- 历史 Binding 全部保留：`basic v1`、`anime v1`、`img2img v1/v2`、`reference v1` 仍为 frozen，旧证据原样保留，未用旧结果冒充新版本证据。

## 3. 历史 Binding 保留情况

| 历史版本 | 状态 | 说明 |
|---|---|---|
| `basic_generate/v1` | frozen | 8 步 turbo + 旧 Qwen VAE；仅历史 Job |
| `anime_generate/v1` | frozen | Anima 2.9B + Qwen3-0.6B；仅历史 Job |
| `img2img/v1` | frozen | denoise 0.55 |
| `img2img/v2` | frozen | denoise 0.8 |
| `reference_generate/v1` | frozen | 旧 Qwen VAE |

旧 Binding 文件未被覆盖；历史 `workflow_hash` / `binding_hash` 未被修改。

## 4. upscale 完整下线报告

**后端**
- 删除 `UpscaleModule`、`default_registry` 注册、`workflows/__init__.py` 导出。
- 删除 `POST /api/v1/images/upscale` 路由与 `ImageUpscaleRequest`。
- Agent 请求体不再接受 `upscale`；旧客户端传 `upscale=true` 返回 **422 `AGENT_UPSCALE_REMOVED`**（显式拒绝，不静默忽略）。现场验证通过。
- 相关服务调用与任务追加逻辑已移除。

**前端**
- 移除高清开关、`hasUpscaleModule`、`setUpscaleEnabled`、Gallery HD 徽标、批量高清按钮、图片详情高清入口、`imageApi.upscale` 及相关测试与样式。
- 前端 CI（typecheck + vitest + build）通过。

**工作流**
- 活动 `upscale` Binding 已移除；旧 `workflow.json` / `binding.yaml` 归档到 `archive/workflows-2026-11/upscale-v1/`。
- `workflows/release_manifest.yaml` 的 upscale 段已删除；`upscale_models` 目录现为空（仅有占位文件），4x-UltraSharp 已不在任何模型搜索路径。

**兼容性（全部满足）**
1. 历史 `kind=upscaled` 图片仍可列表/详情/文件流读取（现场实测 15 张，`/images?kind=upscaled` = 15）。
2. 原图与派生图父子关系保留（`parent_image_id` 有值）。
3. 历史 Job / Stage 不删除（`upscale/v1` 的 2 个 COMPLETED Job、8 个 Stage 仍在库中）。
4. `images.kind` 的历史 `upscaled` 值保留（15 条）。
5. `image_variants` 历史类型保留（现存 `thumbnail`/`preview`；历史无 `upscaled` 变体类型，未新增也未删除）。
6. 未修改任何旧 Migration；7. 未清空 DataRoot；8. 未提供新的放大替代功能。
- 未发现未完成的旧 upscale Job（Gate 0 已确认无 QUEUED/PAUSED/RUNNING）。

## 5. 模型资产清理报告

活动模型（6 个，全部通过 SHA256 实测）：

| 文件 | 大小 | SHA256（前 16） |
|---|---|---|
| qwen-image-2.1-UC-Q4_0.gguf | 3959.2 MB | `13f59f20656efc0a` |
| qwen3vl_8b_w4a8.safetensors | 6019.7 MB | `7754425e55e7bea2` |
| texture_fix_vae_for_qwen_image_2.1_bf16.safetensors | 644.2 MB | `36f56608b02077a5` |
| qwen_image_2.1_turbo8_lora.safetensors | 871 MB | `208dd43250e1e014` |
| f23gg_nsfw_qwen21.safetensors | 152.1 MB | `c29f503f35158778` |
| miaomiaoHarem_v14.safetensors | 6616.6 MB | `e2039a9f785b1fc1` |

归档：`D:\AIHome_2.0_L1_L2\archive\models-2026-11\`，24 个文件，合计 **26.86 GB**（Anima 2.9B、SeedVR2 3B / Distill 1.4B / 两个 VAE、qwen_3_06b_base、qwen_image_vae、旧 Qwen 2.1 VAE、CLIP L/G、SDXL VAE ×2、11 个画布实验 LoRA 等）。
- 迁移方式：Copy → SHA256 校验 → 删除源文件；未使用 `/MOV`。
- 归档目录不在 ComfyUI 活动搜索路径（`extra_model_paths.yaml` 仅 `C:/ComfyUI_models` 与 `app/models`）。
- 源目录 `C:\AIHome_ModelCache\comfyui` 已清空；`C:\ComfyUI_models` 仅剩 4 个活动文件；`app/models/loras` 仅剩 2 个活动 LoRA。
- 重复判定按 SHA256：`femaledVaginus_v1.3.safetensors` 与 `qwen2_1-femaledVaginus-nsfw-v1_3-fine_L22-31.safetensors` 字节相同（`4e1b8d…`），归档只保留实体、未重复迁移。
- 保留未动：`app/models/ultralytics` 的 3 个人脸/手/人像检测模型（不在归档候选清单，且无活动 Binding 引用）。
- 完整清单（文件名 / 大小 / SHA256 / 原始路径 / 活动引用 / 历史引用 / 处理结果）：`docs/W4_0_MODEL_INVENTORY.csv`。

## 6. Preflight 检测报告（Task D）

`backend/app/services/runtime_preflight_service.py`：
- 新增 `CheckpointLoaderSimple: (ckpt_name, checkpoints)` 与 `FOLDER_ALIASES["checkpoints"]="checkpoints"`，确保 `/models/checkpoints` 能检测 miaomiaoHarem。
- 修正 `UnetLoaderGGUF` 为 `unet_gguf` 目录（实测本机 fork 的 `/models/diffusion_models` 为空，`/models/unet_gguf` 才返回 qwen GGUF）；三个 binding 的 `requirements.models.type` 同步改为 `unet_gguf`。
- 未知 Loader / 未知 requirements 类型仍然返回 **UNKNOWN**，不会静默 READY；新增静态测试覆盖两类行为。

现场 `POST /api/v1/engine/preflight`（引擎 ComfyUI 0.37.0 在线）结果：

| 模块 | 状态 | missing_nodes/models/requirements |
|---|---|---|
| `basic_generate/v2` | **READY** | 全空 |
| `anime_generate/v2` | **READY** | 全空 |
| `img2img/v3` | **READY** | 全空 |
| `reference_generate/v2` | **READY** | 全空 |

完整响应：`temp/w4_preflight_four.json`（验收包内）。

## 7. 四条工作流真实出图记录（G3）

全部经 Studio 单队列 + 单 Worker + ComfyUI 真实执行，各一张：

| 模块 | Job | workflow_hash | binding_hash | 参数 | 耗时 | 输出 |
|---|---|---|---|---|---|---|
| basic_generate/v2 | `job_5fae2698-45c0-40a2-bfb8-9b25ba3e1dca` | `9da86110a20db1ed` | `e34bf33b8451ec81` | 832×1216 / 12 步 | 168.3 s（含冷加载） | `img_1488807d…` 1776 KB |
| anime_generate/v2 | `job_0f43ce4e-e143-4079-bce3-06f9b7f6c77d` | `144a4b9f63e8dc67` | `a0aa56fb921178b0` | 832×1216 / 30 步 | 119.1 s（含 checkpoint 加载） | `img_15ae8248…` 1337 KB |
| img2img/v3 | `job_40e4081b-377a-44ba-a2f3-3827d9d77b88` | `d8fac1d3b2e9c627` | `8ed91f6860c51cb4` | denoise 0.8 / 25 步 | 541.0 s（含模型换入） | `img_0897edfa…` 1869 KB |
| reference_generate/v2 | `job_44dd171f-f91d-4cee-8e62-f94f1bf04755` | `65dbbd6ca22eb9e7` | `4ac3b58b16203412` | resolution 768 / 25 步 | 683.2 s | `img_ccbedfec…` 640×928，1250 KB |

- 四条 Job 均为 `COMPLETED`，`completed_count=1`；输入图复用上一链输出（basic → img2img → reference）。
- `default_profile_verified` 保持 `false`：本次只做 G3 单张验证，未做 G4 峰值/耗时档记录。

## 8. carrier 三周期验收

`projects/comfyui/runtime/acceptance-test.ps1`（服务全停时执行）：

```
cycle1/2/3: task Running → 8490 ready (service=comfyui) → 8188 200 → stop → Task Ready, LastTaskResult=0
→ 端口 8188/8490 释放 → 残留进程 0
ALL LIFECYCLE CHECKS PASSED
```

## 9. 测试与 CI

| 项目 | 结果 |
|---|---|
| 后端全量 pytest（本机） | **697 collected，全绿（1 skipped）** |
| 新增 preflight 测试 | 覆盖 CheckpointLoaderSimple/checkpoints、未知 requirements 类型 → UNKNOWN |
| G0 静态校验 | `checked=9 errors=0 warnings=12`（warning 均为历史冻结 binding 的既有项） |
| 前端 typecheck + vitest + build | CI 通过；本地 Vite 构建 9.55 s |
| GitHub CI | `41573977381`（8bb79a0）success；`41578585410`（b25565a）success；`41579171678`（5be526c）success；最终提交链接见第 10 节 |

## 10. 提交与 CI

| 提交 | 内容 |
|---|---|
| `80ba41b` | 基线（GitHub main） |
| `8bb79a0` | W4.0 四工作流收敛与 upscale 下线（四套新 binding、前后端移除、归档） |
| `b25565a` | preflight 按实际 `unet_gguf` 目录检测 + 测试 |
| `5be526c` | 依赖探测 READY、临时放行 G3 |
| 最终提交 | 本报告 + 模型清单 + manifest G3 证据（见交付说明） |

CI：`https://github.com/zxingyu178-dot/nsfw-studio-v2/actions`（main 全绿）

## 11. Gate 0 记录（按数据库实际）

- Job 总量 941（不含本次 G3 新增）。分组：`anime_generate/v1` 346（COMPLETED 293 / CANCELLED 47 / FAILED 4 / INTERRUPTED 2）；`basic_generate/v1` 578（COMPLETED 303 / CANCELLED 236 / FAILED 28 / INTERRUPTED 11）；`img2img/v1` 13；`reference_generate/v1` 2；`upscale/v1` 2。
- **INTERRUPTED 实际为 13 个**（`basic v1` 11 + `anime v1` 2），并非规格中提到的 119；未发现 QUEUED/PAUSED/RUNNING 旧任务。
- 这 13 个 INTERRUPTED 任务分别依赖 Anima 2.9B / qwen_3_06b / 旧 Qwen VAE（已归档）或旧 Qwen 链；按冻结策略不可续跑，Job 记录与图片全部保留。
- 图片：`original` 7703、`upscaled` 15、`processed` 11；`image_variants`：thumbnail 7691、preview 2918。
- 数据库备份：`D:\NSFW-Studio-Data\backups\studio-20261103-125347.db`（SQLite backup API）。

## 12. 必须说明的一次性数据修复（不属于新 Migration）

首次 basic G3 在导入阶段失败：`mobile_image_events.event NOT NULL`。只读检查确认生产库仍是旧分支结构 `(seq, image_id, event)`，而 0022 只做原位 `ADD COLUMN`，遗留的 `event NOT NULL` 使新事件写入失败（所有新图都会受影响）。

处理：停止 Studio → 官方脚本备份 → 以副本重建方式把该表归一为主干结构（保留 `seq` 游标、`event_id/event_type/revision/payload_json/created_at`，8002 行全部保留）→ 只读校验 → 重启 Studio。**未新增 Migration、未修改旧 Migration 文件、未删数据、未清 DataRoot**。修复脚本为一次性诊断工具：`temp/w4_repair_mobile_events.py`。

遗留建议（本阶段未做）：`0022` 的旧结构升级路径本身应在重建后丢弃 legacy `event` 列，建议后续单独提修复与回归测试。

## 13. 已知限制 / 后续

1. **G4 未执行** → 四个新 binding 的 `default_profile_verified` 均为 `false`；不得据此宣称默认档性能已验证。
2. **换行差异导致双指纹不稳定**：dev 树与部署树的同一提交在 LF/CRLF 上不同，`workflow_hash/binding_hash` 会不同（本报告与 manifest 记录的是部署运行树的指纹）。建议后续加 `.gitattributes` 固定换行，避免历史 Job 恢复跨树失败。
3. 13 个 INTERRUPTED 历史 Job 依赖已归档模型，确认不可续跑；未删除、未改写。
4. 归档目录含 1 组 SHA256 重复文件（两个文件名、同一实体内容），未做二次清理。
