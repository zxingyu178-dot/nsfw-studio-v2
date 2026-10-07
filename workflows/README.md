# workflows/

未来存放**工作流定义文件**（如各引擎的 Workflow JSON、模块参数模板）。

Phase 0 规范要求：

- 本目录保持为空，**不放入任何具体引擎的工作流**（不写 ComfyUI Workflow JSON）；
- 工作流的**代码接口**在 `backend/app/workflows/`（WorkflowModule）；
- 文件命名约定（Phase 1+ 再定稿）：`<module-name>/<module-name>-v<version>.json`。
