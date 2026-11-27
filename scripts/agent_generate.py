"""agent_generate — AI 助手（豆包等）可直接调用的本机生图 CLI。

背景：豆包在云端，无法直接访问 http://127.0.0.1:8000；正确分工是"豆包给参数/写一行命令，
在本机执行本脚本"。脚本内已处理 UTF-8、幂等键、轮询、取图（二进制保存）全部细节。

前置：后端已启动（默认为 http://127.0.0.1:8000）。

用法（项目根目录）：
    .venv/Scripts/python scripts/agent_generate.py --prompt "a botanist examining a fern in a glasshouse" \
        [--module <workflow_id>] [--module-version v1] [--binding v15] [--list-workflows] \
        [--model NoobAI-XL-v1.1.safetensors] [--lora <name>[:<strength>]]... \
        [--steps 30] [--cfg 4.5] [--sampler er_sde] [--scheduler simple] [--denoise 1.0] \
        [--negative "..."] [--width 768] [--height 1024] [--count 1] [--seed 42] \
        [--next] [--status <job_id>] [--out D:\\ai_out] \
        [--api http://127.0.0.1:8000/api/v1] [--timeout-min 120]

模型/版本/采样参数（--module-version/--binding/--model/--lora/--steps/--cfg/--sampler/
--scheduler/--denoise）只支持 Agent 端点，需配置 agent.token。

W1.2 工作流规则：
- 不传 --module → 使用服务端当前默认工作流（不在 CLI 硬编码）；
- 显式 --module → 使用指定模块，但必须由服务端校验已注册 / 可用 / 已放行 / 文生图；
- --list-workflows → 读取 /modules，只列出 Agent 允许使用的文生图工作流；
- --list-models / --list-loras → 读取 /agent/capabilities，列出已安装底模或 LoRA 的
  友好名称、适用工作流与默认推荐；
- 输出打印**实际执行**的 module_id（不是 CLI 输入参数）。

示例（豆包只需改提示词）：
    .venv/Scripts/python scripts/agent_generate.py --prompt "a red fox resting beside a woodland stream" --out D:\\ai_out

安全（推荐）：在 configs/config.local.yaml 配置 agent.token 后，
脚本会自动读取该文件（也可用环境变量 NSFW_STUDIO_AGENT_TOKEN 覆盖），并走受保护的
POST /api/v1/agent/jobs（Bearer token + 每分钟限速 + 幂等）。未配置 token 时
仍走本机 /jobs（向后兼容；8000 只绑 loopback，外部 AI 无法直连）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path


REQUEST_FIELDS = {
    "prompt", "negative_prompt", "module_id", "module_version", "binding_version",
    "model", "loras", "params", "use_recommended_sampling", "width", "height", "count", "seed",
    "queue_mode", "client_request_id",
}
REQUEST_FILE_MAX_BYTES = 128 * 1024
REQUEST_SEMANTIC_OPTIONS = {
    "--prompt", "--module", "--module-version", "--binding", "--model", "--lora",
    "--steps", "--cfg", "--sampler", "--scheduler", "--denoise",
    "--face-detailer", "--no-face-detailer", "--use-recommended",
    "--negative", "--width", "--height", "--count", "--seed", "--next",
}
SAMPLE_PARAM_KEYS = {"steps", "cfg", "sampler_name", "scheduler", "denoise", "face_detailer"}
# 与后端 AGENT_DEFAULT_NEGATIVE_PROMPT 保持一致（合同测试守护，禁止分叉）。
DEFAULT_NEGATIVE_PROMPT = (
    "worst quality, low quality, blurry, jpeg artifacts, watermark, text"
)
ADVANCED_FIELDS = (
    "module_version", "binding_version", "model", "loras", "params",
    "use_recommended_sampling",
)


class RequestValidationError(ValueError):
    """标准请求文件不符合 /agent/jobs 输入契约。"""


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise RequestValidationError(f"JSON 包含重复字段: {key}")
        result[key] = value
    return result


def _require_int(payload: dict, field: str, minimum: int, maximum: int) -> int:
    value = payload[field]
    if type(value) is not int:  # bool 是 int 子类，但不应被 JSON 合同接受。
        raise RequestValidationError(f"{field} 必须是整数")
    if not minimum <= value <= maximum:
        raise RequestValidationError(f"{field} 必须在 {minimum}..{maximum} 之间")
    return value


def _require_utf8_text(value: str, field: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise RequestValidationError(f"{field} 包含不能编码为 UTF-8 的字符") from error


def _normalize_loras(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RequestValidationError("loras 必须是数组")
    if len(value) > 2:
        raise RequestValidationError("loras 最多 2 条")
    normalized: list[dict] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise RequestValidationError(f"第 {index} 条 LoRA 必须是对象")
        unknown = set(item) - {"name", "strength_model", "strength_clip"}
        if unknown:
            raise RequestValidationError(
                f"第 {index} 条 LoRA 含未知字段: {', '.join(sorted(unknown))}"
            )
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RequestValidationError(f"第 {index} 条 LoRA 缺少文件名")
        name = name.strip()
        if "/" in name or "\\" in name:
            raise RequestValidationError(f"第 {index} 条 LoRA 文件名不得包含路径")
        strengths: dict[str, float] = {}
        for key in ("strength_model", "strength_clip"):
            if item.get(key) is None:
                # 未显式给强度：保留省略，由服务端套用注册中心推荐强度。
                continue
            raw = item[key]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise RequestValidationError(f"第 {index} 条 LoRA 的 {key} 必须是数字")
            if not -2.0 <= float(raw) <= 2.0:
                raise RequestValidationError(f"第 {index} 条 LoRA 的 {key} 必须在 -2..2")
            strengths[key] = float(raw)
        normalized.append({"name": name, **strengths})
    return normalized


def _normalize_params(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RequestValidationError("params 必须是对象")
    unknown = set(value) - SAMPLE_PARAM_KEYS
    if unknown:
        raise RequestValidationError(f"params 含未知字段: {', '.join(sorted(unknown))}")
    params: dict = {}
    if value.get("steps") is not None:
        steps = value["steps"]
        if type(steps) is not int or not 1 <= steps <= 100:
            raise RequestValidationError("params.steps 必须是 1..100 的整数")
        params["steps"] = steps
    if value.get("cfg") is not None:
        cfg = value["cfg"]
        if isinstance(cfg, bool) or not isinstance(cfg, (int, float)) or not 1.0 <= float(cfg) <= 20.0:
            raise RequestValidationError("params.cfg 必须是 1.0..20.0 的数字")
        params["cfg"] = float(cfg)
    if value.get("denoise") is not None:
        denoise = value["denoise"]
        if isinstance(denoise, bool) or not isinstance(denoise, (int, float)) or not 0.0 <= float(denoise) <= 1.0:
            raise RequestValidationError("params.denoise 必须是 0.0..1.0 的数字")
        params["denoise"] = float(denoise)
    for key in ("sampler_name", "scheduler"):
        if value.get(key) is not None:
            raw = value[key]
            if not isinstance(raw, str) or not raw.strip() or len(raw) > 64:
                raise RequestValidationError(f"params.{key} 必须是非空字符串（≤64）")
            params[key] = raw.strip()
    if value.get("face_detailer") is not None:
        face_detailer = value["face_detailer"]
        if not isinstance(face_detailer, bool):
            raise RequestValidationError("params.face_detailer 必须是布尔值")
        params["face_detailer"] = face_detailer
    return params


def _parse_lora_option(value: str) -> dict:
    """解析 CLI 的 --lora 写法：`文件名` 或 `文件名:0.6`。

    不写强度时保留省略，由服务端按注册中心 recommended_strength 补齐。
    """
    raw = value.strip()
    if not raw:
        raise RequestValidationError("--lora 不能为空")
    name, separator, suffix = raw.rpartition(":")
    if separator and name:
        try:
            strength = float(suffix)
        except ValueError:
            name = raw
        else:
            return {"name": name, "strength_model": strength, "strength_clip": strength}
    return {"name": raw}


def advanced_request_fields(payload: dict) -> list[str]:
    return [field for field in ADVANCED_FIELDS if field in payload]


def validate_request(payload: object, *, require_client_request_id: bool = False) -> dict:
    """严格校验并补齐 Agent API 默认值；绝不改写 Prompt 正文。"""
    if not isinstance(payload, dict):
        raise RequestValidationError("JSON 顶层必须是对象")
    unknown = sorted(set(payload) - REQUEST_FIELDS)
    if unknown:
        raise RequestValidationError(f"未知字段: {', '.join(unknown)}")

    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise RequestValidationError("prompt 必须是字符串")
    if not prompt.strip():
        raise RequestValidationError("prompt 不能为空或纯空白")
    if len(prompt) > 10000:
        raise RequestValidationError("prompt 最多 10000 个字符")
    _require_utf8_text(prompt, "prompt")

    negative = payload.get("negative_prompt")
    if negative is not None:
        if not isinstance(negative, str):
            raise RequestValidationError("negative_prompt 必须是字符串或 null")
        if negative and not negative.strip():
            raise RequestValidationError("negative_prompt 显式提供时不能是纯空白")
        if len(negative) > 8000:
            raise RequestValidationError("negative_prompt 最多 8000 个字符")
        _require_utf8_text(negative, "negative_prompt")

    module_id = payload.get("module_id")
    if module_id is not None:
        if not isinstance(module_id, str):
            raise RequestValidationError("module_id 必须是字符串或 null")
        if not module_id.strip():
            raise RequestValidationError("module_id 不能为空或纯空白")
        if len(module_id) > 64:
            raise RequestValidationError("module_id 最多 64 个字符")
        _require_utf8_text(module_id, "module_id")

    versions: dict[str, str] = {}
    for field in ("module_version", "binding_version"):
        raw = payload.get(field)
        if raw is None:
            continue
        if module_id is None:
            raise RequestValidationError(f"指定 {field} 时必须同时提供 module_id")
        if not isinstance(raw, str) or not raw.strip():
            raise RequestValidationError(f"{field} 必须是非空字符串或 null")
        if len(raw) > 32 or "/" in raw or "\\" in raw:
            raise RequestValidationError(f"{field} 非法（≤32，不得含路径分隔符）")
        versions[field] = raw.strip()

    model = payload.get("model")
    if model is not None:
        if not isinstance(model, str):
            raise RequestValidationError("model 必须是字符串或 null")
        if not model.strip():
            raise RequestValidationError("model 不能为空或纯空白")
        if len(model) > 255 or "/" in model or "\\" in model:
            raise RequestValidationError("model 非法（≤255，不得含路径分隔符）")
        _require_utf8_text(model, "model")
        model = model.strip()

    use_recommended = payload.get("use_recommended_sampling", False)
    if not isinstance(use_recommended, bool):
        raise RequestValidationError("use_recommended_sampling 必须是布尔值")

    normalized = {
        "prompt": prompt,
        "negative_prompt": negative,
        "width": payload.get("width", 1024),
        "height": payload.get("height", 1024),
        "count": payload.get("count", 1),
        "seed": payload.get("seed"),
        "queue_mode": payload.get("queue_mode", "normal"),
    }
    if module_id is not None:
        normalized["module_id"] = module_id.strip()
    normalized.update(versions)
    if model is not None:
        normalized["model"] = model
    if use_recommended:
        normalized["use_recommended_sampling"] = True
    loras = _normalize_loras(payload.get("loras"))
    if loras:
        normalized["loras"] = loras
    params = _normalize_params(payload.get("params"))
    if params:
        normalized["params"] = params

    _require_int(normalized, "width", 64, 4096)
    _require_int(normalized, "height", 64, 4096)
    count = _require_int(normalized, "count", 1, 64)
    seed = normalized["seed"]
    if seed is not None:
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise RequestValidationError("seed 必须是 null 或 0..2147483647 的整数")
        if count != 1:
            raise RequestValidationError("固定 seed 时 count 必须为 1")
    if normalized["queue_mode"] not in ("normal", "next"):
        raise RequestValidationError("queue_mode 只支持 normal 或 next")

    request_id = payload.get("client_request_id")
    if request_id is None and require_client_request_id:
        raise RequestValidationError("client_request_id 是标准请求文件的必填字段")
    if request_id is not None:
        if not isinstance(request_id, str):
            raise RequestValidationError("client_request_id 必须是字符串或 null")
        if not request_id.strip():
            raise RequestValidationError("client_request_id 不能为空或纯空白")
        if len(request_id) > 128:
            raise RequestValidationError("client_request_id 最多 128 个字符")
        _require_utf8_text(request_id, "client_request_id")
        normalized["client_request_id"] = request_id.strip()
    else:
        normalized["client_request_id"] = f"cli_{uuid.uuid4().hex[:12]}"
    return normalized


def load_request_file(path: Path) -> dict:
    """读取标准 UTF-8 JSON 请求；限制大小并拒绝重复字段。"""
    try:
        with path.open("rb") as stream:
            raw = stream.read(REQUEST_FILE_MAX_BYTES + 1)
    except OSError as error:
        raise RequestValidationError(f"无法读取请求文件: {error}") from error
    if len(raw) > REQUEST_FILE_MAX_BYTES:
        raise RequestValidationError(f"请求文件不能超过 {REQUEST_FILE_MAX_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RequestValidationError("请求文件必须是标准 UTF-8 编码") from error
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_fields)
    except RequestValidationError:
        raise
    except json.JSONDecodeError as error:
        raise RequestValidationError(
            f"JSON 语法错误（第 {error.lineno} 行，第 {error.colno} 列）",
        ) from error
    return validate_request(payload, require_client_request_id=True)


def post(
    api: str,
    path: str,
    payload: dict,
    token: str | None = None,
    retries: int = 0,
    suppress_error_body: bool = False,
):
    """POST JSON（失败直接退出；不存在可降级提交路径）。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 中文安全：UTF-8 字节
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        api + path, data=data, method="POST", headers=headers,
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code < 500 or attempt == retries:
                suffix = "（响应正文已省略）" if suppress_error_body else f": {body[:600]}"
                raise SystemExit(f"[FAIL] HTTP {error.code}{suffix}") from error
        except urllib.error.URLError as error:
            if attempt == retries:
                raise SystemExit(f"[FAIL] 提交失败: {error.reason}") from error
        time.sleep(1)
    raise AssertionError("unreachable")


