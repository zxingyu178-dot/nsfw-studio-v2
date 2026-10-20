"""V1 输出导入仅使用临时 DataRoot；绝不调用真实 CLI apply。"""
import importlib.util
import json
import os
from pathlib import Path
import sys

from PIL import Image as PILImage
import pytest
from sqlalchemy import select

from app.database.backup import backup_database
from app.models import Image, Prompt, PromptVersion
from app.services import prompt_service, image_service
from app.storage.manager import StorageManager


def importer():
    path = Path(__file__).resolve().parents[2] / "scripts/import_v1_outputs.py"
    assert path.is_file(), "导入脚本尚未实现"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("import_v1_outputs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample(tmp_path, settings, session_factory):
    output = tmp_path / "output"
    output.mkdir()
    cache = {}
    for n, text in enumerate(["landscape", "landscape", "still life"]):
        path = output / f"{n}.png"
        PILImage.new("RGB", (8, 8), (n * 60, 10, 20)).save(path)
        cache[str(path)] = [1234 + n, text]
    source = tmp_path / "v1"
    (source / "runtime").mkdir(parents=True)
    (source / "runtime/prompt_cache.json").write_text(json.dumps(cache), encoding="utf-8")
    return source, output, settings.storage.data_root


def counts(session_factory):
    with session_factory() as session:
        return tuple(len(list(session.scalars(select(model)))) for model in (Image, Prompt))


def backup(root):
    return backup_database(root / "database/studio.db", root / "backups")


def test_dry_run_writes_only_plan(sample, session_factory):
    source, output, root = sample
    assert counts(session_factory) == (0, 0)  # 先建立 fixture 的 WAL 读连接
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    plan = importer().run(source, output, root)
    assert plan["stats"]["will_import"] == 3
    assert plan["stats"]["will_create_prompts"] == 2
    assert counts(session_factory) == (0, 0)
    after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert all(after[k] == value for k, value in before.items())
    assert all(k.startswith("backups") for k in after.keys() - before.keys()), after.keys() - before.keys()
    assert list((root / "backups").glob("v1-outputs-plan-*.json"))


def test_apply_reuses_prompt_and_is_idempotent(sample, session_factory):
    source, output, root = sample
    with session_factory() as session:
        old = prompt_service.create_prompt(session, name="Existing", mode="full", positive_prompt="landscape")
        old_id = old.id
    backup(root)
    module = importer()
    module.run(source, output, root, apply=True)
    assert counts(session_factory) == (3, 2)
    with session_factory() as session:
        images = list(session.scalars(select(Image)))
        assert all(i.source == "import" and i.sha256 and i.job_id is None for i in images)
        records = [json.loads(i.metadata_json)["v1_output"] for i in images]
        assert sum(r["prompts"][0]["prompt_id"] == old_id for r in records) == 2
        assert all(Path(r["sources"][0]["path"]).is_file() for r in records)
    second = module.run(source, output, root, apply=True)
    assert second["stats"]["will_import"] == 0
    assert counts(session_factory) == (3, 2)


def test_missing_or_expired_backup_refused(sample, session_factory):
    source, output, root = sample
    module = importer()
    with pytest.raises(ValueError, match="backup_db"):
        module.run(source, output, root, apply=True)
    saved = backup(root)
    os.utime(saved, (1, 1))
    with pytest.raises(ValueError, match="backup_db"):
        module.run(source, output, root, apply=True)
    assert counts(session_factory) == (0, 0)


def test_limit_and_duplicate_content(sample, session_factory):
    source, output, root = sample
    cache_path = source / "runtime/prompt_cache.json"
    cache = json.loads(cache_path.read_text())
    duplicate = output / "duplicate.png"
    duplicate.write_bytes((output / "0.png").read_bytes())
    cache[str(duplicate)] = [2345, "another description"]
    cache_path.write_text(json.dumps(cache))
    backup(root)
    plan = importer().run(source, output, root, apply=True, limit=1)
    assert plan["stats"]["will_import"] == 1
    assert plan["stats"]["duplicate_cache_files"] == 1
    assert counts(session_factory) == (1, 2)
    with session_factory() as session:
        meta = json.loads(session.scalar(select(Image)).metadata_json)["v1_output"]
        assert len(meta["sources"]) == len(meta["prompts"]) == 2


def test_generated_image_hash_match_is_skipped(sample, session_factory, settings):
    source, output, root = sample
    with session_factory() as session:
        image_service.import_engine_output(session, StorageManager(settings), data=(output / "0.png").read_bytes(), original_filename="original.png", source="comfyui")
    backup(root)
    plan = importer().run(source, output, root, apply=True)
    assert plan["stats"]["existing_matches"] == 1
    assert counts(session_factory) == (3, 2)


def test_missing_outside_and_invalid_files_are_skipped(sample):
    source, output, root = sample
    cache_path = source / "runtime/prompt_cache.json"
    cache = json.loads(cache_path.read_text())
    cache[str(output / "missing.png")] = [1, "missing"]
    cache[str(source / "outside.png")] = [1, "outside"]
    (output / "bad.png").write_bytes(b"not an image")
    cache[str(output / "bad.png")] = [1, "invalid"]
    cache_path.write_text(json.dumps(cache))
    plan = importer().run(source, output, root)
    assert plan["stats"]["missing_files"] == 1
    assert plan["stats"]["outside_root"] == 1
    assert plan["stats"]["invalid_files"] == 1
    assert plan["stats"]["will_import"] == 3


def test_service_failure_rolls_back_all_business_rows(sample, session_factory, monkeypatch):
    source, output, root = sample
    backup(root)
    module = importer()
    original = module.image_service.import_outputs_transaction
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture import failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(module.image_service, "import_outputs_transaction", fail_second)
    with pytest.raises(RuntimeError, match="fixture import failure"):
        module.run(source, output, root, apply=True)
    assert counts(session_factory) == (0, 0)
    results = list((root / "backups").glob("*-result.json"))
    assert json.loads(results[0].read_text(encoding="utf-8"))["status"].startswith("failed")
    # 文件系统不能与 SQLite 一起回滚，按禁止删除约束保留并在日志中定位。
    assert list((root / "images/originals").glob("*/original.png"))


def test_source_change_after_plan_is_refused(sample, session_factory, monkeypatch):
    source, output, root = sample
    backup(root)
    module = importer()
    original = module.apply_plan

    def change_then_apply(plan, data_root, path):
        (output / "0.png").write_bytes(b"changed")
        return original(plan, data_root, path)

    monkeypatch.setattr(module, "apply_plan", change_then_apply)
    with pytest.raises(ValueError, match="扫描后改变"):
        module.run(source, output, root, apply=True)
    assert counts(session_factory) == (0, 0)


def test_plan_write_failure_prevents_apply(sample, session_factory, monkeypatch, capsys):
    source, output, root = sample
    backup(root)
    module = importer()

    def denied(*args, **kwargs):
        raise PermissionError("fixture plan permission denied")

    monkeypatch.setattr(module, "write_exclusive", denied)
    with pytest.raises(PermissionError):
        module.run(source, output, root, apply=True)
    assert counts(session_factory) == (0, 0)
    assert not list((root / "images/originals").glob("*/original.png"))
    assert '"will_import": 3' in capsys.readouterr().out
