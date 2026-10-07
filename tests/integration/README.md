# tests/integration

前后端联调测试占位。

Phase 0 的集成验证以人工 + 脚本方式执行（见 `docs/PHASE0_REPORT.md` / `TEST_REPORT.md`）：
后端启动 → health API → 前端 dev server → 页面导航与主题切换（浏览器实测）。

Phase 1 计划引入自动化冒烟：脚本拉起前后端 → health 检查 → 首页可访问 → 退出。
