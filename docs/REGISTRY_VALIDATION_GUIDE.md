# NSFW Studio V2 — Registry 校验指南（W4.1）

> 工具：`scripts/validate_registry.py`（只读，不修改正式资源）
> 适用：本地开发、CI、Agent 提交包审核。

---

## 1. 用法

```powershell
# 校验正式 Registry（活动 + 历史）
python scripts/validate_registry.py

# 只校验某目录
python scripts/validate_registry.py --registry registry --strict

# 校验 Agent 提交包（草稿允许 unverified Hash）
python scripts/validate_registry.py --submission agent_submissions/sub_xxx

# 输出 JSON（CI / 机器读取）
python scripts/validate_registry.py --json
```

退出码：
- `0`：无 error（warning 可存在）；
- `1`：存在 error，必须修复；
- `2`：参数/路径错误。

---

## 2. 检查项

| # | 检查 | 说明 |
|---|---|---|
| 1 | Schema | `schemas/*.schema.json` 必填字段、类型、枚举、未知字段 |
| 2 | ID 唯一 | `model_id` / `workflow_id` + version 全局唯一 |
| 3 | 版本规则 | `vN` / 语义版本格式；已发布版本不可重复 |
| 4 | 文件存在 | `workflow_file` / `binding_file` 必须存在 |
| 5 | Hash | LF 规范化值必须与 Manifest 一致；legacy raw 值仅记录 |
| 6 | 模型依赖 | `model_id` 必须存在于 Model Registry |
| 7 | 工作流依赖 | 依赖模型状态合法；冻结/归档不能作为活动依赖 |
| 8 | 路径安全 | 禁止绝对路径、`..`、DataRoot 外路径 |
| 9 | 未知字段 | `additionalProperties: false` 的 Schema 直接报错 |
| 10 | 重复注册 | 同一 workflow_id + version 只能有一个 Manifest |
| 11 | 历史覆盖 | 新 Manifest 不得声明为已发布的旧版本 |
| 12 | 测试报告 | `released` 必须有 validation_report；G3/G4 不得写“已通过”而无证据 |

---

## 3. 输出格式

```json
{
  "checked": 40,
  "errors": 0,
  "warnings": 3,
  "issues": [
    {"level": "warning", "code": "LEGACY_BINDING_WITHOUT_PERFORMANCE", "path": "...", "message": "..."}
  ]
}
```

错误码前缀：
- `SCHEMA_*`：结构/字段问题；
- `ID_*`：唯一性/版本冲突；
- `HASH_*`：Hash 不一致；
- `MODEL_*`：模型依赖问题；
- `WORKFLOW_*`：工作流依赖/放行问题；
- `PATH_*`：路径安全问题；
- `SUBMISSION_*`：提交包合同问题。

---

## 4. 常见失败与修复

| 错误 | 原因 | 修复 |
|---|---|---|
| `HASH_WORKFLOW_MISMATCH` | 修改了 workflow.json 但未升版本 | 新建 binding 版本；不要改已发布目录 |
| `MODEL_DEPENDENCY_UNKNOWN` | Manifest 引用了未登记 model_id | 补 model.yaml 或改正 ID |
| `SCHEMA_ADDITIONAL_PROPERTY` | Manifest 有未知字段 | 删除或升级 Schema（需审批） |
| `PATH_ABSOLUTE` | 写了盘符/绝对路径 | 改为项目相对路径 |
| `SUBMISSION_HASH_UNVERIFIED` | released 状态仍写 unverified | 计算真实 SHA256 后再提交 |
| `WORKFLOW_HISTORY_OVERWRITE` | 在原版本目录改文件 | 还原并新建版本 |

---

## 5. CI 与发布前门禁

1. 本地：`python scripts/validate_registry.py --strict`；
2. CI：同命令，error > 0 直接失败；
3. 发布前：人工确认 `release_manifest.yaml` 的 G3/G4 证据与 Manifest 一致；
4. 任何 `default_profile_verified=true` 必须能追溯到 G4 记录。
