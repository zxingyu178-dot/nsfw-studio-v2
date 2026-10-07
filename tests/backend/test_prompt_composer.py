"""PromptComposer（Phase 1 规范 §八、§九）。"""
from __future__ import annotations

from app.services.prompt_composer import (
    STRUCTURED_FIELDS,
    compose_structured,
    dumps_structured,
    empty_structured,
    loads_structured,
    normalize_structured,
)


def test_field_order_is_permanent():
    """八字段顺序永久固定：风格→人脸→服饰→动作→场景→构图→光线→额外。"""
    assert STRUCTURED_FIELDS == (
        "style", "face", "clothing", "pose", "scene", "composition", "lighting", "extra",
    )


def test_compose_skips_empty_and_keeps_order():
    composed = compose_structured(
        {"style": "anime", "scene": "cafe", "extra": "masterpiece", "face": "", "unknown_field": "x"}
    )
    assert composed == "anime, cafe, masterpiece"


def test_normalize_drops_unknown_and_strips():
    normalized = normalize_structured({"style": "  real  ", "bogus": "1", "pose": None})
    assert normalized["style"] == "real"
    assert normalized["pose"] == ""
    assert "bogus" not in normalized
    assert set(normalized) == set(STRUCTURED_FIELDS)


def test_dumps_roundtrip_is_stable():
    raw = dumps_structured({"style": "a", "extra": "b"})
    assert list(loads_structured(raw)) == list(STRUCTURED_FIELDS)
    assert loads_structured(raw)["style"] == "a"
    assert loads_structured(raw)["extra"] == "b"


def test_loads_tolerates_broken_json():
    assert loads_structured("not-json{") == empty_structured()
    assert loads_structured(None) == empty_structured()
    assert loads_structured('"a-string"') == empty_structured()
