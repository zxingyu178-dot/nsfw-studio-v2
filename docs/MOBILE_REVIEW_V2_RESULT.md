# Mobile Review v2 交付记录（进行中）

用户已授权审核桥接口及固定端口8877。旧8767处于Windows保留范围8767–8866；不停止虚拟化网络、不自动换口。现有Studio仍由ControlHub管理，8877为其受管子运行时，不新增独立daemon。

已实现：持久事件增量、快照详情、按图片审核及收藏、精确提示词版本统计/图组/评分、设备隔离幂等回执。0021迁移为增量事件、回执、已看证据建立持久记录，触发器兼容桌面写入。评分服务保持旧调用默认commit，桥在单一事务中flush后写回执。

验证：核心36项、兼容22项、迁移/health2项、端口runtime5项分轮通过；手机分支整合164项JVM通过。原评分迁移断言失败已修复为按ID选择旧基线；不宣称全量单轮通过。手机最终端口修改后仍需编译/安装和实际联调。

部署：已一致备份生产SQLite109522944字节且quick_check=ok，程序94aa003也已归档。默认DataRoot/backups写入被拒，实际备份在MediaReview的gitignored review_meta/nsfw-integration-20261029/private-backups，未修改ACL。已将ca912e6部署为app分支29d3fef，0021启动迁移成功，但8767绑定被系统拒绝；正按授权改8877。未做真实图片审核决定或评分写入。

回滚：先经Studio受管入口停止Bridge；保留当前库，核对新增评分/审核后再决定恢复配套数据库及程序。不能用旧快照直接覆盖后续用户生成或评分。程序源变更只在codex/mobile-review-v2，原main的pose_generate并行改动保留。
