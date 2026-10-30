# workflows/

存放各引擎的 **Provider Binding**（工作流定义 + 参数映射 + 依赖/性能声明）。

Phase 0 的“本目录保持为空”规定已废止（2026-10-30，W0 文档收口）。当前结构：

```text
workflows/providers/comfyui/<module_id>/<binding_version>/
├── workflow.json          # ComfyUI API 格式工作流（必须）
├── binding.yaml           # 节点映射、默认参数、依赖、性能声明（必须）
├── README.md              # 来源、图结构、注入契约、限制（必须）
└── source.workflow.json   # UI 格式来源备份（建议，不参与运行）
```

约束：

- 工作流的**代码接口**在 `backend/app/workflows/`（WorkflowModule）；
- 节点 ID、模型文件名、采样参数只允许出现在 provider binding 层；
- 新工作流必须遵循 [docs/WORKFLOW_SUBMISSION_STANDARD.md](../docs/WORKFLOW_SUBMISSION_STANDARD.md)；
- `basic_generate/v1/` 是唯一单目录特例（版本靠 Git 历史），其它已投入使用 binding 修改必须新建 `v2/`；
- 禁止把模型权重、私人图片/提示词、日志、缓存、机器绝对路径放入本目录。
