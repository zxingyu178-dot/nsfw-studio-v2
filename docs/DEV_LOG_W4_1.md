# W4.1 — 统一资源与资产管理体系（执行记录）

> 日期：2026-11-04 · 基线 `9904e12` · 项目 `nsfw-studio-v2`
> 本文件记录实际执行过的步骤、命令与结果；未执行项明确标注“未执行”。

---

## 1. 执行时间线

| 阶段 | 动作 | 结果 |
|---|---|---|
| Gate 0 | 只读盘点数据库/模型/工作流/图片/Prompt/Job | 五份文档 + 18,346 行文件清单 CSV |
| Gate 0 | SQLite backup API 备份 | `backups/studio-20261104-103427.db` |
| Gate 0 | DataRoot 全量副本 | `D:\NSFW-Studio-Data-Backup-20261104`（20,992 文件 / 14.487 GB，0 失败） |
| Gate 1 | 建立 5 个 JSON Schema、30 个模型 Manifest、10 个工作流 Manifest | Validator `checked=40 errors=0 warnings=7` |
| Gate 1 | Agent 提交标准/版本标准/校验指南/四类模板 | 已写入 `docs/`、`agent_submissions/templates/` |
| 实现 | LF/CRLF 双 Hash + `.gitattributes` | 新 Job 用 `lf-normalized-v1`，历史 raw 值继续可验证 |
| 实现 | 0023 `mobile_image_events` 修复 | 旧库/当前库/W4.0 快照副本演练通过；当前库安全跳过 |
| 实现 | AssetIngest / Storage / AssetQuery / PromptCenter / Provenance / Registry API | 已落地 |
| 迁移 | 停止 Studio / ComfyUI / Bridge | 8000 / 8188 / 8877 全部 FREE |
| 迁移 | 迁移前数据库快照 | `backups/studio-20261104-125925.db` |
| 迁移 | 图片资产正式迁移 | 7,733 图 + 10,613 变体；0 缺失 / 0 Hash 不一致 / 0 孤立 |
| 迁移 | 全量校验 | 计数完全一致；全部图片有 SHA256；父子关系 32 条不变 |
| 测试 | 前端 build + 488 vitest | 通过 |
| 测试 | 受影响后端定向测试 | 通过 |
| 测试 | 后端全量 pytest | 697 collected；1 个 SSE 启动超时（单测复跑通过）、1 skipped |
| 部署 | Commit `645649d` + Push + app 树 pull | 完成 |
| 部署 | 新代码启动，正式库应用 0023 | `latest_migration=0023_mobile_event_legacy_repair` |
| 验收 | 四模块 Preflight | 全部 READY |
| 验收 | G3 四工作流真实出图 | 4/4 COMPLETED |
| 验收 | G4 冷/热 + GPU/RAM 峰值 | 8 个冷/热 Job + 4 个峰值 Job，全部 COMPLETED，0 OOM |
| 验收 | 手机端 | mobile 合同测试通过；Bridge 运行态 `api_contract=2` |
| CI | GitHub Actions | `41789128325` @ `645649d` success |
| 交付 | G4 放行清单 / 报告 / ZIP | 放行清单与报告已更新；ZIP 待打包 |

---

## 2. 关键命令

```powershell
# Registry 校验
.venv\Scripts\python.exe scripts\validate_registry.py

# 图片迁移 dry-run
.venv\Scripts\python.exe scripts\migrate_assets_w41.py --dry-run

# 图片迁移正式执行（服务停止后）
C:\Espressif\tools\python\python.exe scripts\migrate_assets_w41.py --apply --report temp\w41_migration_report.json

# 迁移验证
C:\Espressif\tools\python\python.exe temp\w41_verify_migration.py

# 后端测试
.venv\Scripts\python.exe -m pytest -q

# 前端
npm run build
npm run test:ci
```

---

## 3. 未执行 / 限制

1. 后端全量 pytest 尚未结束，本文件不声称全绿。
2. G3/G4 尚未开始；未产生新的四工作流出图证据。
3. 0023 尚未在正式库启动时写入 `migration` 记录（当前库结构已主干，启动会安全跳过）。
4. 旧 `images/*` 目录未归档、未删除。
5. GitHub CI、Commit SHA、验收 ZIP 未生成。
