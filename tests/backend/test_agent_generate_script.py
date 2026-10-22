"""scripts/agent_generate.py 的 token 解析：CLI/环境变量优先，回退本机 config.local.yaml；不打印 token。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "agent_generate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("agent_generate_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_or_env_token_has_priority(tmp_path):
    module = _load_module()
    config = tmp_path / "config.local.yaml"
    config.write_text('agent:\n  token: "from-config"\n', encoding="utf-8")
    assert module.load_token("from-cli", config) == "from-cli"


def test_fallback_to_local_config(tmp_path):
    module = _load_module()
    config = tmp_path / "config.local.yaml"
    config.write_text('agent:\n  token: "from-config-token"\n  rate_limit_per_min: 30\n', encoding="utf-8")
    assert module.load_token("", config) == "from-config-token"


def test_missing_or_invalid_config_returns_empty(tmp_path):
    module = _load_module()
    assert module.load_token("", tmp_path / "not-exists.yaml") == ""
    broken = tmp_path / "broken.yaml"
    broken.write_text("agent: [unclosed", encoding="utf-8")
    assert module.load_token("", broken) == ""
    no_agent = tmp_path / "no-agent.yaml"
    no_agent.write_text("data_root: D:/somewhere\n", encoding="utf-8")
    assert module.load_token("", no_agent) == ""
