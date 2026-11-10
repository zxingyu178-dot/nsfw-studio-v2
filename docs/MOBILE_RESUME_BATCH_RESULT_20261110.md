# 手机续审与批量接口：源码阶段记录

2026-11-10。只收口既有在研后端，未部署、未修改真实媒体/审核/评分数据，未改依赖、数据库结构、工作流或服务入口。手机界面与双端组合验收仍未完成。

## 双向图库

现有gallery新增previous_page_cursor、0起始start_index，total仍为原scope当前存活总数；反向keyset返回最近前页，最终保持原排序。前/后页都带正确两向游标，scope剥离direction保持旧格式；查询条件/水位/上限继续绑定。新增mobile_gallery_bidirectional_v1能力，旧正向客户端不必更新请求。

本轮主Agent运行`python -m pytest tests/backend/test_mobile_gallery.py -q`：8通过2失败。两失败精确复现为隔离样本直接delete(Image)违反image_variants外键；仅修改测试，复用正式cleanup_service._purge_image_rows的关联清理与REMOVE事件，不放宽数据库约束。随后`-m pytest tests/backend/test_mobile_gallery.py -k deletion_and_empty --tb=short -q`：2通过。按8+2分轮记录，不称单轮10绿。包含正反序/同时间戳、前后首尾、scope/新图隔离、删除后计数和空页、非法方向拒绝、旧日期/快照回归。

## 整页混合审核

- POST /mobile/images/batch-review，Header Idempotency-Key（1..128），body.items为1..10个不同image_id/action(KEEP或REJECT)/expected_revision。
- 全页必须仍为NEW且revision匹配，先全检再修改；atomic_write持SQLite写锁并复核设备，图片状态、事件、回执同事务。保留favorite，淘汰只改状态，不删文件。
- 返回items（image_id/status/revision）、kept_count、rejected_count；GET /mobile/images/batch-review/{request_id}/result只允许当前设备查自己的冻结回执，其他设备404。相同号相同载荷重放原结果，不同载荷409。
- 能力mobile_image_batch_review_v1。该接口不推导未提交图片的审核结果，手机必须冻结实际可见/成功加载的提交集合。

子任务使用现有venv、正确PYTHONPATH=backend及项目可写TEMP/TMP，在既有tests/backend/test_mobile_v2_contract.py补最小8用例。

`-m pytest tests/backend/test_mobile_v2_contract.py -k batch_review --tb=short -q`：实现前8项405失败；实现后7通过、1测试误取V2详情is_favorite字段失败。测试改直接断言隔离DB favorite保留，生产实现不改，仅复跑`-m pytest tests/backend/test_mobile_v2_contract.py::test_batch_review_mixed_atomic_receipt_and_device_scope --tb=short -q`，1通过。覆盖混合成功、重复事件不新增、载荷冲突、跨设备、revision/已审/未知ID/重复ID/空/超限拒绝及第二项事件异常全回滚。结果为7+1分轮通过，不称单轮8绿。

## 交付边界

### 追加：图库筛选底座（未部署）

`GET /mobile/images/gallery`新增可选prompt_id/version_id/status/category/favorite，默认None（不筛选）；status读取NEW/KEEP/REJECT/ARCHIVED及历史FAVORITE，category为anime/imported，favorite独立布尔（False保留）。version_id无prompt_id返回422；提示词/版本存在性及归属复用mobile_v2_service._images_query，分类、状态和收藏复用桌面image_service._apply_image_filters，不猜测版本。新增mobile_gallery_filters_v1。响应filters仅回显非None值，无筛选为{}；仅非空筛选才把filters追加到游标q，旧无筛选q仍为[sort,from_utc,before_utc]，旧scope字节保持。前/后游标、anchor、total/start均沿用同一筛选与原水位快照，状态改变可缩小存活范围，不引入offset。

