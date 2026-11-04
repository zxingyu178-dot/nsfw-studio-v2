# W4.1 — Model Center 与 Workflow Center 登记报告

> 日期：2026-11-04 · 基线：`9904e12` · 工具：`scripts/validate_registry.py`
> 定义真源：`registry/models/**/model.yaml`、`registry/workflows/**/manifest.yaml`
> 运行状态：`GET /api/v1/registry/models`、`GET /api/v1/registry/workflows`、`GET /api/v1/registry/validate`

---

## 1. 模型登记（Model Center）

| 项 | 数量 |
|---|---:|
| 活动模型 Manifest | 6 |
| 归档模型 Manifest | 24 |
| 已发布模型 SHA256 为 `unverified` | 0 |
| 重复 `model_id` | 0 |

活动模型：

| model_id | version | 类型 | 文件 |
|---|---|---|---|
| `qwen_image_2_1` | 2.1.0 | diffusion_model | `qwen-image-2.1-UC-Q4_0.gguf` |
| `qwen3vl_8b_w4a8` | 1.0.0 | text_encoder | `qwen3vl_8b_w4a8.safetensors` |
| `texture_fix_vae_qwen_image_2_1` | 1.0.0 | vae | `texture_fix_vae_for_qwen_image_2.1_bf16.safetensors` |
| `qwen_image_2_1_turbo8_lora` | 1.0.0 | lora | `qwen_image_2.1_turbo8_lora.safetensors` |
| `f23gg_nsfw_qwen21` | 1.0.0 | lora | `f23gg_nsfw_qwen21.safetensors` |
| `miaomiao_harem_v14` | 14.0.0 | checkpoint | `miaomiaoHarem_v14.safetensors` |

- 每个 Manifest 记录 `filename / folder / size_bytes / sha256`；
- 归档模型状态 `archived`，保留登记信息，物理文件不进入 Git；
- 本机安装状态通过 `model_registry.search_roots`（仅 `config.local.yaml`）解析；
- 未登记模型在正式 Binding 的 Preflight 中返回 UNKNOWN，不会静默 READY。

---

## 2. 工作流登记（Workflow Center）

| 项 | 数量 |
|---|---:|
| 活动工作流 Manifest | 4 |
| 历史/冻结 Manifest | 5 |
| 已归档 Manifest（upscale） | 1 |
| Hash 不一致 | 0 |
| 依赖缺失 | 0（历史归档依赖仅 warning） |

活动版本：

| workflow_id | version | binding_hash (LF) | workflow_hash (LF) | 模型依赖 |
|---|---|---|---|---|
| `basic_generate` | v2 | `d9ca1eba6c482f57` | `af870a6442432dfd` | qwen / qwen3vl / texture VAE / turbo8 / f23gg |
| `anime_generate` | v2 | `7832e2b669aa1c44` | `db2bd841c260a434` | miaomiao_harem_v14 |
| `img2img` | v3 | `21d056e2f9e7db77` | `c94f28966da4db41` | qwen / qwen3vl / texture VAE |
| `reference_generate` | v2 | `cfc68ee2f803c9ed` | `88007850182aff4d` | qwen / qwen3vl / texture VAE |

历史 Manifest：

| workflow_id | version | 状态 |
|---|---|---|
| `basic_generate` | v1 | frozen |
| `anime_generate` | v1 | frozen |
| `img2img` | v1 / v2 | frozen |
| `reference_generate` | v1 | frozen |
| `upscale` | v1 | archived（执行文件已移出活动目录） |

每个 Manifest 包含：`workflow_id / version / display_name / description / provider /
workflow_file / binding_file / model_dependencies / input_schema / output_schema /
default_parameters / parameter_constraints / hashes / release_status / validation_report`。

Hash 结构同时记录：
- `algorithm: lf-normalized-v1`；
- `workflow_hash` / `binding_hash`（LF 值）；
- `legacy_raw_workflow_hash` / `legacy_raw_binding_hash`（dev/app 树观测到的原始字节值）。

---

## 3. Validator 结果

命令：

```powershell
python scripts/validate_registry.py
```

结果：

```text
checked=40 errors=0 warnings=7
```

7 条 warning 均为历史冻结 Binding 依赖已归档模型（Anima、旧 Qwen VAE 等），属于预期历史兼容项；
活动工作流的依赖全部为 `released`。

---

## 4. API

| 端点 | 说明 |
|---|---|
| `GET /api/v1/registry/summary` | 模型/工作流数量与校验摘要 |
| `GET /api/v1/registry/models?include_archived=true&verify_hash=false` | 模型登记 + 本机安装状态 |
| `GET /api/v1/registry/workflows?include_history=true` | 工作流 Manifest + Hash + 放行状态 |
| `GET /api/v1/registry/validate` | 全量校验报告 |
| `GET /api/v1/registry/assets` | 图片资产统计 |
| `GET /api/v1/registry/assets/orphans` | 孤立文件（只报告） |
| `GET /api/v1/jobs/{job_id}/provenance` | Job → 工作流/模型/Prompt/Seed/输出资产 |

`/api/v1/modules` 新增 `registry` 投影（workflow_id / version / hashes / model_dependencies /
default_parameters / release_status），前端不得再维护第二份工作流配置。

---

## 5. 已知限制

1. SHA256 全量校验（`verify_hash=true`）会读取 GB 级模型文件，默认关闭；文件大小与 Manifest 始终校验。
2. 历史 Job 的 `model_snapshot` 缺失，`/jobs/{id}/provenance` 明确标记 `历史 Job`，不做推测。
3. 归档工作流（upscale）只保留定义，执行文件不在活动目录，Validator 跳过文件存在性检查。
