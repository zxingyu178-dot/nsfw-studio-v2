"""W1.2.1：CLI 默认工作流 fail-closed 与“不提前写 Prompt”回归。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/agent_generate.py"


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("agent_generate_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def allowed(module_id: str, *, is_default: bool = False, ready: bool = True) -> dict:
    return {
        "module_id": module_id,
        "title": module_id,
        "available": True,
        "is_generative": True,
        "input_required": False,
        "allowed_job_kinds": ["generate"],
        "is_default": is_default,
        "release_status": {"ready_to_run": ready},
    }


def test_default_requires_explicit_is_default(cli, monkeypatch):
    monkeypatch.setattr(cli, "get", lambda api, path: [allowed("basic_generate"), allowed("anime_generate")])
    assert cli.default_module_id("http://x") is None, "没有 is_default 时不得猜测默认"


def test_default_returns_marked_workflow(cli, monkeypatch):
    monkeypatch.setattr(cli, "get", lambda api, path: [
        allowed("basic_generate", is_default=True),
        allowed("anime_generate"),
    ])
    assert cli.default_module_id("http://x") == "basic_generate"


def test_default_unreleased_is_unavailable(cli, monkeypatch):
    monkeypatch.setattr(cli, "get", lambda api, path: [
        allowed("basic_generate", is_default=True, ready=False),
        allowed("anime_generate"),
    ])
    assert cli.default_module_id("http://x") is None, "默认未放行时不得切换到其他工作流"


def test_cli_does_not_call_prompt_ensure_or_expose_dead_option(cli):
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"/prompts/ensure"' not in source
    assert "no-prompt-library" not in source


def test_list_workflows_only_shows_agent_allowed(cli, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get", lambda api, path: [
        allowed("basic_generate", is_default=True),
        allowed("anime_generate", ready=False),
        {**allowed("img2img"), "input_required": True,
         "input_slots": [{"role": "source", "required": True, "max_count": 1}]},
    ])
    monkeypatch.setattr(sys, "argv", ["agent_generate.py", "--list-workflows"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "basic_generate" in output
    assert "anime_generate" not in output
    assert "img2img" not in output
    assert "服务端默认" in output


@pytest.mark.parametrize("value", ["", "   "])
def test_cli_blank_module_fails_before_http(cli, monkeypatch, capsys, value):
    """W1.2.2：显式空/纯空白 --module 必须在任何 HTTP 请求之前失败。"""
    calls: list[object] = []
    monkeypatch.setattr(cli, "post", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(cli, "get", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(sys, "argv", ["agent_generate.py", "--prompt", "x", "--module", value])
    assert cli.main() == 2
    assert calls == [], "空白 module_id 不得发起任何 HTTP 请求"
    assert "不能为空" in capsys.readouterr().out


def write_request(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


def test_request_file_preserves_prompts_and_explicit_request_id(cli, tmp_path):
    body = {
        "prompt": "portrait of a botanist, examining a fern, glasshouse, soft window light",
        "negative_prompt": "blur, watermark",
        "module_id": "basic_generate",
        "width": 768,
        "height": 1024,
        "count": 1,
        "seed": 42,
        "queue_mode": "normal",
        "client_request_id": "studio-daily-0001",
    }
    first = cli.load_request_file(write_request(tmp_path, body))
    second = cli.load_request_file(tmp_path / "request.json")
    assert first == second
    assert first["prompt"] == body["prompt"]
    assert first["negative_prompt"] == body["negative_prompt"]
    assert first["client_request_id"] == "studio-daily-0001"


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"surprise": True}, "未知字段"),
        ({"prompt": "   "}, "prompt"),
        ({"negative_prompt": 123}, "negative_prompt"),
        ({"module_id": "   "}, "module_id"),
        ({"width": True}, "width"),
        ({"width": 63}, "width"),
        ({"height": 4097}, "height"),
        ({"count": 0}, "count"),
        ({"seed": -1}, "seed"),
        ({"seed": 1, "count": 2}, "count"),
        ({"queue_mode": "urgent"}, "queue_mode"),
        ({"client_request_id": "   "}, "client_request_id"),
    ],
)
def test_request_file_rejects_invalid_contract(cli, tmp_path, patch, message):
    body = {"prompt": "safe landscape study"}
    body.update(patch)
    with pytest.raises(cli.RequestValidationError, match=message):
        cli.load_request_file(write_request(tmp_path, body))


def test_request_file_rejects_non_utf8_and_duplicate_fields(cli, tmp_path):
    bad_utf8 = tmp_path / "bad-utf8.json"
    bad_utf8.write_bytes(b'{"prompt":"\xff"}')
    with pytest.raises(cli.RequestValidationError, match="UTF-8"):
        cli.load_request_file(bad_utf8)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"prompt":"first","prompt":"second"}', encoding="utf-8")
    with pytest.raises(cli.RequestValidationError, match="重复字段"):
        cli.load_request_file(duplicate)


def test_request_file_requires_explicit_request_id(cli, tmp_path):
    with pytest.raises(cli.RequestValidationError, match="client_request_id.*必填"):
        cli.load_request_file(write_request(tmp_path, {"prompt": "safe landscape study"}))


def test_request_file_rejects_unpaired_surrogate_without_echo(cli, tmp_path, monkeypatch, capsys):
    secret_prompt = "PRIVATE_\ud800_PROMPT"
    request_file = tmp_path / "surrogate.json"
    request_file.write_text(json.dumps({
        "prompt": secret_prompt,
        "client_request_id": "studio-daily-surrogate",
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "agent_generate.py", "--request-file", str(request_file), "--validate-only",
    ])
    assert cli.main() == 2
    output = capsys.readouterr().out
    assert "UTF-8" in output
    assert "PRIVATE_" not in output


@pytest.mark.parametrize("width_arg", ["--width", "--width=768"])
def test_request_file_rejects_ambiguous_semantic_cli_options(
    cli, tmp_path, monkeypatch, capsys, width_arg,
):
    request_file = write_request(tmp_path, {
        "prompt": "safe landscape study", "client_request_id": "studio-daily-conflict",
    })
    argv = ["agent_generate.py", "--request-file", str(request_file), width_arg]
    if width_arg == "--width":
        argv.append("768")
    monkeypatch.setattr(sys, "argv", argv)
    assert cli.main() == 2
    assert "不能同时使用" in capsys.readouterr().out


def test_request_file_agent_submit_reuses_validated_request_id(cli, tmp_path, monkeypatch):
    request_file = write_request(tmp_path, {
        "prompt": "safe landscape study",
        "client_request_id": "studio-daily-0001",
    })
    calls = []

    def fake_post(api, path, payload, token=None, retries=0, suppress_error_body=False):
        calls.append((path, payload, token, retries, suppress_error_body))
        return {"id": "job_1", "status": "FAILED", "module_id": "basic_generate"}

    monkeypatch.setattr(cli, "load_token", lambda value: "masked-token")
    monkeypatch.setattr(cli, "post", fake_post)
    monkeypatch.setattr(cli, "get", lambda api, path: {
        "id": "job_1", "status": "FAILED", "error_type": "mock", "error_message": "mock",
    })
    monkeypatch.setattr(sys, "argv", [
        "agent_generate.py", "--request-file", str(request_file), "--out", str(tmp_path / "out"),
    ])

    assert cli.main() == 2
    assert len(calls) == 1
    path, payload, token, retries, suppress_error_body = calls[0]
    assert path == "/agent/jobs"
    assert payload["client_request_id"] == "studio-daily-0001"
    assert token == "masked-token"
    assert retries == 2
    assert suppress_error_body is True


def test_request_file_preserves_model_and_sampling(cli, tmp_path):
    body = {
        "prompt": "1girl, night city, anime style",
        "client_request_id": "studio-v15-0001",
        "module_id": "anime_generate",
        "module_version": "v1",
        "binding_version": "v15",
        "model": "NoobAI-XL-v1.1.safetensors",
        "loras": [{
            "name": "cunnyfunky_v5.0_000008.safetensors",
            "strength_model": 0.6,
            "strength_clip": 0.6,
        }],
        "params": {
            "steps": 28, "cfg": 5.0, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 0.9,
        },
    }
    normalized = cli.load_request_file(write_request(tmp_path, body))
    assert normalized["module_version"] == "v1" and normalized["binding_version"] == "v15"
    assert normalized["model"] == "NoobAI-XL-v1.1.safetensors"
    assert normalized["loras"][0]["strength_model"] == 0.6
    assert normalized["params"] == body["params"]


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"binding_version": "v15"}, "module_id"),
        ({"module_id": "anime_generate", "module_version": " "}, "module_version"),
        ({"binding_version": "v15", "module_id": "anime_generate", "model": "../evil"}, "model"),
        ({"module_id": "anime_generate", "loras": [{"name": "a"}, {"name": "b"}, {"name": "c"}]},
         "最多 2 条"),
        ({"module_id": "anime_generate", "params": {"steps": 0}}, "steps"),
        ({"module_id": "anime_generate", "params": {"unknown": 1}}, "未知字段"),
    ],
)
def test_request_file_rejects_invalid_model_contract(cli, tmp_path, patch, message):
    body = {"prompt": "safe study", "client_request_id": "studio-v15-bad"}
    body.update(patch)
    with pytest.raises(cli.RequestValidationError, match=message):
        cli.load_request_file(write_request(tmp_path, body))


def test_advanced_fields_require_agent_token(cli, tmp_path, monkeypatch, capsys):
    request_file = write_request(tmp_path, {
        "prompt": "safe study",
        "client_request_id": "studio-v15-legacy",
        "module_id": "anime_generate",
        "binding_version": "v15",
        "model": "NoobAI-XL-v1.1.safetensors",
    })
    calls = []
    monkeypatch.setattr(cli, "load_token", lambda value: "")
    monkeypatch.setattr(cli, "post", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(cli, "get", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(sys, "argv", [
        "agent_generate.py", "--request-file", str(request_file), "--out", str(tmp_path / "out"),
    ])
    assert cli.main() == 2
    assert calls == []
    assert "仅支持 Agent 端点" in capsys.readouterr().out


def test_parse_lora_option(cli):
    assert cli._parse_lora_option("a.safetensors") == {
        "name": "a.safetensors", "strength_model": 1.0, "strength_clip": 1.0,
    }
    assert cli._parse_lora_option("a.safetensors:0.6") == {
        "name": "a.safetensors", "strength_model": 0.6, "strength_clip": 0.6,
    }


def test_validate_only_has_no_credentials_network_or_directory_side_effects(
    cli, tmp_path, monkeypatch, capsys,
):
    prompt = "PRIVATE_PROMPT_BODY"
    token = "PRIVATE_TOKEN_VALUE"
    request_file = write_request(tmp_path, {
        "prompt": prompt, "client_request_id": "studio-daily-validate",
    })
    out_dir = tmp_path / "must-not-exist"

    def forbidden(*args, **kwargs):
        raise AssertionError("validate-only 不得加载凭据或联网")

    monkeypatch.setattr(cli, "load_token", forbidden)
    monkeypatch.setattr(cli, "post", forbidden)
    monkeypatch.setattr(cli, "get", forbidden)
    monkeypatch.setattr(sys, "argv", [
        "agent_generate.py",
        "--request-file", str(request_file),
        "--validate-only",
        "--token", token,
        "--out", str(out_dir),
    ])

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "校验通过" in output
    assert prompt not in output
    assert token not in output
    assert not out_dir.exists()