既有test_mobile_gallery.py新增2用例：同提示词两个版本排他、NEW审核后移出但后页不漏；动漫/导入/收藏筛选与False回显；条件跨游标拒绝、无prompt版本拒绝、未知提示词/版本404、旧scope兼容及能力声明。首轮先修正新增fixture误取add_prompt_version二元返回值，随后2项RED均实际复现旧接口忽略筛选；实现后`python -m pytest tests/backend/test_mobile_gallery.py -q --tb=short`单轮12项通过。日志在忽略的temp/mobile-gallery-filters-red-20261110.log、mobile-gallery-filters-red-corrected-20261110.log、mobile-gallery-filters-green-20261110.log。环境为既有canonical venv、当前工作树PYTHONPATH=backend与可写项目TEMP/TMP；diff检查通过，既有Starlette弃用警告保留。未全量/部署/手机验收，无依赖/数据库/工作流修改。**搜索q、标签编辑、完整库管理及两端真实组合验证仍未完成**；不据本轮筛选称计划D全部完成。

追加V2详情合同补漏：手机刷新调用`GET /mobile/images/{image_id}/details`，其`mobile_v2_service.details`原未返回status，不能借另一legacy详情端点已有status假定此链路完整。增强既有`test_decision_favorite_only_preserves_status_and_conflict`的NEW/KEEP断言，以及`test_batch_review_mixed_atomic_receipt_and_device_scope`的KEEP/REJECT刷新断言；修复前2项均因缺status而失败。仅在该DTO加入`status=image.status`，同2项复验通过；没有改变状态写入、审核事件、回执或迁移。命令为既有venv、工作树根目录、进程级PYTHONPATH=backend及可写TEMP/TMP：`python -m pytest tests/backend/test_mobile_v2_contract.py::test_decision_favorite_only_preserves_status_and_conflict tests/backend/test_mobile_v2_contract.py::test_batch_review_mixed_atomic_receipt_and_device_scope -q --tb=short`。日志为忽略的temp/mobile-details-status-red-20261110.log与mobile-details-status-green-20261110.log；既有Starlette弃用警告保留，未全量、未部署、未做手机验收。

主Agent检查生产diff、事务封装与定向输出，git diff --check通过；日志在忽略temp目录，既有Starlette弃用警告保留。没有新长期运行对象或脚本。尚未验证：手机前页合并及序号、9图界面、断网未知结果恢复、同提示词6/10图与评分、完整桌面到手机事件投影、实际部署。不能据接口用例称双端统一已全部完成。

## 分类增量摘要补齐

图库与feed的summary新增categories集合，复用桌面image_service._apply_image_filters，anime/imported可重叠，每页最多2次分类查询。普通生成返回空集合；旧桥不返回字段时客户端必须保留未知，不得当成空集合。没有改数据库、分类规则、工作流或部署实例。

新增gallery/feed两个参数化用例覆盖普通生成、动漫模块、普通导入、文件名/metadata的Anima导入；最初2项均因缺categories出现KeyError。补实现后 `python -m pytest tests/backend/test_mobile_gallery.py -q` 14项通过（exit0），既有httpx弃用warning保留。日志在忽略temp/mobile-categories-{red,green}-20261110.log。本结果不覆盖Android或真实手机，新源码仍需后续统一候选部署。

## 手机图库搜索与当前版本文字标签（2026-11-10）

GET gallery新增可选search（最长200）/tag（最长100），trim后空值归None，不改变旧空scope三元组；非空写入filters回显与游标范围，变更条件后复用scope拒绝422。能力为mobile_gallery_search_v1。

搜索使用SQL字面子串，%/_不作通配：导入文件名、Job正负提示词快照，以及通过既有Job/V1导入显式ID关联的Prompt名称与任意版本正负正文。标签复用Prompt当前版本structured_json的tags列表，非列表回退extra.tags；仅精确匹配strip后的文字标签，不新增标签库/选项API。历史非字符串标签不扩展支持；无效JSON按无标签处理，不报500。所有过滤在SQL分页/计数之前执行，不逐图查询或全表Python扫描。

新增综合回归先证明旧API忽略条件而返回错误图片；实现后test_mobile_gallery.py整文件15通过。随后review新增坏JSON回归出现sqlite malformed JSON，json_valid保护与type=text约束后仅该单例1通过；是15+1分轮证据，不称最终16单轮全绿。日志temp/mobile-search-{red,green}-20261110.log与mobile-search-badjson-{red,green}-20261110.log。未跑全量、未部署、未读写真实媒体/评分，无迁移/依赖/生命周期改动。
