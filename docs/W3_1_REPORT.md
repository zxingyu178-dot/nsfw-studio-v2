# W3.1 完成报告 — Mainline Consolidation

> 基线：`e5ec120a28fb9de559efe246c3e3451eab354f9a`（W3.0 收尾）。
> 参考分支：`codex/mobile-review-v2`（`ca912e6` / `1883b61` / `3fd93ab`），只作功能参考，
> **未 cherry-pick、未 hard reset**；main 是最终代码基线。
> 客户端事实源：MediaReview `1212c30`（`NSFW_MOBILE_API_CONTRACT_V2.md` / `NsfwStudioApi.kt`）。

## 1. Task A：数据库兼容 Gate 0

详细对照与前后计数见 [W3_1_DB_MIGRATION.md](file:///d:/AIHome_2.0_L1_L2/projects/nsfw-studio-v2/docs/W3_1_DB_MIGRATION.md)。

- 部署库当前记录的是参考分支 `0021_mobile_v2_events`，而非 main
  `0021_mobile_event_log_mutations`；两套同名 `mobile_image_events` 列结构不同。
- 部署库副本（只读备份）升级结果：事件 5439 条保 seq、回执 54 条合并、
  已读 24 条保留、设备/图片/Job/Prompt/评分计数不变、images 触发器清零；
  二次执行 0022 无迁移。
- `0021` 改为 callable 守卫；新增 `0022_mobile_v2_compat`（原位扩展、历史图补事件、
  旧回执合并、移除触发器、建立 `mobile_image_seen`）。
- **正式 DataRoot 未执行迁移**；部署时需先备份，再由启动流程应用 0022。

## 2. Task B：客户端合同 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/mobile/images/feed` | opaque 游标分页、UPSERT / REMOVE、`resumed` |
| GET | `/mobile/images/{id}/details` | 生成快照 + EXACT/UNRESOLVED/UNLINKED |
| POST | `/mobile/review/images/{id}/decision` | KEEP/REJECT/RESET + favorite-only + 乐观锁 |
| GET | `/mobile/prompts/{id}/review-summary` | 版本/整体评分、图片计数、seen |
| GET | `/mobile/prompts/{id}/images` | `/mobile/images/...` 缩略图分页 |
| POST | `/mobile/prompts/{id}/evaluations` | 版本或整体评分，原子幂等 |
| GET | `/mobile/prompts/evaluations/{client_request_id}` | 本设备回执查询 |

健康：`api_contract=2`，新增 `mobile_feed_v2`、`mobile_image_details_v2`、
`mobile_image_decision_v2`、`mobile_prompt_review_v2`、`mobile_prompt_evaluation_v2`；
V1 配对/二进制/冻结会话接口保持兼容。

## 3. Task C：业务复用与关键修正

1. **revision** 改为事件 `seq` 十进制字符串：feed / 详情 / snapshot / W3 单图审核统一，
   不再用毫秒时间戳。
2. `expected_updated_at` 保留客户端合同语义；连续写入时 `updated_at` 单调 +1ms。
3. 幂等键使用 `client_request_id`；`operation` 固定为
   `image_decision` / `prompt_evaluation` / `image_review`，不拼接长 UUID。
4. 写事务 `BEGIN IMMEDIATE` 串行化，事务内重新校验设备未吊销。
5. 删除只写 `IMAGE_REMOVED` 事件，不开放手机永久删除。
6. 历史图片由 0022 补首事件，首次空游标同步包含历史图。
7. 业务状态 + 事件 + 回执同一事务；图片创建/导入/审核/收藏/元数据/删除/评分均复用
   `image_event_service` 唯一写入机制；images 触发器已移除，无重复记录。
8. Prompt 关联复用 Job 快照 / V1 导入元数据显式 ID，三态输出，禁止文本匹配。
9. 评分复用 `PromptEvaluation`：支持指定版本或整体；`source=mobile`；不改 Prompt 状态；
   评分 + `PROMPT_EVALUATED` 事件 + 回执原子提交；同设备回执可查、跨设备隔离。
10. Prompt 图片缩略图统一 `/mobile/images/...`，不暴露 Desktop API。

## 4. Task D：端口统一

- `MobileReviewRuntimeService.FIXED_PORT=8877`；冷启动健康等待上限 **120 秒**。
- `configs/config.yaml`、`config.local.yaml.template`、健康日志、停止脚本、验收客户端、
  Settings UI 文案与测试全部改为 8877。
- 不自动换口、不停止非本进程。
- 巡检（执行本次交付时）：

| 端口 | 状态 |
| --- | --- |
| 8877 | OCCUPIED_BY_DEPLOYED_BRIDGE（PID 39184，`app.mobile_main:app --port 8877`，参考分支运行实例；未停止） |
| 18877 | Probe 前 FREE、Probe 后 FREE |
| 8767 | 无监听（旧端口已统一移除） |

隔离 Probe 使用 18877 仅因生产 8877 正被已部署参考分支占用；生产配置仍固定 8877，
未发生自动换口。

## 5. 测试

### 5.1 新增

- `tests/backend/test_mobile_v2_contract.py`（12 tests）：健康能力、feed 首次/分页/更新/删除、
  revision 单调、详情三态、favorite-only、409 权威状态、幂等重放/冲突、并发单事件单回执、
  版本/整体评分、回执设备隔离、错误版本拒绝、图片分组、401/吊销、410。
- `tests/backend/test_mobile_v2_migration.py`（3 tests）：旧分支 0021 升级无丢失、
  主干 0021 历史图回填、旧回执指纹重放/冲突。

### 5.2 回归

- 后端全量 pytest（见 §6）。
- 前端 Settings 相关 3 文件 / 13 tests；全量见 §6。
- G0 静态工作流校验。

## 6. 验收结果

| 项 | 结果 |
| --- | --- |
| 后端全量（本地） | 690 passed / 3 skipped（693 collected） |
| 后端全量（CI） | 690 passed / 3 skipped（164.67s） |
| 前端 Settings 定向 | 3 files / 13 tests passed |
| 前端全量（CI） | 97 files / 489 tests passed |
| 前端 build | 通过（396.29 kB JS） |
| Store regression | 11 passed |
| G0 | checked=6 errors=0 warnings=14 |
| 数据库副本迁移 | 通过，见 Task A |
| 真实 HTTP Probe | PASS，证据 [W3_1_BRIDGE_PROBE.json](file:///d:/AIHome_2.0_L1_L2/projects/nsfw-studio-v2/docs/W3_1_BRIDGE_PROBE.json) |
| 合同一致性 | [W3_1_CONTRACT_CONSISTENCY.md](file:///d:/AIHome_2.0_L1_L2/projects/nsfw-studio-v2/docs/W3_1_CONTRACT_CONSISTENCY.md) |

真实 Probe 覆盖：health 能力、双设备配对、feed 首次同步、details EXACT、favorite-only、
幂等重放、同键异载荷 409、stale 409、更新 revision 前进、summary seen、提示词图片、
版本评分、回执同设备可见/跨设备隐藏、未带 Bearer 401、thumbnail ETag/Cache-Control/nosniff、
桌面删除后 REMOVE tombstone；Probe 端口前后 FREE。

## 7. 未验证 / 限制

- 未连接真实手机 / MediaReview APK；仅按客户端冻结 DTO 与真实 HTTP Probe 验证。
- 正式 DataRoot 未迁移；生产 8877 当前仍由参考分支 Bridge 占用，需在部署窗口切换到 main。
- Snapshot 仍一次性返回全部图片，未分页。
- 事件默认永久保留，无自动裁剪。
- 未启动 ComfyUI / GPU。

## 8. Git / CI / ZIP

| 项 | 值 |
| --- | --- |
| 基线 | `e5ec120a28fb9de559efe246c3e3451eab354f9a` |
| W3.1 提交 | `c066c15d63abd405e77e2c60c28b7d009c70859a` |
| CI run | `41276157845` |
| 后端 | 690 passed / 3 skipped，G0 checked=6 errors=0 warnings=14 |
| 前端 | typecheck + 97 files / 489 tests + build + store regression 11 passed |
| 远端同步 | 本地 HEAD == `origin/main` |

随后仅文档提交，不改变代码；最终 HEAD 的 CI 结果见交付汇报。

验收 ZIP：`handoff/NSFW_Studio_W3.1_Review.zip`（报告、`e5ec120..HEAD` 补丁、
变更清单、git log/status、Probe 证据）。不含 DataRoot、依赖或构建产物。
