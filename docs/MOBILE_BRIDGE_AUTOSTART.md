# 手机审核桥随 Studio 启动

2026-11-07，用户已确认推荐方案。基线5153cfe，隔离分支codex/bridge-autostart。只修复已有mobile_review.enabled配置执行，不新增ControlHub对象、端口、daemon或生命周期入口。

## 行为与边界

- 公共模板仍enabled=false；正式配置在验证后按用户选择启用。enabled=true时在Studio生命周期中调度后台启动，健康等待不占用ASGI事件循环、不延迟桌面可用；失败记入既有日志与ERROR状态。
- 保留8877和现有手动start/stop/restart。串行化进程变更，自动与手动同时请求也只能产生一个owned子进程；状态查询不得把冷启动记录清掉。
- 生命周期关闭信号中断健康等待，等待启动线程收口后只停止owned PID；不终止外部健康桥或冲突进程。沿用Bridge父进程存活监测作为兜底，不宣称原来没有孤儿保护。不自动恢复用户手动停止的桥，不增加无限重试。
- ComfyUI、队列、配对、审核与评分语义不变。实际Studio重启仅经ControlHub，并先核对队列空闲、备份程序/配置/数据库；正式发布后启用私有配置，并验证随启动恢复，不能用单次手动start代替。

## 串行实施与验证

1. 复用TestClient/settings与现有runtime seams，先确认enabled=true生命周期不触发启动的RED。覆盖关闭、慢启动不阻塞、失败、退出中断、外部归属；测试无真实进程/端口/DataRoot。
2. MobileReviewRuntimeService添加async startup/shutdown、进程操作锁与可中断等待，main.py只挂接生命周期，资源清理放finally。
3. 运行相关runtime/lifespan与配对路由用例；完整项目门禁交由PR CI，不重复已通过测试来补报告。复核diff/归属安全后push修复分支，CI通过后按develop→main流程合入。
4. 正式部署沿用deploy_app_dist/check_app_dist及ControlHub，核对固定端口、父子归属和配置生效；若官方运行合同需要实质变更则先完成对应登记流程。验证真实健康与已有配对保留，不给真实图片评分或审核。

## 实施验证

- 原代码新生命周期回归：5失败、2通过，失败对应未自动启动和退出未回收。
- 修复后生命周期10项通过（18.33秒）；包括并发启动复用、冷启动期间手动停止/重启、外部桥保护。既有运行时6项及配对鉴权6项也已通过。
- 一轮新增并发测试的3秒兜底计时包含了临时数据库初始化，导致事件提前释放；已改为10秒兜底，并以健康等待仍未释放时桌面可响应作为非阻塞证据，避免把数据库初始化耗时误算成桥启动耗时。
- ControlHub合同核对：继续由既有计划任务身份托管Studio，8877由Studio自行管理，符合合同多组件约定；不修改已审批manifest、target或端口，不另建接入对象。
- 已交付672aa9d（PR35）：Windows完整后端733通过、1跳过、1既有弃用警告；PR/main/develop CI均成功。官方部署及dist一致性检查通过，私有配置已启用；ControlHub实际停启确认自有桥退出、8000/8877释放，再次启动自动恢复且配对记录一致。未停启ComfyUI，手机与家庭Wi-Fi本轮尚未验证。

## 后续诊断缺陷

- 受控spawn失败时start返回ERROR，但下一次status因无响应重算成STOPPED，导致设置页丢失失败状态。修正范围仅为保留无进程、无响应时既有ERROR；显式停止清除错误，再次启动和外部健康桥仍按实际探测更新。测试仅用临时目录与进程/探测替身，不改生产配置。
- 新增回归在原代码1失败（0.42秒）；修复后2026-11-08执行 `python -m pytest tests/backend/test_mobile_runtime.py tests/backend/test_mobile_bridge_lifespan.py` 共17通过（15.13秒），1既有Starlette弃用警告。未重复全量本地回归；本项未部署，正式环境仍672aa9d。
