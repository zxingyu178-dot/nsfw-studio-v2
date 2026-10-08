# UPSCALE_WORKFLOW_INVENTORY — 本机高清放大链调查与选择（Phase 3 §十二）

> 调查方式：只读检查本机 `D:\AIHome_2.0_L1_L2\projects\comfyui` 的模型、用户工作流与节点。
> 未升级 ComfyUI、未安装新节点、未下载新模型、未修改用户原工作流。

## 1. 本机现状盘点

| 资产 | 位置 | 结论 |
| --- | --- | --- |
| `千问-4x审核放大.json` | `app/user/default/workflows/` | 用户工作流（UI 格式）：`UpscaleModelLoader → LoadImage → ImageUpscaleWithModel → SaveImage`，简单、可 API 化 |
| 历史输出 `upscale-4x/` | `app/output/upscale-4x/` | 2026-09-28 / 10-06 有产物 → **该链在本机已实际跑通过** |
| `4x-UltraSharp.pth` | `app/models/upscale_models/` | 已存在的 4x ESRGAN 类放大模型（轻量） |
| `ComfyUI-SeedVR2-1.4B`（自定义节点） | `app/custom_nodes/` | 不注册节点，仅给官方 SeedVR2 节点打补丁（6 层检测 / 单帧 VAE 快路径 / 显存释放） |
| SeedVR2 模型 | `app/models/diffusion_models/seedvr2_*` + `models/vae/seedvr2_*` | 已存在（1.4B distilled / 3B / VAE），但属 DiT 视频放大链，6GB 显存下更重 |
| `千问-批量审核4x可视化.json` | 用户工作流 | 批量审核可视化流（含额外节点编排），不适合作为 v1 绑定 |
| `ImageUpscaleWithModel` / `UpscaleModelLoader` | ComfyUI 官方 `comfy_extras/nodes_upscale_model.py` | 0.37.0 存在且输入契约未变（`model_name` / `upscale_model` + `image`） |

## 2. 最终选择：`upscale/v1` = 4x-UltraSharp 链

```
LoadImage(image=<Studio 上传>) → UpscaleModelLoader(4x-UltraSharp.pth)
→ ImageUpscaleWithModel → SaveImage(filename_prefix=NSFWStudio/{job_short}/{stage}/{item_short})
```

选择原因（按合同"优先复用当前电脑已经能够正常工作的高清链"）：

1. **已被证明可用**：`output/upscale-4x/` 有该链的历史产物；
2. **零新增依赖**：模型文件已在本机，无需下载；节点为 ComfyUI 官方内置，无需安装 custom node；
3. **适合 6GB 显存**：单次 4x ESRGAN 放大显存/耗时远低于 SeedVR2 DiT 链，且
   `ImageUpscaleWithModel` 内置分块（tiled）推理；
4. **结构最简单**：4 节点、单输入单输出，API 化后绑定面最小，便于 Workflow 身份固化与 hash 校验；
5. **固定 4x**：与图库"高清 ×4"展示语义一致。

对应文件（Studio 侧，不动用户原工作流）：

- `workflows/providers/comfyui/upscale/v1/workflow.json`（API 格式等价图）
- `workflows/providers/comfyui/upscale/v1/binding.yaml`（`input_image → LoadImage.image`）

## 3. 未选择 SeedVR2 的原因

- SeedVR2 需要官方节点（`SeedVR2` 系列）+ DiT + 视频 VAE 解码，1.4B 亦明显重于 4x-UltraSharp；
- 6GB 显存下更易触发 OOM（尽管 custom node 已有 1.4B 单帧补丁）；
- **如需更高画质**：后续可新增 `upscale/v2` binding 指向 SeedVR2 链（新建版本目录，不改动 v1，
  符合"binding 目录 immutable + workflow_hash 校验"规则，§0.3）。

## 4. 输入契约（Studio 侧）

```yaml
inputs:
  input_image: {node: "1", field: "image"}   # LoadImage.image = 已上传文件名（含 subfolder）
```

- 上传：`POST /upload/image`（subfolder=`NSFWStudio_inputs`，文件名=`<image_id>.png`），
  返回的引用名直接注入 `LoadImage.image`（ComfyUI 约定 `subfolder/name`）；
- 输出：`SaveImage` 的 `filename_prefix` 模板包含 Studio 身份，用于文件级恢复核对（§九）。

## 5. 复验方法（只读）

```powershell
# 模型与历史产物
Get-ChildItem 'D:\AIHome_2.0_L1_L2\projects\comfyui\app\models\upscale_models'
Get-ChildItem 'D:\AIHome_2.0_L1_L2\projects\comfyui\app\output\upscale-4x'
# 绑定文件
Get-Content 'D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2\workflows\providers\comfyui\upscale\v1\binding.yaml'
```