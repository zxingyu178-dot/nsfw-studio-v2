# W3.0 完成报告 — Mobile Review Bridge V2

> 基线：`5a9df4a4d7b92b093ea3dadf6e454406c4baae74`（W2.0 Runtime Guard 完成）。
> 前置：MediaReview V2A.2 已通过独立验收。
> 一次完整交付：Migration + Event Log + 增量/快照 API + 图片详情 + 单图审核 + Prompt 版本评分 +
> 幂等回执 + V2 OpenAPI/fixtures + 回归测试 + 文档。
> 未修改 MediaReview 仓库、未改 ComfyUI、未改 W2.0 Runtime Guard、未改单队列、
> 未增加与手机审核无关的 UI、未启动真实 GPU。

## 1. 架构与安全（保持 V1 红线）

- Desktop 8000 始终 loopback；ComfyUI 8188；Bridge 8767 独立进程，随 Studio 退出。
- 手机只访问 8767；不能生成、不能编辑 Prompt、不能永久删除。
- 配对码一次性 + 10 分钟；Bearer 只存 SHA-256；吊销设备立即 401。
- 所有新增接口都经 `get_current_device`；唯一开放端点仍是 health / pairing。
- 图片二进制沿用原 thumbnail / preview / original 缓存与 ETag。

## 2. Task A：Bridge Contract V2

- `GET /mobile/system/health`：`api_contract=2`，新增能力标识
  `image_event_feed / image_detail / image_review / prompt_version_evaluation /
  idempotent_mutation / snapshot_resync`；不包含 `permanent_delete` / `generation` /
  `engine_control` / `prompt_edit`。
- 新增 `docs/integration/MEDIAREVIEW_NSFW_CONTRACT_V2.md`、
  `openapi-mobile-review-v2.json`（由运行中的 FastAPI 路由生成，18 paths）、
  `fixtures/`（health / events / snapshot / image_detail / review / evaluation）。
- V1 端点与契约文件全部保留。

## 3. Task B：Transactional Event Log

- 新增模型 `MobileImageEvent`（`seq` 自增、`event_id` 唯一、`event_type`、`image_id`、
  `revision`、`payload_json`、`created_at`）；**无 images 外键**，图片删除后事件仍可读。
- Migration `0021_mobile_event_log_mutations`。
- 写入点：
  - 引擎输出 / 外部导入：`image_service.import_outputs_transaction` 在 Image 同一事务、
    commit 之前写入 `IMAGE_CREATED` / `IMAGE_IMPORTED`；
  - 桌面审核 / 收藏 / 元数据：`image_service.set_review/set_favorite/set_image_status`
    与状态更新同事务；
  - 手机会话 decision：`image_review_session_service.apply_decision` 复用
    `image_service.apply_review_fields` 并写同一事件；
  - 手机单图审核：同一事务写事件 + 回执；
  - 永久删除：`cleanup_service._purge_image_rows` 在 DELETE 之前写 `IMAGE_REMOVED`；
  - 提示词评分：`prompt_scoring_service.create_evaluation` 写 `PROMPT_EVALUATED`
    （Desktop source=user、Mobile source=mobile）。
- 失败整体 rollback；Event 不与业务写入分离提交。

## 4. Task C：增量同步 + Snapshot

- `GET /mobile/events?cursor=&limit=`：`events / next_cursor / has_more / server_time`；
  `seq` 全局升序、`seq > cursor` 分页，不漏不重。
- 游标：`mr2_` + base64url JSON `{"v":1,"seq":n}`，不直接暴露数据库 seq；
  非法/未来游标、早于最小可用水位 → HTTP 410 `CURSOR_EXPIRED`，
  `details.snapshot_required=true`。
- `GET /mobile/sync/snapshot`：全量图片 + `cursor` 水位 + `server_time`；
  快照与水位同一 DB 读事务，保证与后续增量无空隙。
- 保留策略：V2 默认永久保留、不自动裁剪；若运维裁剪，早于最小水位的游标按 410 处理。

## 5. Task D：图片详情

`GET /mobile/images/{image_id}`：尺寸/时间/revision/status/favorite/kind/source/job_id/seed/
generation module + metadata（module/binding/双 hash/scale/parent/root）/
prompt snapshot / negative / source_prompt_id/version / Prompt 名称与版本号 /
thumbnail/preview/original URL。

- 复用 `image_service.get_provenance()` 与 Job 快照；
- 禁止 DataRoot / DB / workflow 文件路径 / 私有配置；
- 外部导入图片的 Prompt 字段明确为 null，不伪造。
  （注：`generation_metadata` 中的 workflow_hash/binding_hash 为执行指纹，不是文件路径。）