def get(api: str, path: str, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(api + path, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def load_token(cli_value: str = "", config_path: Path | None = None) -> str:
    """解析 Agent token：CLI/环境变量优先，否则读本机私有 config.local.yaml。

    只返回字符串，绝不打印 token 本身；文件不存在/解析失败时回退为空（走旧路径）。
    """
    token = (cli_value or "").strip()
    if token:
        return token
    token = os.environ.get("NSFW_STUDIO_AGENT_TOKEN", "").strip()
    if token:
        return token
    path = config_path or (Path(__file__).resolve().parents[1] / "configs" / "config.local.yaml")
    try:
        import yaml  # 项目 venv 已包含 pyyaml（配置加载依赖）

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        agent = data.get("agent") if isinstance(data, dict) else None
        return str((agent or {}).get("token") or "").strip() if isinstance(agent, dict) else ""
    except Exception:
        return ""


def allows_agent_module(module: dict) -> bool:
    """与服务端 Agent 能力校验保持一致：可用 + 已放行 + 生成型 + 无输入图 + 允许 generate。"""
    allowed = module.get("allowed_job_kinds") or []
    return (
        module.get("available") is True
        and module.get("is_generative") is True
        and module.get("input_required") is not True
        and (module.get("release_status") or {}).get("ready_to_run") is True
        and "generate" in allowed
    )


def list_agent_workflows(api: str) -> list[dict]:
    return [module for module in get(api, "/modules") if allows_agent_module(module)]


def default_module_id(api: str) -> str | None:
    """服务端当前默认工作流（只认 /modules 的 is_default，绝不猜测第一个候选）。"""
    candidates = list_agent_workflows(api)
    preferred = next((m for m in candidates if m.get("is_default") is True), None)
    return str(preferred.get("module_id")) if preferred else None


def _format_recommended(profile: object) -> str:
    if not isinstance(profile, dict):
        return ""
    parts = []
    if profile.get("steps") is not None:
        parts.append(f"{profile['steps']} 步")
    if profile.get("cfg") is not None:
        parts.append(f"cfg{profile['cfg']}")
    if profile.get("sampler_name"):
        parts.append(str(profile["sampler_name"]))
    if profile.get("scheduler"):
        parts.append(str(profile["scheduler"]))
    return " / ".join(parts)


def list_agent_models(api: str, token: str) -> int:
    """打印已安装底模、注册中心元数据与推荐采样参数（需 Agent token）。"""
    capabilities = get(api, "/agent/capabilities", token=token)
    models = capabilities.get("models") or []
    catalog = capabilities.get("model_catalog") or {}
    profiles = capabilities.get("sampling_profiles") or {}
    if not models:
        print("[!] 当前没有已安装的底模；请先在 ComfyUI /models/checkpoints 安装并重启引擎")
        return 1
    print(f"[OK] 已安装底模（{len(models)}）：")
    for name in models:
        entry = catalog.get(name) or {}
        display = str(entry.get("display_name") or "")
        family = str(entry.get("family") or "")
        recommended = _format_recommended(entry.get("recommended_sampling") or profiles.get(name))
        print(f"  - {name}")
        details = [part for part in (
            display if display and display != name else "",
            family,
            f"推荐 {recommended}" if recommended else "",
        ) if part]
        if details:
            print("    " + " · ".join(details))
    default_model = capabilities.get("default_model")
    if default_model:
        default_profile = capabilities.get("default_sampling_profile") or profiles.get(default_model)
        recommended = _format_recommended(default_profile)
        print(f"默认底模：{default_model}" + (f"（推荐 {recommended}）" if recommended else ""))
    return 0


def list_agent_loras(api: str, token: str) -> int:
    """打印已安装 LoRA、注册中心元数据与适用工作流（需 Agent token）。"""
    capabilities = get(api, "/agent/capabilities", token=token)
    loras = capabilities.get("loras") or []
    catalog = capabilities.get("lora_catalog") or {}
    if not loras:
        print("[!] 当前没有已安装的 LoRA；请先在 ComfyUI /models/loras 安装并重启引擎")
        return 1
    print(f"[OK] 已安装 LoRA（{len(loras)}）：")
    for name in loras:
        entry = catalog.get(name) or {}
        display = str(entry.get("display_name") or "")
        family = str(entry.get("family") or "")
        workflows = "/".join(str(item) for item in entry.get("compatible_workflows") or [])
        base_models = "、".join(str(item) for item in entry.get("base_models") or [])
        strength = entry.get("recommended_strength")
        print(f"  - {name}")
        details = [part for part in (
            display if display and display != name else "",
            family,
            f"推荐强度 {strength}" if isinstance(strength, (int, float)) else "",
            f"适用 {workflows}" if workflows else "",
            f"依赖 {base_models}" if base_models else "",
        ) if part]
        if details:
            print("    " + " · ".join(details))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="本机生图 CLI（AI 助手调用入口）")
    parser.add_argument("--prompt", default="", help="正向提示词（中文/英文标签均可）")
    parser.add_argument("--request-file", type=Path,
                        help="标准 UTF-8 JSON 请求（字段与 POST /agent/jobs 一致）")
    parser.add_argument("--validate-only", action="store_true",
                        help="仅离线校验请求；不加载凭据、不联网、不创建输出目录")
    parser.add_argument("--module", default=None,
                        help="工作流模块 id；不传使用服务端默认。可用性由服务端校验")
    parser.add_argument("--module-version", default=None,
                        help="模块代码版本（需配合 --module；仅 Agent 端点）")
    parser.add_argument("--binding", default=None,
                        help="binding 版本（如 v15；仅 Agent 端点）")
    parser.add_argument("--model", default=None,
                        help="底模文件名（不含路径，例如 NoobAI-XL-v1.1.safetensors；仅 Agent 端点）")
    parser.add_argument("--lora", action="append", default=None, metavar="NAME[:STRENGTH]",
                        help="LoRA 文件名（可带强度，最多 2 条；不写强度时由服务端套用推荐强度；仅 Agent 端点）")
    parser.add_argument("--steps", type=int, default=None, help="采样步数（仅 Agent 端点）")
    parser.add_argument("--cfg", type=float, default=None, help="CFG（仅 Agent 端点）")
    parser.add_argument("--sampler", default=None, help="采样器名称（仅 Agent 端点）")
    parser.add_argument("--scheduler", default=None, help="调度器名称（仅 Agent 端点）")
    parser.add_argument("--denoise", type=float, default=None, help="降噪强度 0..1（仅 Agent 端点）")
    parser.add_argument("--face-detailer", dest="face_detailer", action="store_true", default=None,
                        help="强制开启人脸修复（FaceDetailer）")
    parser.add_argument("--no-face-detailer", dest="face_detailer", action="store_false",
                        help="关闭人脸修复以显著提速（仅 Agent 端点）")
    parser.add_argument("--use-recommended", action="store_true",
                        help="套用注册中心推荐采样参数；省略 --model 时用 binding 默认底模（仅 Agent 端点）")
    parser.add_argument("--list-workflows", action="store_true",
                        help="列出 Agent 允许使用的文生图工作流（不提交任务）")
    parser.add_argument("--list-models", action="store_true",
                        help="列出已安装底模、注册中心元数据与推荐采样参数（需 Agent token）")
    parser.add_argument("--list-loras", action="store_true",
                        help="列出已安装 LoRA、显示名、family、适用工作流与依赖（需 Agent token）")
    parser.add_argument("--status", default=None, metavar="JOB_ID",
                        help="只读查询任务进度（/agent/jobs/{id}，需 Agent token；不提交、不下载）")
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE_PROMPT,
                        help="负向提示词；不传使用统一默认，传空字符串表示不使用负向提示词")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None, help="固定 Seed（默认随机）")
    parser.add_argument("--next", dest="queue_next", action="store_true",
                        help="插队到等待队列最前（默认排到队尾）")
    parser.add_argument("--out", default=".", help="输出目录（默认当前目录）")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--timeout-min", type=int, default=120, help="单任务超时（分钟）")
    parser.add_argument("--token", default="",
                        help="Agent token（默认读 NSFW_STUDIO_AGENT_TOKEN；配置后走受保护的 /agent/jobs）")
    parser.add_argument("--legacy", action="store_true",
                        help="强制走旧 /jobs 端点（仅本机调试；不推荐）")
    args = parser.parse_args()

    if args.status is not None:
        if args.list_workflows or args.list_models or args.list_loras or args.request_file is not None:
            print("[FAIL] --status 不能与其他操作同时使用")
            return 2
        token = load_token(args.token)
        if not token:
            print("[FAIL] --status 需要 Agent token（配置 agent.token 或 --token）")
            return 2
        data = get(args.api, f"/agent/jobs/{args.status}", token=token)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.list_models or args.list_loras:
        flag = "--list-models" if args.list_models else "--list-loras"
        if args.list_models and args.list_loras:
            print("[FAIL] --list-models 不能与 --list-loras 同时使用")
            return 2
        if args.list_workflows:
            print(f"[FAIL] {flag} 不能与 --list-workflows 同时使用")
            return 2
        if args.request_file is not None:
            print(f"[FAIL] {flag} 不能与 --request-file 同时使用")
            return 2
        token = load_token(args.token)
        if not token:
            print(f"[FAIL] {flag} 需要 Agent token（配置 agent.token 或 --token）")
            return 2
        return list_agent_models(args.api, token) if args.list_models else list_agent_loras(args.api, token)

    if args.request_file is not None:
        supplied_options = {item.split("=", 1)[0] for item in sys.argv[1:] if item.startswith("--")}
        explicit_semantic = sorted(REQUEST_SEMANTIC_OPTIONS.intersection(supplied_options))
        if explicit_semantic:
            print("[FAIL] --request-file 不能同时使用请求语义参数: " + ", ".join(explicit_semantic))
            return 2
        if args.list_workflows:
            print("[FAIL] --request-file 不能与 --list-workflows 同时使用")
            return 2
        try:
            request_payload = load_request_file(args.request_file)
        except RequestValidationError as error:
            print(f"[FAIL] 请求文件校验失败: {error}")
            return 2
    else:
        if args.validate_only and args.list_workflows:
            print("[FAIL] --validate-only 不能与 --list-workflows 同时使用")
            return 2
        direct_payload = {
            "prompt": args.prompt,
            "negative_prompt": args.negative,
            "width": args.width,
            "height": args.height,
            "count": args.count,
            "seed": args.seed,
            "queue_mode": "next" if args.queue_next else "normal",
            "client_request_id": f"cli_{uuid.uuid4().hex[:12]}",
            **({"module_id": args.module} if args.module is not None else {}),
        }
        if args.module_version is not None:
            direct_payload["module_version"] = args.module_version
        if args.binding is not None:
            direct_payload["binding_version"] = args.binding
        if args.model is not None:
            direct_payload["model"] = args.model
        if args.use_recommended:
            direct_payload["use_recommended_sampling"] = True
        if args.lora:
            try:
                direct_payload["loras"] = [_parse_lora_option(item) for item in args.lora]
            except RequestValidationError as error:
                print(f"[FAIL] 参数校验失败: {error}")
                return 2
        params = {
            "steps": args.steps,
            "cfg": args.cfg,
            "sampler_name": args.sampler,
            "scheduler": args.scheduler,
            "denoise": args.denoise,
            "face_detailer": args.face_detailer,
        }
        params = {key: value for key, value in params.items() if value is not None}
        if params:
            direct_payload["params"] = params
        try:
            request_payload = validate_request(direct_payload)
        except RequestValidationError as error:
            if not args.list_workflows:
                print(f"[FAIL] 参数校验失败: {error}")
                return 2
            request_payload = {}

    if args.list_workflows:
        modules = list_agent_workflows(args.api)
        if not modules:
            print("[!] 当前没有 Agent 可用的文生图工作流（检查 /modules 的 available / ready_to_run）")
            return 1
        print("[OK] Agent 可用工作流：")
        for module in modules:
            mark = "（服务端默认）" if module.get("is_default") is True else ""
            print(f"  - {module['module_id']}{mark}  {module.get('title') or ''}")
        return 0

    if args.validate_only:
        print("[OK] 请求校验通过（未加载凭据、未联网、未创建输出目录）")
        return 0

    # Agent 加固路径把 module_id 省略交给服务端解析（不在 CLI 里写默认）；
    # 旧 /jobs 路径需要先解析实际 Primary。
    token = load_token(args.token)
    use_agent_endpoint = bool(token) and not args.legacy
    advanced = advanced_request_fields(request_payload)
    if advanced and not use_agent_endpoint:
        print("[FAIL] 以下字段仅支持 Agent 端点（需配置 agent.token 或 --token）: "
              + ", ".join(advanced))
        return 2
    if "module_id" in request_payload:
        primary_id: str | None = request_payload["module_id"]
    elif use_agent_endpoint:
        primary_id = None
    else:
        primary_id = default_module_id(args.api)
        if not primary_id:
            print("[FAIL] 服务端未标记可用的默认工作流；请显式 --module <workflow> "
                  "（CLI 不猜测默认，也不自动切换）")
            return 2
    modules = [{"module_id": primary_id}] if primary_id else []

    # W1.2.1：Prompt 由服务端在 Job 创建事务内统一关联（不再提前调 /prompts/ensure）；
    # 未放行/非法请求不会提前产生 Prompt。
    if token and not args.legacy:
        # 加固路径：专用 Agent 端点，Bearer token + 服务端限速 + 幂等键。
        job = post(
            args.api, "/agent/jobs", request_payload, token=token,
            retries=2 if args.request_file is not None else 0,
            suppress_error_body=args.request_file is not None,
        )
    else:
        # 旧路径：本机 loopback UI 同款 /jobs（未配置 token 时保持向后兼容）。
        job = post(args.api, "/jobs", {
            "source": "doubao",
            "client_request_id": request_payload["client_request_id"],
            "queue_mode": request_payload["queue_mode"],
            "snapshot": {
                "prompt_mode": "full",
                "full_prompt": request_payload["prompt"],
                "negative_prompt": request_payload["negative_prompt"]
                if request_payload["negative_prompt"] is not None else DEFAULT_NEGATIVE_PROMPT,
                "count": request_payload["count"],
                "width": request_payload["width"],
                "height": request_payload["height"],
                "seed_mode": "fixed" if request_payload["seed"] is not None else "random",
                "seed": request_payload["seed"],
                "workflow_modules": modules,
                "input_images": [],
            },
        }, retries=2 if args.request_file is not None else 0,
           suppress_error_body=args.request_file is not None)
    job_id = job["id"]
    actual_modules = [
        item.get("module_id") for item in (job.get("workflow_snapshot") or {}).get("modules") or []
    ] or [job.get("module_id")]
    actual_primary = str(job.get("module_id") or (actual_modules[0] if actual_modules else "") or "job")
    print(f"[..] job={job_id}  状态={job['status']}  实际工作流={actual_modules}")

    deadline = time.time() + args.timeout_min * 60
    detail = job
    while time.time() < deadline:
        detail = get(args.api, f"/jobs/{job_id}")
        if detail["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            break
        time.sleep(5)

    if detail["status"] != "COMPLETED":
        print(f"[FAIL] 任务未成功: {detail['status']} {detail.get('error_type')} {detail.get('error_message')}")
        return 2

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, item in enumerate(detail["items"]):
        image_id = item.get("image_id")
        if not image_id:
            continue
        with urllib.request.urlopen(f"{args.api}/images/{image_id}/content", timeout=300) as response:
            data = response.read()  # 图片是二进制：只写文件，不当文本打印
        file_path = out_dir / f"{actual_primary}_{job_id[-8:]}_{index}.png"
        file_path.write_bytes(data)
        saved.append(str(file_path))
        print(f"[OK] {file_path}  ({len(data)} bytes)")

    if not saved:
        print("[FAIL] 任务完成但未找到输出图片")
        return 3
    print(f"[OK] 完成：{len(saved)} 张。Seed={detail['items'][0].get('seed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
