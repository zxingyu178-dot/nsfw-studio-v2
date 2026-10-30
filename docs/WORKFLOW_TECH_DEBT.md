# 工作流技术债清单（W0 登记）

> 日期：2026-10-30。本阶段只登记，不扩大修改范围；后续 W1/W2/W3 按优先级处理。

## W1 更新（2026-10-30）

- **已解决**：W0 直接修改 img2img/v1；W1 已恢复 v1 冻结指纹并新建 v2（0.8），
  审计确认 0 个 Job 使用 W0 新指纹。详见 `docs/W1_IMG2IMG_VERSION_AUDIT.md`。
- **已实现**：G0 静态校验器 `scripts/validate_workflows.py` + CI 阻断。
- **已实现**：`workflows/release_manifest.yaml` 与 `release_status.ready_to_run`；
  `anime_generate` 不再进入正常工作流选择列表。
- **归档核实**：`experiment/pose-generate-20261030` **仅存在本地，未推送远端**（按 W1 指令
  不擅自推送实验代码）；如需长期保存，后续由用户决定是否推送。

## P1 — 运行前保护缺失

1. **`module_availability()` 不检查依赖与硬件**
   当前只检查模块是否注册、binding 目录/文件是否存在、自描述与指纹是否一致；
   不检查模型文件、节点、显存/内存，也不验证是否通过真实 Gate。
   → W2：增加 `dependencies_ready` / `hardware_status` / `real_gate_passed` / `ready_to_run`。

2. **宽高上限 4096，缺少像素预算**
   `basic_generate` / `anime_generate` 继承的宽高上限为 4096；
   未按显卡显存与模型链设置最大执行尺寸/总像素。
   → W2：在 Job 创建期按硬件档案拒绝超限任务。

3. **图片导入只有文件大小限制，没有总像素限制**
   10 MB 压缩图仍可能是超大分辨率，进入 img2img 的 VAE 编码后可能 OOM。
   → W2：导入时检查宽、高、总像素，并与模块能力联动。

4. **执行指纹未覆盖实际依赖**
   `workflow_hash` / `binding_hash` 只覆盖两份文件；模型文件内容、自定义节点版本、
   ComfyUI 版本变化不会使指纹失效。
   → W2：在 G2 增加实际依赖校验，并把校验结果写入 Job 证据。

## P2 — 验收覆盖与性能事实

5. **真实 ComfyUI 集成测试覆盖不均**
   目前主要覆盖 `basic_generate` 与 `upscale`；`img2img`、`reference_generate`、
   `anime_generate` 的真机 Gate 不完整。→ W3 按单张、串行、逐步提高分辨率重测。

6. **`reference_generate` 默认配置未验证**
   已验证配置为 640 参考分辨率 / 20 步 / 单张 60+ 分钟；正式默认 1024 / 25 步，
   没有对应的 G3/G4 证据，不得当作已验证默认。→ W3 补测或下调默认。

7. **`anime_generate` 性能宣传缺证据**
   模型文件合计 4.22 GB 只是磁盘大小；CLIPLoader `device=default` 未针对 6GB 显存验证；
   移植后真实 Gate 未执行。不得继续宣传“轻量/快速/批量首选”。→ W3 优先单张低分辨率实测。

8. **`img2img` 默认值口径不一致（已在 W0 对齐）**
   Python `DEFAULT_DENOISE=0.8` 与 binding capabilities `0.55`、workflow `0.55` 不一致；
   W0 已将 binding capabilities 与 workflow 模板统一为 0.8。注意这会改变 `binding_hash`，
   历史 img2img Job 可能无法续跑。→ 后续在版本说明中告知。

## P3 — 环境与生命周期

9. **ComfyUI 启动可能超过载体 420 秒超时**
   2026-10-29/30 观察到冷启动（含 ComfyUI-Manager 网络缓存刷新、节点加载）超过 7 分钟，
   计划任务载体按 `startupTimeoutSeconds=420` 判定失败并回收进程。
   当前临时处理：手动启动 ComfyUI 完成验证；正式修复需评估提高启动超时或预热 Manager 缓存。
   → 运维事项，待 ControlHub/ComfyUI 维护者处理。

10. **`pose_generate` 实验未通过硬件验收**
    2026-10-29 双 LoRA + 双参考图在 6GB/16GB 上出现 OOM/停止推进；
    2026-10-30 已从运行实例与 `main` 下线，代码归档到
    `experiment/pose-generate-20261030`。→ 换更大显存/内存后再评估，不得直接复活到正式主线。

## 处理顺序建议

1. W1：静态检查器（G0 自动化）。
2. W2：运行前依赖/像素/硬件保护。
3. W3：五个正式模块重新验收（basic → img2img → anime → reference → upscale）。