## 6. Task E/F：单图审核 + 幂等

`POST /mobile/images/{image_id}/review`：

- `action`：KEEP / REJECT / RESET；`favorite` true/false；两者独立；
- `expected_revision` 乐观锁；不一致 → 409 `REVIEW_CONFLICT`，
  `details.image` 为权威 Image DTO、`details.revision` 为最新 revision；
- 不允许永久删除；
- 与既有 session decision 复用 `apply_review_fields` 与同一事件写入。

幂等 `MobileMutationReceipt`：

- 唯一约束 `(device_id, operation, idempotency_key)`；
- 相同 Key + 相同 Payload → 原响应 + `idempotent_replay=true`，不重复写事件；
- 相同 Key + 不同 Payload → 409 `IDEMPOTENCY_CONFLICT`；
- 业务状态、事件、回执同一事务提交；并发唯一键冲突时 rollback 后返回既有回执。

## 7. Task G：Prompt 版本评分

`POST /mobile/prompts/{prompt_id}/versions/{version_id}/evaluation`：

- 先校验 version 属于 prompt（否则 404）；
- 复用 `PromptEvaluation`，source=mobile；不改 Prompt keep/candidate/eliminated；
- 评分 + `PROMPT_EVALUATED` 事件 + 回执同一事务；支持重放；
- `GET .../evaluations` 查询该版本评分。

## 8. 测试

`tests/backend/test_mobile_review_v2.py`（14 tests）：

1. 生成图片 → IMAGE_CREATED；
2. 外部导入 → IMAGE_IMPORTED；
3. 桌面审核/收藏/元数据事件独立；
4. 手机审核/收藏事件独立；
5. 删除后 IMAGE_REMOVED 仍可读（图片行已删除）；
6. 多事件游标分页顺序、不漏不重；
7. 非法/未来游标 → 410 CURSOR_EXPIRED + snapshot_required；
8. Snapshot 水位与增量无空隙；
9. 详情关联 Prompt/版本/名字/模块，无 file_path；
10. 导入图不伪造 Prompt；
11. 409 REVIEW_CONFLICT 返回权威图片与最新 revision；
12. 相同幂等 Key 重放成功且不重复事件；
13. 相同 Key 不同 Payload → 409 IDEMPOTENCY_CONFLICT；
14. 评分关联正确版本、事件/回执原子、重放不重复；未配对/吊销设备 401。

既有 V1 回归：`test_mobile_*`、`test_prompt_scoring`、`test_cleanup_rejected`、
`test_image_service` 全部通过（定向合计 74 passed）。

## 9. 测试结果

| 项 | 结果 |
| --- | --- |
| 后端定向（本地：mobile v2 + session/cleanup/image/scoring/migration） | 74 passed |
| 后端全量（CI） | 674 passed / 3 skipped（166.58s） |
| 前端 typecheck | 通过 |
| 前端 vitest | 97 files / 489 tests passed |
| 前端 build | 通过（396.29 kB JS） |
| Store regression | 11 passed |
| G0（CI step） | checked=6 errors=0 warnings=14 |

测试全部使用 SQLite 隔离 DataRoot，未依赖真实 GPU / ComfyUI。

## 10. Git / CI

| 项 | 值 |
| --- | --- |
| 基线 | `5a9df4a4d7b92b093ea3dadf6e454406c4baae74` |
| W3.0 提交 | `62eb37718482406a7931f0879748c1453a95e4ea` |
| CI run | `41267919495` |
| 后端 | 674 passed / 3 skipped，G0 通过 |
| 前端 | typecheck + 97 files / 489 tests + build + store regression 11 passed |
| 远端同步 | 本地 HEAD == `origin/main` |

随后仅文档提交，不改变代码；最终 HEAD 的 CI 结果见交付汇报。

## 11. 验收 ZIP

`handoff/NSFW_Studio_W3.0_Review.zip`：W3.0 报告、`5a9df4a..HEAD` 变更补丁、
变更文件清单、git log / status。仅文档与审查用途，不含 DataRoot、依赖或构建产物。

## 12. 未验证 / 限制

- 未在真实手机 / MediaReview 客户端联调；仅 Bridge 契约 + SQLite 隔离测试。
- 并发测试以“唯一回执 + rollback 回查”实现，未做真实多线程压力测试；
  唯一约束保证不会重复事件/重复回执。
- Snapshot 当前返回全部图片，未做分页；大批量库需在后续阶段评估。
- 事件默认永久保留；自动裁剪策略未实现（避免静默丢弃客户端可能使用的游标）。
