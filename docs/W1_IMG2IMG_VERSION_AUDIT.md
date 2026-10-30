# W1-0：img2img 版本与历史 Job 兼容性审计

> 日期：2026-10-30。审计方式：**只读** SQLite（`file:...?mode=ro` + `PRAGMA query_only=ON`），
> 未修改数据库、未重建/清理任何 Job。

## 1. 数据库与范围

- 数据库：`D:/NSFW-Studio-Data/database/studio.db`
- 表：`jobs`、`job_stages`
- 条件：`job_stages.module_id = 'img2img'`
- 结果：**13 个 img2img Stage**；Job 状态全部为 COMPLETED / FAILED，**没有 QUEUED / RUNNING / PAUSED / RECOVERABLE 的 img2img 任务**。

## 2. 实测指纹

| workflow_hash | binding_hash | binding_version | Stage 数 |
| --- | --- | --- | --- |
| `92132d53229d9bea` | `ca978ab11e07ca4a` | v1 | 1 |
| `7c11569529d4e653` | `2f2d5c06055c623a` | v1 | 12 |

W0 修改后的实际工作区指纹（从被修改文件字节计算）：

| 文件 | W0 新指纹 |
| --- | --- |
| `img2img/v1/workflow.json` | `9c7d1a1f1113391d` |
| `img2img/v1/binding.yaml` | `2d8bae7af79c8bd3` |

**数据库中没有任何 Stage 使用 W0 新指纹**（0 条）。

## 3. 解释与风险

- `7c1156…/2f2d5…` 是 94aa003 原始 v1 在 Windows 工作区（CRLF）下的实际字节哈希，
  与恢复后的 v1 完全一致；12 个历史 Job 可继续按 v1 身份恢复。
- `92132d…/ca978…` 是同一份 94aa003 的 LF 字节变体，只有 1 个更早 Job 使用；
  该 Job 在 W1 之前就已无法与当前工作区字节匹配，不属于本次 W0 回归，且已完成，不需要恢复。
- 没有任何 W0 新指纹任务，因此可以安全恢复 v1；不存在“先恢复会破坏在途任务”的情况。

## 4. 处理结果

1. 从父提交 `94aa003` 恢复 `img2img/v1/{workflow.json,binding.yaml}`（0.55 冻结版本）。
2. 新建 `img2img/v2/`：节点图与模型链相同，仅默认 denoise = 0.8，并补齐 `requirements` / `performance`。
3. `Img2ImgModule` 默认 binding 改为 `v2`；`configs/workflow.yaml` 的 `modules.img2img.binding_version` 改为 `v2`。
4. 历史 Job 的 `binding_version` / 指纹保持原样，未做任何数据库写入。
5. 回归测试锁定 v1 指纹（`7c1156…/2f2d5…`）与 v2 默认值，防止再次误改冻结目录。

## 5. 已知限制

- 1 个 LF 变体历史 Job 仍不可恢复；这是 W1 之前已存在的字节差异，本文如实记录，未修改数据库。
- `img2img` 输入图片的总像素上限仍未实现（W2）。
