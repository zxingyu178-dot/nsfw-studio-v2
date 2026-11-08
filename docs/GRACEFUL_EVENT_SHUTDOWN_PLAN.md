# Studio事件推送正常退出实施计划

> 按已批准设计实施；逐项完成最小回归、审查与交付，保留生产验证边界。

**目标**：停止Studio时先结束SSE，再排空普通请求，最后执行既有Bridge/Worker清理，避免无限连接阻塞退出。

**设计与技术**：用户2026-11-08明确选择“先正常关闭推送连接”。保留Python/FastAPI/Uvicorn、现有ControlHub任务身份和8000/8877/8188端口。新增现有服务的Uvicorn入口封装，在super.shutdown之前通知EventBroker；不替换信号处理、不新建服务、不增加依赖、不把所有请求改为定时取消。

## 实施顺序

- [x] 先为EventBroker关闭时唤醒空/满队列、重复关闭、关闭后订阅，以及真实SSE结束退订写最小回归，观察旧实现失败。
- [x] 修改backend/app/core/events.py，关闭后不再发布；满队列也必须送达关闭通知。修改backend/app/api/v1/jobs.py，收到内部关闭标记后正常结束响应。
- [x] 新增backend/app/runtime_server.py作为同一Studio服务的启动封装；shutdown先关Broker，再调用Uvicorn原关闭流程。普通请求完成与lifespan顺序用临时回环端口的真实HTTP验证，不连接生产端口、不使用真实数据。
- [x] 运行tests/backend/test_event_shutdown.py及相关既有SSE/Bridge生命周期目标；只重跑失败或受影响项，不重复本地全量。
- [ ] 只读审查、commit/push、PR及主分支CI。补齐现有carrier如何切换到新入口的受管部署方案；确认Registry/ControlHub既有身份和官方接入要求后再落生产，不直接修改历史staging或隐藏改动。
- [ ] 生产验证须先核队列、备份程序/配置/数据库及旧carrier，经官方ControlHub验证停止和启动。必须区分候选源码通过、入口已切换及实际Windows信号退出；没执行的不得称通过。不停启ComfyUI，不操作真实审核/评分/删除。

## 约束与验收

不修改UI、端口、配对、任务/图片数据协议、数据库迁移或ControlHub平台源码。Broker关闭应可重复、使新订阅立即结束、不被满队列阻塞；过期publish回调不能在关闭后恢复事件。普通请求不被该修复取消。若其他长请求或Worker仍超时，独立报告，不能扩大杀进程范围掩盖问题。已有诊断证明SSE机制可复现，尚未证明它是生产当次超时唯一原因。

## 候选验证（2026-11-08）

- 原实现新增3项均失败（缺关闭能力/入口，1.58秒）。实现后 `python -m pytest tests/backend/test_event_shutdown.py tests/backend/test_mobile_runtime.py tests/backend/test_mobile_bridge_lifespan.py` 20通过（31.42秒），1既有Starlette弃用警告。
- 另执行 `python -m pytest tests/backend/test_job_queue.py::test_sse_stream_receives_events`，既有真实HTTP推送1项通过（5.17秒），同一既有警告；分轮验证，不称单轮21项。
- 定向测试替代本地全量；没有Gradle/模拟器/真实媒体操作，没有重启生产。只读审查未发现阻塞项。慢客户端的发送背压、普通长请求仍可能延迟退出，未增加全局取消时限。
- **候选未部署**。已有carrier仍用Uvicorn CLI，只有改为 `python -m app.runtime_server` 才会启用前置关闭；不能只pull源码便宣称生产修复。下一步核定已有carrier的可追溯源/登记与正式接入流程，再做独立Windows信号验证和受管部署。不能声称实际CTRL_BREAK、总退出预算或生产优雅停服通过。
