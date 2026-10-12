"""Phase 0.11 — 合成测试图库播种（性能 / 审核 / 清理验收，独立临时 DataRoot）。

在 worktree 根用 phase011 venv 运行：
  .venv\\Scripts\\python.exe scripts/e2e/phase011_seed.py --root temp/phase011_e2e_data --count 1000

做什么：
- 在独立 DataRoot 初始化目录与数据库（含迁移 0015/0016）；
- 生成 N 张合成 original PNG（尺寸/画幅多样、时间分布、状态按规则分布），
  **只写 original + images 行、不生成 thumbnail** —— 模拟"历史无缩略图"，
  以便在浏览时验证 thumbnail 按需生成与无限滚动；
- 预置约 100 张 REJECT，并让其中 2 张分别被 Prompt 封面 / Asset 溯源引用，
  用于验证"清理废片"时被引用图受保护（预期 100 张 REJECT 删 98、保护 2）。

不触碰正式 DataRoot；全部为合成数据，不含真实图片 / 用户 Prompt。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw

DIM_POOL = [
    (768, 1024),
    (1216, 832),
    (1024, 1024),
    (640, 896),
    (896, 640),
    (832, 1216),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="temp/phase011_e2e_data")
    p.add_argument("--count", type=int, default=1000)
    return p.parse_args()


def status_for(i: int) -> str:
    if i % 100 == 3:
        return "FAVORITE"  # 10
    if i % 50 == 9:
        return "ARCHIVED"  # 20
    if i % 10 == 7:
        return "REJECT"  # 100
    if i % 10 in (1, 2):
        return "KEEP"  # 200
    return "NEW"  # 其余 670


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def make_picture(width: int, height: int, i: int) -> bytes:
    import colorsys
    from io import BytesIO

    hue = (i * 0.05) % 1.0
    top = colorsys.hsv_to_rgb(hue, 0.55, 0.9)
    bottom = colorsys.hsv_to_rgb((hue + 0.12) % 1.0, 0.65, 0.65)
    th = tuple(int(round(c * 255)) for c in top)
    bh = tuple(int(round(c * 255)) for c in bottom)
    # 1×256 渐变条 → 放大到目标尺寸（C 层 resize，避免逐像素百万次循环）
    strip = PILImage.new("RGB", (1, 256))
    sp = strip.load()
    for y in range(256):
        t = y / 255
        sp[0, y] = tuple(int(th[c] * (1 - t) + bh[c] * t) for c in range(3))
    img = strip.resize((width, height), PILImage.BILINEAR)
    draw = ImageDraw.Draw(img)
    # 几个确定性形状 + 序号，便于目检区分
    draw.rectangle([width * 0.1, height * 0.2, width * 0.4, height * 0.7],
                   outline=(255, 255, 255), width=4)
    draw.ellipse([width * 0.55, height * 0.25, width * 0.85, height * 0.75], fill=(20, 20, 20))
    draw.text((width * 0.05, height * 0.86), f"seed #{i}", fill=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    os.environ["NSFW_STUDIO_DATA_ROOT"] = str(root)

    from sqlalchemy import text

    from app.core.config import load_settings
    from app.database.base import init_database, make_engine
    from app.storage.manager import StorageManager

    settings = load_settings()
    storage = StorageManager(settings)
    storage.ensure()
    engine = make_engine(settings.storage.database_path)
    init_database(engine)

    now = datetime.now()
    counts: dict[str, int] = {}
    reject_ids: list[str] = []

    rows = []
    for i in range(args.count):
        width, height = DIM_POOL[i % len(DIM_POOL)]
        data = make_picture(width, height, i)
        image_id = f"img_seed_{i:05d}"
        final_dir = storage.resolve_under("images/originals", image_id)
        final_dir.mkdir(parents=True, exist_ok=True)
        file_path = final_dir / "original.png"
        file_path.write_bytes(data)
        rel = storage.relative_to_root(file_path)
        status = status_for(i)
        counts[status] = counts.get(status, 0) + 1
        if status == "REJECT":
            reject_ids.append(image_id)
        created = now - timedelta(minutes=(args.count - i))  # i 越大越新
        favorite = 1 if status == "FAVORITE" else 0
        reviewed = iso(now) if status != "NEW" else None
        rows.append({
            "id": image_id, "file_path": rel, "width": width, "height": height,
            "status": status, "favorite": favorite, "created_at": iso(created),
            "updated_at": iso(created), "reviewed_at": reviewed,
        })

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text(
                "INSERT INTO images (id,job_id,job_item_id,parent_image_id,kind,file_path,width,height,seed,"
                "review_status,favorite,source,sha256,imported_filename,status,reviewed_at,review_note,"
                "metadata_json,created_at,updated_at) "
                "VALUES (:id,NULL,NULL,NULL,'original',:file_path,:width,:height,NULL,'UNREVIEWED',"
                ":favorite,'mock',NULL,NULL,:status,:reviewed_at,'{}','{}',:created_at,:updated_at)"
            ), r)

    # 引用保护演示：让前两张 REJECT 分别被 Prompt 封面 / Asset 溯源引用（数量不足则降级）
    protected: list[str] = []
    prompt_cover = reject_ids[0] if len(reject_ids) >= 1 else None
    asset_source = reject_ids[1] if len(reject_ids) >= 2 else None
    with engine.begin() as conn:
        if prompt_cover is not None:
            conn.execute(text(
                "INSERT INTO prompts (id,name,current_version_id,favorite,archived,preview_image_id,created_at,updated_at) "
                "VALUES ('prompt_protect_demo','保护演示-Prompt','pv_demo',0,0,:cover,:t,:t)"
            ), {"cover": prompt_cover, "t": iso(now)})
            conn.execute(text(
                "INSERT INTO prompt_versions (id,prompt_id,version_no,mode,positive_prompt,negative_prompt,"
                "structured_json,created_at) VALUES ('pv_demo','prompt_protect_demo',1,'structured','演示',"
                "'(无)','{}',:t)"
            ), {"t": iso(now)})
            protected.append(prompt_cover)
        if asset_source is not None:
            conn.execute(text(
                "INSERT INTO assets (id,type,name,current_version_id,favorite,archived,source_image_id,"
                "created_at,updated_at) VALUES ('asset_protect_demo','face','保护演示-Asset',NULL,0,0,"
                ":src,:t,:t)"
            ), {"src": asset_source, "t": iso(now)})
            protected.append(asset_source)

    # 演示 Job/Recipe/Prompt（模块5 Job 审核入口 + 模块9 详情溯源）：
    # 用 ORM 建一套完整链路，并把最新的 16 张 NEW 图挂到该 Job（全部未审核）。
    from sqlalchemy.orm import Session as _Session
    from app.models.prompt import Prompt as _Prompt, PromptVersion as _PV
    from app.models.recipe import Recipe as _Recipe, RecipeVersion as _RV
    from app.models.job import Job as _Job, JobItem as _JI
    from app.models.image import Image as _Image

    pos_text = "masterpiece, best quality, 1girl, portrait, soft studio lighting, detailed eyes"
    neg_text = "lowres, bad anatomy, worst quality"
    with _Session(bind=engine) as s:
        s.add(_Prompt(id="prompt_demo", name="演示-Prompt（可复制）", current_version_id="pv_demo_job"))
        s.add(_PV(id="pv_demo_job", prompt_id="prompt_demo", version_no=1, mode="structured",
                  positive_prompt=pos_text, negative_prompt=neg_text, structured_json="{}"))
        s.add(_Recipe(id="recipe_demo", name="演示-配方", current_version_id="rv_demo"))
        s.add(_RV(id="rv_demo", recipe_id="recipe_demo", version_no=1, prompt_mode="structured",
                  positive_prompt_snapshot=pos_text, negative_prompt_snapshot=neg_text,
                  structured_prompt_snapshot="{}", source_prompt_id="prompt_demo",
                  source_prompt_version_id="pv_demo_job",
                  generation_settings_json='{"width":1024,"height":1024}',
                  workflow_snapshot_json='{"modules":[]}', input_images_json="[]", default_count=1))
        s.add(_Job(id="job_demo", source="web", client_request_id="demo_req_001", status="COMPLETED",
                   prompt_mode="structured", positive_prompt_snapshot=pos_text,
                   negative_prompt_snapshot=neg_text, structured_prompt_snapshot="{}",
                   workbench_snapshot_json="{}",
                   generation_settings_json='{"width":1024,"height":1024}',
                   workflow_snapshot_json='{"modules":[]}', module_id="anime_generate",
                   module_version="1.0.0", provider="comfyui", requested_count=16,
                   completed_count=16, job_kind="generate",
                   started_at=iso(now - timedelta(minutes=20)),
                   finished_at=iso(now - timedelta(minutes=5))))
        s.flush()  # 确保 job 行已存在
        linked = s.query(_Image).filter(_Image.status == "NEW") \
            .order_by(_Image.created_at.desc()).limit(16).all()
        assert len(linked) == 16, f"need 16 NEW, got {len(linked)}"
        for n, img in enumerate(linked):
            ji = _JI(id=f"ji_demo_{n:02d}", job_id="job_demo", item_index=n,
                     status="COMPLETED", seed=1000 + n, image_id=img.id)
            s.add(ji)
            img.job_id = "job_demo"
            img.seed = 1000 + n
        s.flush()  # 先插入 job_items，再回填 image.job_item_id（满足外键顺序）
        for n, img in enumerate(linked):
            img.job_item_id = f"ji_demo_{n:02d}"
        s.commit()
        linked_ids = [img.id for img in linked]

    print("DataRoot:", root)
    print("status counts:", json.dumps(counts, ensure_ascii=False, sort_keys=True))
    print("REJECT total:", len(reject_ids))
    print("protected REJECT (prompt cover / asset source):", protected)
    print("expected cleanup: deleted =", len(reject_ids) - len(protected),
          "protected =", len(protected))
    print("demo job: job_demo, linked 16 NEW images:", linked_ids[:4], "...")


if __name__ == "__main__":
    main()
