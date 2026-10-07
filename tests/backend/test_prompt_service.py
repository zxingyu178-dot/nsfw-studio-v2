"""PromptService：CRUD / 版本机制 / 归档 / 并发保护（Phase 1 规范 §六-§十一、§五十五-§五十七）。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError
from app.models import PromptVersion
from app.services import prompt_service


def test_create_prompt_with_v1(session):
    prompt = prompt_service.create_prompt(
        session, name="测试", mode="structured",
        structured={"style": "anime", "extra": "hi"}, negative_prompt="blur",
    )
    assert prompt.id.startswith("prm_")
    version = prompt_service.get_current_version(session, prompt)
    assert version is not None
    assert version.id.startswith("prmv_")
    assert version.version_no == 1
    assert version.mode == "structured"
    assert version.negative_prompt == "blur"
    assert '"style": "anime"' in version.structured_json
    assert prompt.created_at.endswith("Z")  # UTC ISO 8601（规范 §五）


def test_content_change_creates_version_and_unchanged_skips(session):
    prompt = prompt_service.create_prompt(session, name="P", mode="full", positive_prompt="v1")
    first = prompt_service.get_current_version(session, prompt)

    version2, created = prompt_service.add_prompt_version(session, prompt.id, mode="full", positive_prompt="v2")
    assert created and version2.version_no == 2
    assert prompt.current_version_id == version2.id
    assert prompt_service.get_current_version(session, prompt).positive_prompt == "v2"

    # 相同内容 → 不产生 v3（规范 §十一：内容变化才建版本）
    current, created_again = prompt_service.add_prompt_version(
        session, prompt.id, mode="full", positive_prompt="v2"
    )
    assert not created_again
    assert current.id == version2.id


def test_meta_change_does_not_create_version(session):
    prompt = prompt_service.create_prompt(session, name="P", mode="full", positive_prompt="x")
    before = prompt_service.get_current_version(session, prompt)

    prompt_service.update_prompt_meta(session, prompt.id, name="改名", favorite=True)
    after = prompt_service.get_current_version(session, prompt)
    assert prompt.name == "改名"
    assert prompt.favorite is True
    assert after.id == before.id  # 版本未变（规范 §十一）


def test_versions_are_immutable_and_history_linear(session):
    prompt = prompt_service.create_prompt(session, name="P", mode="full", positive_prompt="v1")
    prompt_service.add_prompt_version(session, prompt.id, mode="full", positive_prompt="v2")
    prompt_service.add_prompt_version(session, prompt.id, mode="full", positive_prompt="v3")

    versions = prompt_service.list_versions(session, prompt.id)
    assert [v.version_no for v in versions] == [3, 2, 1]  # 按新→旧

    # 恢复 v1 → 创建 v4（指针不倒退，规范 §五十五）
    v1 = next(v for v in versions if v.version_no == 1)
    restored = prompt_service.restore_prompt_version(session, prompt.id, v1.id)
    assert restored.version_no == 4
    assert restored.positive_prompt == "v1"
    assert prompt_service.get_current_version(session, prompt).id == restored.id
    # 旧版本内容原样保留
    assert session.get(PromptVersion, v1.id).positive_prompt == "v1"


def test_archive_and_restore(session):
    prompt = prompt_service.create_prompt(session, name="P", mode="full", positive_prompt="x")
    prompt_service.set_archived(session, prompt.id, archived=True)
    assert prompt_service.get_prompt(session, prompt.id).archived is True
    prompt_service.set_archived(session, prompt.id, archived=False)
    assert prompt.archived is False


def test_not_found(session):
    with pytest.raises(NotFoundError) as exc:
        prompt_service.get_prompt(session, "prm_missing")
    assert exc.value.code == "PROMPT_NOT_FOUND"


def test_version_no_conflict_surfaces_conflict(session, monkeypatch):
    """并发保护（规范 §五十七）：UNIQUE(parent, version_no) 冲突 → 显式 ConflictError，不静默覆盖。"""
    prompt = prompt_service.create_prompt(session, name="P", mode="full", positive_prompt="x")

    # 模拟并发窗口：两个请求都计算出了同一个 version_no（此处强制返回已被占用的 1）
    monkeypatch.setattr(prompt_service, "_next_version_no", lambda session, prompt_id: 1)
    with pytest.raises(ConflictError) as exc:
        prompt_service.add_prompt_version(session, prompt.id, mode="full", positive_prompt="y")
    assert exc.value.code == "VERSION_CONFLICT"

    # 冲突回滚后：库中仍只有最初的 v1，current_version_id 未被破坏
    versions = session.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt.id)
    ).scalars().all()
    assert [v.version_no for v in versions] == [1]
    assert prompt_service.get_current_version(session, prompt).positive_prompt == "x"


def test_list_filters(session):
    p1 = prompt_service.create_prompt(session, name="人像 侧脸", mode="structured", structured={"face": "侧脸"})
    p2 = prompt_service.create_prompt(session, name="风景", mode="full", positive_prompt="mountain lake", favorite=True)
    prompt_service.set_archived(session, p2.id, archived=True)

    items, total = prompt_service.list_prompts(session)
    assert total == 1 and items[0].id == p1.id  # 默认不含已归档

    items, total = prompt_service.list_prompts(session, archived=None)
    assert total == 2

    items, _ = prompt_service.list_prompts(session, search="侧脸")
    assert [p.id for p in items] == [p1.id]  # 按结构化内容命中

    items, _ = prompt_service.list_prompts(session, favorite=True, archived=None)
    assert [p.id for p in items] == [p2.id]
