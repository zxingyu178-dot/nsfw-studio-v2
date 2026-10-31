"""W1.2.1：CLI 默认工作流 fail-closed 与“不提前写 Prompt”回归。"""
from __future__ import annotations

import importlib.util
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
