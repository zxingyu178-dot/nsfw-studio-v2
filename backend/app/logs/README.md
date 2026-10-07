# backend/app/logs/

**运行日志默认不在这里。** 日志统一写入 DataRoot（默认 `D:/NSFW-Studio-Data/logs/{app,jobs,errors}`，JSON 格式）。

本目录仅作兜底占位：仅当 DataRoot 不可用导致日志初始化失败时，才考虑降级使用（Phase 0 未启用该降级路径）。此目录中的 `*.log` 已被 gitignore。
