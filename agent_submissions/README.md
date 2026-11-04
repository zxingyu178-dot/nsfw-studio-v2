# AI Agent 提交区（W4.1）

本目录是 AI Agent 提交模型、工作流、Prompt 模板、图片处理能力的**唯一 staging 区**。
提交包不会被自动发布；必须通过 `scripts/validate_registry.py` 与人工审批后才进入
`registry/` 与 `workflows/`。

## 目录

```text
agent_submissions/
├── templates/     # 四类提交模板
├── <submission_id>/
│   ├── submission.yaml
│   ├── manifest.yaml
│   ├── assets/    # 仅小型样例/测试图，禁止模型权重
│   ├── tests/
│   ├── README.md
│   └── CHANGELOG.md
```

## 规则

1. 提交前先读 `docs/AGENT_SUBMISSION_STANDARD.md`；
2. `submission_id` 唯一，格式 `sub_<resource>_<change>`；
3. 草稿允许 `sha256: unverified`，发布前必须替换为真实 Hash；
4. 禁止提交模型二进制、完整生成图片、DataRoot、日志、凭据；
5. 禁止覆盖 `registry/` 中已发布的版本；
6. 提交包必须包含回滚说明与测试方法。

## 校验

```powershell
python scripts/validate_registry.py --submission agent_submissions/<submission_id>
```
