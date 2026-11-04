# NSFW Studio V2 — AI Agent 统一提交标准（W4.1）

> 适用范围：任何 AI Agent / 自动化脚本提交 **模型、工作流、Prompt 模板、图片处理能力**。
> 本文件是 W4.1 之后的唯一提交合同。未按本文件提交的资源，Validator 一律拒绝注册。
> 关联：`RESOURCE_VERSIONING_STANDARD.md`、`REGISTRY_VALIDATION_GUIDE.md`、`W4_1_ARCHITECTURE.md`。

---

## 1. 基本原则

1. Agent 只能**准备提交包**，不能直接修改正式活动资源；
2. 正式资源发布后不可覆盖；
3. 所有资源必须有唯一 ID、版本、文件 Hash、依赖与回滚说明；
4. 禁止以文件名、显示名、图片路径推断资源身份；
5. 模型二进制、图片、DataRoot、日志、凭据不得进入 Git；
6. 提交不等于发布：必须经过 `Staging → Schema → Dependency → Static → Runtime/G3 → 人工审批 → Release`。

---

## 2. 提交目录

```text
agent_submissions/
└── <submission_id>/
    ├── submission.yaml      # 外层合同（submission.schema.json）
    ├── manifest.yaml        # 资源定义（model / workflow / prompt / asset）
    ├── assets/              # 仅允许必要的小型样例/测试图；禁止模型权重
    ├── tests/               # 可执行测试或测试说明
    ├── README.md            # 目的、影响范围、使用方式
    └── CHANGELOG.md         # 与原版本的差异
```

`submission_id` 形如 `sub_basic_generate_v2_refresh`，必须唯一。
模板位于 `agent_submissions/templates/`。

---

## 3. 提交内容（缺一不可）

| 字段 | 说明 |
|---|---|
| 提交类型 | `model` / `workflow` / `prompt` / `asset_import` |
| 资源 ID | `model_id` / `workflow_id` / `prompt_id` / `asset_id` |
| 版本 | 模型语义版本 / binding `vN` / Prompt 整数版本 / Asset 无版本 |
| 变更原因 | 为什么需要新版本；不得为空 |
| 依赖资源 | 模型、工作流、节点、ComfyUI 版本 |
| 文件清单 | 每个文件的路径、大小、SHA256 |
| 输入输出 | 结构化 schema / 槽位 / 输出 kind |
| 兼容性 | 与历史 Job、历史 Binding、手机端的关系 |
| 测试方法 | 命令、G3/G4 证据、预期结果 |
| 回滚方式 | 如何回到上一版本；不得依赖删除历史 |
| 状态 | `draft` / `staged` / `validated` / `approved` / `released` / `rejected` |

---

## 4. 自动验收（Validator）

`scripts/validate_registry.py` 执行以下检查：

1. Manifest 是否符合对应 JSON Schema；
2. ID 是否唯一（跨活动 + 历史 + 提交包）；
3. 版本规则是否正确（已发布版本不可重复/覆盖）；
4. 文件是否存在（路径相对项目根，禁止绝对路径）；
5. SHA256 是否与声明一致（`unverified` 只允许在 draft/staged）；
6. 模型依赖是否存在且状态合法；
7. 工作流依赖是否完整（workflow_id/model_id/节点版本）；
8. 路径是否穿越、是否指向 DataRoot 外；
9. 是否存在未知字段；
10. 是否重复注册；
11. 是否覆盖历史版本；
12. 是否附带测试证据（G0/G1/G3/G4 或明确“未执行”）。

**任何一项失败 → 拒绝注册，不允许“先合入后补”。**

---

## 5. 发布流程

```text
AI Agent 提交包
   ↓
Submission Staging（agent_submissions/<submission_id>）
   ↓
Schema Validation
   ↓
Dependency Validation
   ↓
Static Validation（Hash / 路径 / 版本）
   ↓
Runtime / G3 Test（真实 Studio 队列）
   ↓
人工审批
   ↓
正式 Release（registry/ + workflows/）
   ↓
Registry 更新（release_manifest.yaml / Registry Service）
```

- `draft` / `staged` 允许 `sha256: unverified`；
- `released` 必须全部为真实 SHA256；
- G3/G4 必须由本机真实运行产生，禁止 Mock、禁止旧证据复用；
- `default_profile_verified=true` 只能在 G4 证据齐全后设置。

---

## 6. 禁止事项

- 新增模型/工作流未经批准；
- 重新引入 4x 放大或 SeedVR2；
- 覆盖历史 Binding 或改写历史 Job；
- 直接把正式 DataRoot 文件移动/删除；
- 把模型权重、完整生成图片、凭据写入提交包；
- 让前端直接拼接模型文件名/工作流路径；
- 用旧版本 G3/G4 结果冒充新版本证据。

---

## 7. 示例

参考：

- `agent_submissions/templates/MODEL_SUBMISSION_TEMPLATE.yaml`
- `agent_submissions/templates/WORKFLOW_SUBMISSION_TEMPLATE.yaml`
- `agent_submissions/templates/PROMPT_SUBMISSION_TEMPLATE.yaml`
- `agent_submissions/templates/ASSET_IMPORT_TEMPLATE.yaml`

实际提交包必须把 `submission.yaml` 与对应 `manifest.yaml` 同时放入同一目录。
