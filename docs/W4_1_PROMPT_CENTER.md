# W4.1 — Prompt Center 统一报告

> 日期：2026-11-04 · 数据源：`studio.db` 只读盘点 + `GET /api/v1/prompts/stats`
> 原则：复用既有 `prompts / prompt_versions / prompt_evaluations`，不重建 Prompt 数据库。

---

## 1. 数据现状

| 项 | 数量 |
|---|---:|
| Prompt | 294 |
| PromptVersion | 294 |
| 无版本 Prompt | 0 |
| 多版本 Prompt | 0 |
| 收藏 | 0 |
| 归档 | 2 |
| 评分记录 | 1 |
| `full` 模式版本 | 293 |
| `structured` 模式版本 | 1 |
| 有图片关联 Prompt | 254 |
| 无图片关联 Prompt | 40 |
| 关联图片总数 | 2,736 |
| 无效关联 | 0 |

## 2. 字段标准与映射

W4.1 标准字段：

`style / character / clothing / action / scene / camera / lighting / extra`

当前数据字段为：

`style / face / clothing / pose / scene / composition / lighting / extra`

只读映射：

| 历史字段 | W4.1 字段 |
|---|---|
| `face` | `character` |
| `pose` | `action` |
| `composition` | `camera` |

- 原始 `structured_json` 不改写；
- 读取投影同时保留原字段与标准字段；
- 98 条带 `_v1_migration` 标记的记录识别为 `legacy_import`；
- 没有历史版本信息的 Prompt（当前 0 条）标记 `legacy_import`，不伪造修改记录。

## 3. 版本管理

- `prompt_versions` 只 INSERT；当前 294 条均为 `version_no=1`；
- 修改内容创建新版本，历史版本永远可读；
- 生成时保存 Prompt ID / Version / 完整正向 / 完整负向 / 最终拼接文本；
- 现有 Job `workbench_snapshot_json.source_prompt_id/source_prompt_version_id` 保留。

## 4. 图片关联

双通道：

1. 新 Job：`job.workbench_snapshot_json.source_prompt_id / source_prompt_version_id`；
2. 旧 V1 导入：`image.metadata_json.v1_output.prompts[]`。

查询入口：

- `GET /api/v1/prompts/{id}/images?limit=&offset=&version_id=&kind=&status=`：全部关联图片分页；
- Prompt 列表卡片仅返回有限预览（默认 3 张），并返回真实总数；
- 前端 `+N` 抽屉按服务端分页加载，不把前三张当全集。

## 5. 标签与评分（W4.1 标准字段）

- `tags`：保存在 `prompt_versions.structured_json.tags`（不新建表/不迁移），
  创建或新增版本时通过 `tags` 字段写入；读取投影同时兼容 `structured.extra.tags`；
- `rating`：取该 Prompt 最新一条 `prompt_evaluations.overall_score`（1–5），无评分为 `null`；
- `GET /api/v1/prompts/{id}/center` 返回统一投影：
  `prompt_id / version / title / category / positive_prompt / negative_prompt /
  structured_fields / tags / favorite / rating / legacy_import / created_at / updated_at`；
- `GET /api/v1/prompts?include_evaluation=true` 的列表项同时返回 `tags` 与 `rating`。

## 6. 性能

- 列表页图片使用 `prompt_ids` 下推的 UNION + 窗口函数批量查询，无 N+1；
- 列表与图片详情分开加载；
- 缩略图走 `cache/thumbnails`，不批量加载原图；
- 分页使用稳定 `created_at desc, id desc` 排序。

## 7. API

| 端点 | 说明 |
|---|---|
| `GET /api/v1/prompts` | 列表（分页、筛选、排序、可选预览；含 tags/rating） |
| `GET /api/v1/prompts/stats` | Prompt Center 统计（W4.1 新增） |
| `GET /api/v1/prompts/{id}/center` | 统一投影（版本/结构化字段/tags/rating） |
| `GET /api/v1/prompts/{id}/images` | 全部关联图片分页 |
| `POST /api/v1/prompts/{id}/versions` | 创建新版本（不可覆盖） |
| `POST /api/v1/prompts/{id}/evaluations` | 评分 |

## 8. 结论

- 全部历史 Prompt 已纳入统一体系；
- 无需新增 Prompt 表或重写现有 Service；
- 40 条无图片 Prompt 保留原样，不强行关联；
- 既有评分/收藏/标签关系无丢失。
