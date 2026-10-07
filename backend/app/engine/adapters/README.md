# engine/adapters/

未来生成引擎适配器的实现目录。

- Phase 0 规范（§十四）要求：本目录**不实现任何具体引擎**，不出现 ComfyUI 地址、节点 ID、模型名或 Workflow JSON。
- Phase 1+ 将在此实现 `ComfyUIAdapter`（实现 `app.engine.base.EngineAdapter` 接口），并通过 `configs/workflow.yaml` 选择启用，不修改核心代码。
