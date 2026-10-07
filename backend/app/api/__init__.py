"""HTTP 接口层：只做 HTTP 编排，禁止写业务逻辑。

Phase 0 仅有健康检查；Phase 1 规划路由：
/api/v1/jobs、/api/v1/images、/api/v1/assets、/api/v1/prompts（见 docs/API_PLAN.md）。
"""
