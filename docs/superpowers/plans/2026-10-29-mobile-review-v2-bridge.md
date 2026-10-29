# Mobile Review v2 审核桥实施计划

2026-10-29，用户已明确授权补齐桥接口；只限8767审核桥、增量图片、详情、审核、提示词版本评分与幂等回执，复用既有鉴权/图库/评分服务。不修改生成工作流或其他在开发中的改动。开发基线94aa003，独立codex/mobile-review-v2。

合同采用MediaReview feature/nsfw-image-review-v2/docs/integration/NSFW_MOBILE_API_CONTRACT_V2.md，与手机实现同步。实现前审查两项持久需求：跨桌面写入的单调revision/REMOVE事件，以及评分/审核幂等记录；不能仅依赖轮询时间或进程内缓存。必要时新增最小迁移，测试升级及旧数据回填。

1. 复用mobile_client和make_mobile_image夹具，新增feed鉴权、分页、增量、桌面变更、tombstone、非法/过期游标回归；先红后绿。
2. 按生成快照及可靠prompt/version关联构建details DTO；未知字段留null，禁止文本匹配猜归属；测试旧图不随编辑变化。
3. image_id审核复用既有语义，favorite-only不改status；expected_updated_at并发守卫与持久幂等同事务；不删除文件。
4. 复用prompt_scoring_service的校验/写入，提供版本summary、图片分页、请求号查询；并发同号不重复历史，换载荷409，所属设备隔离，未知版本仅显式整体评分。
5. 能力/contract仅在全部对应端点通过定向测试后升级；原v1会话与图片读取兼容，路由白名单继续拒绝桌面控制入口。
6. 与手机合并分支定向测试串行执行；构建同证书Alpha23，保留数据覆盖安装；先隔离合成数据，再只读生产联通。部署需通过既有ControlHub，记录备份和迁移，不绕过生命周期。

交付：双方commit/push、精简结果与真实手机证据；未验证项明确列出，不跑全量大套。
