# Daily Use 阶段 — Task 0 基线确认与保护

> 本文件由豆包在开工（任何功能代码）之前生成，用于确认本轮开发基线正确、工作区受保护、基线测试全绿。
>
> 对应开发计划：`NSFW_Studio_Daily_Use_Development_Plan_Doubao.md` 第五节（Task 0）与第三节（开发安全规则）。

---

## 1. Worktree 与分支身份

| 项目 | 值 |
| --- | --- |
| 主仓库（Git 主工作树，只读保护） | `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2` |
| **本轮开发 worktree（唯一开发位置）** | `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse` |
| 本轮开发分支 | `feature/daily-use-ux-runtime` |
| **基线 HEAD** | `d4f1821855064168d29300ad305e8a14ff20065b`（简写 `d4f1821`） |
| 远程 origin | `https://github.com/zxingyu178-dot/nsfw-studio-v2.git` |

Worktree 创建命令（严格按计划 3.1）：

```powershell
git worktree add D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse `
  -b feature/daily-use-ux-runtime d4f1821855064168d29300ad305e8a14ff20065b
```

### 关键基线确认

- [x] 新 worktree 的 `HEAD = d4f1821855064168d29300ad305e8a14ff20065b`（与计划要求一致，**不是** 从 main 旧 UI 起步）。
- [x] 新 worktree 创建后工作树 clean（`git status --porcelain` 计数为 0）。
- [x] 主工作树 `feature/ui-v1-phase7` 及其 12 处未提交 Anime 本地实验改动**完全未触碰**：未 stash、未 reset、未 clean、未 checkout、未改动/删除任何实验文件。
- [x] 新 worktree 位于 `projects\` 下，未散落到受管理根目录；与既有 worktree（`temp\baseline_wt`、`temp\nsfw-studio-v2-phase2b`）路径不冲突。

---

## 2. 关键 Git 引用

| 引用 | SHA |
| --- | --- |
| `main`（本地） | `3f4908ed709513cfa8a610550b30ed526b37e624` |
| `develop`（本地） | `3f4908ed709513cfa8a610550b30ed526b37e624` |
| `origin/main` | `3f4908ed709513cfa8a610550b30ed526b37e624`（v0.9.0） |
| `origin/develop` | `3f4908ed709513cfa8a610550b30ed526b37e624` |
| `feature/ui-v1-phase7`（本地） | `d4f1821855064168d29300ad305e8a14ff20065b` |
| `origin/feature/ui-v1-phase7` | `d4f1821855064168d29300ad305e8a14ff20065b` |

> 说明：本轮基线 `d4f1821` 领先主线 `3f4908e`（v0.9.0），是当前实际日用 UI 集成分支。本轮结束后按计划停在 `feature/daily-use-ux-runtime`，**不自行 merge main**，等待审查。

---

## 3. 工具链与本机环境

| 工具 | 版本 / 路径 |
| --- | --- |
| 后端虚拟环境（本轮 worktree 内，自建） | `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse\.venv`（Python **3.11.15**） |
| venv 基础解释器 | `C:\Espressif\tools\python\python.exe`（3.11.15） |
| 系统 PATH 中的 Python | 3.13.13（仅作记录；后端测试统一使用 worktree 的 3.11 venv） |
| Node.js | v22.23.2 |
| npm | 10.9.8 |
| 后端框架 | FastAPI（venv 内 0.143.0）、SQLAlchemy 2.1.4、pydantic 2.14、uvicorn 0.54、pytest 9.1.1 |
| 前端框架 | React 18 + TypeScript 5.6 + Vite 5.4（vitest 3.2） |

> 依赖安装：worktree venv 用 `pip install -r backend\requirements-dev.txt` 完成；前端用 `npm ci`（168 个包）完成。`.venv/` 与 `node_modules/` 均已被 `.gitignore`，不会入库。

---

## 4. 本机 ComfyUI 与数据路径（机器事实，仅记录，不入库）

| 项目 | 当前值 |
| --- | --- |
| ComfyUI 工作目录 | `D:\AIHome_2.0_L1_L2\projects\comfyui\app`（入口 `main.py`） |
| ComfyUI 解释器 | `D:\AIHome_2.0_L1_L2\projects\comfyui\venv\Scripts\python.exe` |
| ComfyUI 端口 | **8188**（固定，本轮禁止自动换口） |
| ComfyUI URL | `http://127.0.0.1:8188` |
| 当前 DataRoot | `D:/NSFW-Studio-Data` |
| 本机配置文件（主工作树） | `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2\configs\config.local.yaml`（gitignore，私有） |

