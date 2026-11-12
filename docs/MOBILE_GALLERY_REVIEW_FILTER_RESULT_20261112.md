# 手机图库审核状态筛选补齐

日期：2026-11-12。分支：`codex/mobile-gallery-date-query`。

## 变更

- 手机图库继续使用单值 `status`，新增 `NOT_REJECTED`，只排除 `REJECT`，保留 `NEW`、`KEEP`、`ARCHIVED`；现有状态行为保持。
- 手机桥图库路由允许新值，health声明 `mobile_gallery_review_filter_v1`。
- 沿用现有query中的filters绑定游标，响应filters完整回显status；page/scope游标不得跨审核条件复用。
- 仅修改手机图库service、桥路由、能力声明和定向测试；保留既有dirty电脑前端及文档修改。

## RED / GREEN 实际证据

使用项目主目录既有 `.venv/Scripts/python.exe`，进程级PYTHONPATH指向当前worktree的backend，TEMP/TMP指向当前worktree/temp。测试夹具使用隔离DataRoot，并有禁止访问真实8000/8188/8877端口的hermetic护栏。

修复前执行：

```text
python -m pytest tests/backend/test_mobile_gallery.py::test_gallery_not_rejected_pagination_and_review_change -q --basetemp temp/mobile-not-rejected-red
```

实际1失败：GET /mobile/images/gallery?status=NOT_REJECTED 返回422，尚未得到图库结果。

修复后执行：

```text
python -m pytest tests/backend/test_mobile_gallery.py::test_gallery_not_rejected_pagination_and_review_change tests/backend/test_mobile_gallery.py::test_gallery_existing_single_review_status -q --tb=short --basetemp temp/mobile-not-rejected-green
```

实际4通过：1个新增组合用例与3个单值参数用例。覆盖total、分页、NEW/KEEP/ARCHIVED保留、REJECT排除、filters回显、page/scope跨条件拒绝、审核改REJECT后旧游标查询排除及更新total、health能力，以及NEW/KEEP/REJECT原单值行为。

定向 `git diff --check` 通过。既有Starlette/httpx弃用警告保留，未扩大处理。

## 边界

未运行前端或全套测试，未使用真实数据，未启动服务、部署、合并或commit/push。本次证据不代表手机或日用实例已支持新筛选。pytest输出仅工具回执，未另存原始日志。隔离测试临时目录保留在worktree/temp。
