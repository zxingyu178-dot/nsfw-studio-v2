"""Mobile Review Bridge 路由包（Phase 0.13）。

仅含审核相关四个子域：system / pairing / images / review。
**禁止** include jobs / engine_runtime / prompts / recipes / assets / cleanup /
modules / desktop SPA——mobile_main 的 route table 守卫测试会断言这些不存在。
"""