`config.local.yaml` 当前关键内容（机器事实，**不会**复制进本轮提交）：

```yaml
data_root: "D:/NSFW-Studio-Data"
comfyui:
  url: "http://127.0.0.1:8188"
  output_dir: "D:/AIHome_2.0_L1_L2/projects/comfyui/app/output"
  input_dir: "D:/AIHome_2.0_L1_L2/projects/comfyui/app/input"
  input_ttl_seconds: 86400
```

> 边界说明：本轮 daily-use worktree 是全新检出，不含 `configs/config.local.yaml`（该文件 gitignore）。
> - 自动化测试通过夹具注入 `NSFW_STUDIO_DATA_ROOT` 指向临时目录，不依赖本机 config.local，也绝不触碰真实 DataRoot；
> - 若需在本 worktree 直接以日用模式运行，应在本机放置一份**未提交**的 `configs/config.local.yaml`（仓库只提供 template/schema，真实路径永不入库）。

---

## 5. 基线测试结果（全部先于功能代码执行）

### 5.1 Backend（pytest）

| 范围 | 结果 | 耗时 |
| --- | --- | --- |
| 确定性后端套件（CI 等价） | **254 passed** | 107.81 s |

命令：

```powershell
.venv\Scripts\python.exe -m pytest --ignore=tests/backend/test_comfyui_integration.py
```

**关于 `test_comfyui_integration.py` 的诚实说明（未隐瞒）：**

- 该文件带有 `pytest.mark.skipif(not _comfy_available())` 门控：仅当本机 8188 上检测到健康 ComfyUI 时运行，CI / 其他机器自动跳过。
- 本轮首次执行的是完整 `pytest`（无 ignore）。由于本机当时确有一个外部启动的 ComfyUI 运行在 8188（18:17 由既有 carrier 启动，非 Studio 启动），门控通过，套件进入 3 条**真实生图**用例，单条超时上限分别为 1200s / 2400s / 900s（最坏合计约 75 分钟），并会实际占用 GPU。
- 为得到快速、确定性、与 GitHub CI 一致的基线，执行者**停止**了这次长跑，改用上面的 CI 等价命令确认基线全绿（254 passed）。
- 这 3 条真实链路（基础生成 / 基础+高清 / 图库单独高清）所覆盖的"引擎在线真实生图"能力，将在本轮**真实浏览器 E2E 走查**（计划第二十三节 A~I、第二十四节异常验收）中以真实运行方式验收，不会被遗漏；其结果会在 `docs/DAILY_USE_ACCEPTANCE.md` 与最终报告中如实记录。

### 5.2 Frontend

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 依赖安装 | `npm ci` | 168 packages，成功 |
| 类型检查 | `npm run typecheck` | **通过**（exit 0） |
| 单元测试 | `npm test`（vitest run） | **44 passed**（6 个测试文件），未删除任何既有用例 |
| 生产构建 | `npm run build` | **成功**：88 modules，产出 `dist/`（index.css 42.58 kB、index.js 262.69 kB） |

> 原始测试输出已保存在本 worktree 的 gitignored 目录 `temp/baseline/`（`baseline_pytest.txt`、`baseline_typecheck.txt`、`baseline_vitest.txt`、`baseline_build.txt`），供交接包使用，不入库。

---

## 6. Task 0 结论

- 基线分支 / HEAD 正确（`feature/daily-use-ux-runtime` @ `d4f1821`），工作树 clean。
- 主工作树及其 Anime 本地实验改动已受保护、未受影响。
- 确定性后端基线 **254 passed**；前端 typecheck / 44 个 vitest / build **全部通过**。
- 环境门控的真实 ComfyUI 集成测试在基线条目下按 CI 等价方式跳过，其真实生图路径纳入后续真实 E2E 验收（已在本文件第 5.1 节如实说明）。

**基线满足开工条件，可以进入 Task 1（FastAPI 直接托管前端）。**
