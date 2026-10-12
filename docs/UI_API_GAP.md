# UI API Gap 记录

> 范围：`feature/ui-v1-redesign` 对 NSFW Studio V2 前端表现层的重构。
> 契约基线：v0.8.0 / commit `1b8286be831bdc811b79dc064189a2ba87458053`。
> 后端契约来源：FastAPI OpenAPI（应用工厂导出，共 46 个端点）与 `backend/app/schemas`。

## 结论

**No blocking API gaps.**

本次所有页面（生成、图库、提示词、素材、设置）均在不修改任何端点、字段、枚举与状态语义的前提下完成迁移，未出现必须新增或修改后端才能实现的 UI 需求。以下为迁移过程中记录的非阻塞观察，供主开发线评估，UI 侧已用现有端点实现，不阻塞交付。

---

## GAP-001

页面：
Gallery

当前需求：
在图片详情中一次展示“来源图片 / 派生版本”关系。

当前可用 API：
图片详情返回 `parent_id` 及父子关系字段；列表/详情可按图片与任务查询。

缺口：
没有单个“派生版本聚合”端点，前端需按 `parent_id` / 子图集合自行拼装来源与派生链接。

建议：
如未来详情页关系更复杂，可考虑在图片详情响应中附带派生版本摘要（只读聚合，不改数据模型）。

是否阻塞 UI：
否（当前已由前端拼装实现，见 Gallery 详情抽屉的来源 / 派生版本链接）。

---

## GAP-002

页面：
Gallery

当前需求：
多张图片批量保留 / 淘汰 / 收藏。

当前可用 API：
提供单张图片的 review / favorite 更新端点。

缺口：
无批量审图端点，多选操作由前端逐张调用并汇总结果。

建议：
数据量很大且批量操作频繁时，可考虑只读/幂等的批量 review 端点；当前家庭单机规模下无必要。

是否阻塞 UI：
否（多选工具条已实现，逐张提交并以 Toast / 撤销反馈）。

---

## 备注

- 未修改任何 API 返回结构、Job 状态枚举、Pause/Cancel/Resume/Seed 语义及 Image parent/provenance 规则。
- Workflow 与动态参数完全依据 `/modules` 返回的能力与参数 Schema 渲染，未在前端写死 `basic_generate / img2img / upscale` 业务分支。
