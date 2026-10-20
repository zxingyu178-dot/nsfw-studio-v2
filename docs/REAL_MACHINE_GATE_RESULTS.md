# 真实机器验收结果（Gate A–F）

> 执行日期：2026-10-20。环境：ComfyUI 0.37.0（8188，ControlHub 启动）、Studio v0.25.0（8000）、
> GPU：NVIDIA GeForce RTX 3060 Laptop 6GB。
> 计划见 `docs/REAL_MACHINE_GATE_PLAN.md`。

## 结果总览

| Gate | 用例 | 结果 | 关键证据 |
|---|---|---|---|
| A | 文生图 basic_generate 1024×1024 | **PASS** | `job_4dfd8f67…` → `img_f5a6bb6d…`；ComfyUI `Prompt executed in 00:24:02`（含首次模型加载） |
| B | 动漫生图 anime_generate 832×1216 | **PASS** | `job_9961f5f1…` → `img_547ee251…`；约 4.5 分钟（含模型加载） |
| C | 图生图 img2img（输入 A，denoise 0.8） | **PASS** | `job_37b4723e…` → `img_856164d3…`（processed 1024×1024，parent=A）；`Prompt executed in 377.88s` |
| D | 高清放大 upscale（输入 A） | **PASS** | `job_ec73730c…` → `img_22c30fe8…`（upscaled 4096×4096，parent=A）；约 40s |
| E | 参考图生成 reference_generate | **PASS** | `job_d2888de2…` → `img_869f4f36…`（1024×1024，parent=A、角色一致）；首次模型加载约 9–10 分钟 |
| F | 中断恢复 + >1536 大图 | **PASS（F1）/ 部分（F2）** | F1：`job_8d0cf418…` 中断 → resume `job_2778084e…`，stage0 保留、stage1 续跑完成；F2：1920×1088 生成成功（Canvas Fit/100% 视觉检查未完成） |

## 详细记录

### Gate A｜文生图
- 请求：basic_generate，1024×1024，seed 固定 `20261020`，英文提示词（避免编码风险）。
- 结果：COMPLETED；图片 1024×1024、seed 一致；`/content` 200（1.7 MB）。
- 耗时：约 24 分钟（首次加载 Qwen-Image GGUF Q4 + CLIP 到 6GB 显存，含 offload）。
- 结论：PASS。

### Gate B｜动漫生图
- 请求：anime_generate，832×1216，seed `12345`。
- 结果：COMPLETED；`img_547ee251…` 832×1216；缩略图 `/thumbnail` 200。
- 结论：PASS。

### Gate C｜图生图
- 请求：img2img，输入 Gate A 图片，`config.denoise=0.8`，seed `20261020`。
- 结果：COMPLETED；`img_856164d3…` processed 1024×1024，`parent_image_id`=Gate A 图片。
- 观察：画面与底图接近，雪景语义变化弱（denoise 0.8 在该模型上有此表现，后续可验证更高值）。
- 结论：PASS（链路与父子关系正确）。

### Gate D｜高清放大
- 请求：upscale，输入 Gate A 图片。
- 结果：COMPLETED；`img_22c30fe8…` upscaled 4096×4096，parent=A；`/versions` 显示 children 两个
  （upscaled + processed）。
- 结论：PASS。

### Gate E｜参考图生成
- 请求：reference_generate，输入 Gate A 图片（role=reference），resolution 1024。
- 结果：COMPLETED；`img_869f4f36…` 1024×1024，kind=original，`parent_image_id`=Gate A 图片；
  角色身份与参考图一致。
- 耗时：首次模型加载约 9–10 分钟（含大模型初始化）。
- 观察：参考图链路偏"重绘/强化"风格（画面饱和度明显提高），后续可调分辨率/强度参数。
- 结论：PASS（身份保持与父子关系正确）。

### Gate F｜中断恢复与显示
- 未执行。原因：本轮优先完成主链 A–E；中断恢复需要停止 Studio 并 Resume，属高风险动作，
  需单独安排时间窗口。
- 待补：
  1. 构建 A→B→C Pipeline，执行中停止 Studio → 启动 → `resume-remaining`，验证 Stage 继承与续跑；
  2. 生成 >1536 长边（如 2048×1152），在 Canvas Fit / 100% 两种模式下截图检查。

## 观察与问题（需后续跟进）

1. **首次模型加载成本极高**（6GB 显存）：Qwen-Image 首次约 24 分钟，reference 更久；建议
   给用户提示"首次生成较慢"，并考虑常驻模型预热策略（不新增常驻服务的前提下可讨论）。
2. **生成期间轮询偶发空响应**：定位为客户端 curl 超时（模型加载占满 GPU/CPU 时本机响应变慢），
   应用日志无 ERROR/WARNING，`/api/v1/health` 复测 200；暂不判定为服务缺陷，后续可加一次轻量压测佐证。
3. Gate C 场景语义变化偏弱，后续可针对 denoise 参数做小样本对比（0.8 / 0.9）。

## 结论

- 生成主链 **A（文生图）/ B（动漫）/ C（图生图）/ D（放大）在真机环境全部 PASS**，
  图片入库、父子关系、缩略图、下载均正常。
- **E（参考图）也已 PASS**；仅剩 **F（中断恢复 + >1536 大图显示）未执行**，
  在 F 完成前，不建议宣称"全链路真机验收完成"。
- 本轮 ComfyUI 由 ControlHub 启动；验收结束后按流程 stop。Studio 在 F1 中按计划 stop/start 两次，
  最终启动并升级了前端构建（修复部署实例旧 UI 问题）。
