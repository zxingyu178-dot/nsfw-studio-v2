# RUNTIME_COLD_START_FOLLOWUP — v0.15.0（Task 25）

> 状态：**未执行 / 移交下一阶段**。本文档如实记录原因、应执行的方法与边界，
> 不编造任何启动计时数据。

## 1. 指导要求

本阶段结束前至少记录 3 次计时：

```text
Studio cold start
Studio warm start
Comfy cold start
```

并判断是否存在 `startup time > ControlHub timeout`。若存在，**只能**：

- 在 ControlHub 按现有合同调整 per-service timeout；或
- 明确移交 AIHome 下一阶段。

**禁止在 NSFW 另写绕过 ControlHub 的 launcher。**

## 2. 本次为什么没有执行

发布验收时实测：

- `GET /api/v1/engine/status`、`/api/v1/engine/runtime` 均返回
  `STOPPED / owned=false / host 127.0.0.1 / port 8188`，
  detail 为“ComfyUI 未运行（ControlHub offline）”；
- 端口探测：8188 = 未监听，8080 = 未监听；仅 8000（Studio 后端）、3000 在监听；
- ControlHub 处于 offline，无法取得真实的受管启动链路与计时。

v0.15 的代码边界是**不在 NSFW 内自起第二套生命周期/launcher**（遵循 AIHome 全局规则
§8.1 与本项目“不接 ControlHub 平行设施”的约束）。因此在 ControlHub offline 时，
**不擅自启动长生命周期 GPU 服务**来凑计时数据。

## 3. 下一阶段应执行的方法（不在本次完成）

在 ControlHub 恢复 online 后，对**受管对象**分别计时 3 次（cold / warm / Comfy），
每次记录：

1. 发起启动的时刻（ControlHub 受控调用）；
2. 健康检查首次通过的时刻（Studio `/api/v1/health`；ComfyUI 8188 就绪）；
3. 差值 = 启动耗时；
4. 与 ControlHub 该 service 的 per-service timeout 对比。

判定：

- 若 `p95 启动耗时 <= timeout`：记录“达标”，**不得写“稳定”**，需给具体数值；
- 若存在 `startup time > timeout`：按 ControlHub 现有合同调整该 service 的 timeout，
  或在本文登记为移交项；**不得**在 NSFW 仓库新增 launcher / 守护脚本绕过。

## 4. 移交项

- [ ] ControlHub online 后补做 3 组 cold/warm/Comfy 计时并回填本文件；
- [ ] 若超时，按 ControlHub 合同调整 per-service timeout 并记录调整前后值；
- [ ] NSFW 仓库保持不新增任何自管 launcher / 自管常驻服务（v0.15 未新增 ControlHub 登记对象）。

## 5. v0.15 运行对象登记情况

本版本**未新增长期运行对象**：前端为构建产物，后端改动仅在既有 Studio 后端内
（事件分流/进度字段），无新服务、新端口、新计划任务。故不触发 ControlHub 接入义务。
