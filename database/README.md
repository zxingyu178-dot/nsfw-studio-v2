# database/

数据库设计与迁移说明目录（文档性质）。

- **运行期数据库不在本目录**：SQLite 运行库位于 DataRoot（默认 `D:/NSFW-Studio-Data/database/studio.db`）。
- **迁移定义**（单一事实源）在 `backend/app/database/migrations.py`，按 `migration_id` 升序执行，执行记录写入 `migration` 表。
- 当前 schema、Phase 1 规划与 Alembic 升级路线见 [docs/DATABASE_PLAN.md](../docs/DATABASE_PLAN.md)。
