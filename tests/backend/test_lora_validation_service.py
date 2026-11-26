"""任务级 LoRA 存在性校验（v5）。"""
from __future__ import annotations

import pytest

from app.core.errors import UnprocessableError
from app.services.lora_validation_service import validate_task_loras


class _Adapter:
    def __init__(self, names: set[str] | None) -> None:
        self.names = names

    def available_lora_names(self) -> set[str] | None:
        return self.names


def test_skips_when_no_lora_configured():
    validate_task_loras(_Adapter({"a"}), [{"module_id": "anime_generate", "config": {}}])


def test_passes_when_all_names_exist():
    modules = [{
        "module_id": "anime_generate",
        "config": {"loras": [{"name": "a.safetensors"}, {"name": "b.safetensors"}]},
    }]
    validate_task_loras(_Adapter({"a.safetensors", "b.safetensors"}), modules)


def test_missing_lora_raises_422_with_code():
    modules = [{
        "module_id": "anime_generate",
        "config": {"loras": [{"name": "missing.safetensors"}]},
    }]
    with pytest.raises(UnprocessableError) as error:
        validate_task_loras(_Adapter({"a.safetensors"}), modules)
    assert error.value.status_code == 422
    assert error.value.code == "LORA_NOT_FOUND"
    assert "missing.safetensors" in error.value.message


def test_engine_unreachable_does_not_block():
    modules = [{
        "module_id": "anime_generate",
        "config": {"loras": [{"name": "missing.safetensors"}]},
    }]
    validate_task_loras(_Adapter(None), modules)
