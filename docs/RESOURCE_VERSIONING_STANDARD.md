# NSFW Studio V2 — 资源版本标准（W4.1）

> 目标：模型、工作流、Binding、Prompt、Schema 的版本演进有明确规则；已发布版本不可覆盖。

---

## 1. 版本类型

| 类型 | 字段 | 规则 |
|---|---|---|
| Model Version | `model.version` | 语义版本 `MAJOR.MINOR.PATCH`；换权重/结构 = 新版本 |
| Workflow Version | `workflow.version` | `vN`；与目录名、`binding.yaml.binding_version` 一致 |
| Binding Version | `binding.version` | 同 Workflow Version；执行身份 = 目录 + 双 Hash |
| Prompt Version | `prompt_version.version_no` | 从 1 递增；只 INSERT，不 UPDATE |
| Schema Version | `schema_version` | 当前 `1.0`；Schema 结构变化必须升版 |

`module_version`（Python 模块接口版本）与 `binding_version`（执行绑定版本）是**两个独立域**，禁止互相兜底。

---

## 2. 什么时候升版本

| 变更 | 动作 |
|---|---|
| 换模型 / 换 VAE / 换 LoRA | 新 binding 版本（新目录） |
| 改节点图 / 注入位置 / 默认采样 | 新 binding 版本 |
| 只改 Prompt 文本/结构化字段 | 新 PromptVersion（Prompt 本身 ID 不变） |
| 只改显示名称/收藏/归档 | 不建新版本 |
| 新增用户参数 | 更新 Module 契约 + 新 binding |
| 换输入角色/输出语义 | 新 Module（不得复用旧 module_id） |
| Schema 增加必填字段 | Schema 升版 + 迁移说明 |

---

## 3. 不可变规则

1. 已发布 `binding.yaml` / `workflow.json` 不可原地修改；修改 = 新版本目录；
2. 已发布模型版本不可覆盖；新文件 = 新 `version`；
3. `prompt_versions` 只 INSERT；恢复旧版本 = 复制为新版本；
4. 历史 Job 的 `workflow_hash` / `binding_hash` 不改写；
5. `release_manifest.yaml` 的历史证据不删除，追加新证据；
6. 旧版本 G3/G4 结果不得标记为新版本证据。

---

## 4. Hash 与换行

| 算法 | 标识 | 规则 |
|---|---|---|
| 原始字节 | `raw-bytes-v1` | 历史 Job / 历史 Binding 验证 |
| LF 规范化 | `lf-normalized-v1` | W4.1 起 Manifest 与新 Job 标准 |

- `.gitattributes` 固定 JSON/YAML 为 LF；
- 不 renormalize 已发布 Binding；
- Manifest 同时记录 `lf` 值与 `legacy_raw_*` 观测值；
- `load_binding` 接受 raw 或 LF，不匹配才拒绝。

---

## 5. 版本冲突处理

| 情况 | 处理 |
|---|---|
| 目录已存在同版本 | 拒绝；只能新建版本或提交变更说明 |
| Hash 与 Manifest 不一致 | 拒绝发布；先修正文件或 Manifest |
| 依赖模型版本缺失 | 拒绝；补登记或改为可选依赖 |
| 历史版本被引用 | 保留；标记 `frozen`，不删除 |
| 重复 ID | 拒绝；ID 全局唯一 |
| 两个 Manifest 定义同一 ID/版本 | 拒绝；只允许一个真源 |

---

## 6. Manifest 生命周期

```text
draft（本地/提交包）
  → staged（agent_submissions）
  → validated（Validator 通过）
  → approved（人工审批）
  → released（registry/ 正式定义 + release_manifest 证据）
  → frozen（不再新任务，仅历史）
  → archived（下线，文件归档，登记保留）
```

状态只能向前；回退必须记录原因与审批。
