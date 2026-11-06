"""W4.1 Prompt Center：统计、legacy 标记与结构化字段只读映射。

不新建 Prompt 表、不改历史版本内容。字段映射只发生在读取投影层：
- face → character
- pose → action
- composition → camera
原始 structured_json 原样保留，不伪造历史修改记录。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Prompt, PromptEvaluation, PromptVersion

FIELD_MAP = {"face": "character", "pose": "action", "composition": "camera"}


def canonical_structured(raw: dict[str, Any]) -> dict[str, Any]:
    """返回 W4.1 标准字段视图，同时保留 raw 原字段。"""
    result = dict(raw)
    for legacy, target in FIELD_MAP.items():
        if legacy in raw and target not in result:
            result[target] = raw[legacy]
    return result


def legacy_import(prompt: Prompt, version: PromptVersion | None) -> bool:
    """无版本记录或带 V1 迁移标记 → legacy_import（不伪造历史）。"""
    if version is None:
        return True
    try:
        structured = json.loads(version.structured_json or "{}")
    except ValueError:
        structured = {}
    return bool(isinstance(structured, dict) and structured.get("_v1_migration"))


def _tags(structured: dict[str, Any]) -> list[str]:
    """标准标签：优先 structured.tags，其次 structured.extra.tags；去重且保持顺序。"""
    raw = structured.get("tags")
    if not isinstance(raw, list):
        extra = structured.get("extra")
        raw = extra.get("tags") if isinstance(extra, dict) else []
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in tags:
            tags.append(text)
    return tags


def latest_evaluation(session: Session, prompt_id: str) -> PromptEvaluation | None:
    return session.execute(
        select(PromptEvaluation)
        .where(PromptEvaluation.prompt_id == prompt_id)
        .order_by(PromptEvaluation.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def prompt_view(
    prompt: Prompt,
    version: PromptVersion | None,
    evaluation: PromptEvaluation | None = None,
) -> dict[str, Any]:
    structured: dict[str, Any] = {}
    if version is not None:
        try:
            parsed = json.loads(version.structured_json or "{}")
            structured = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            structured = {}
    return {
        "prompt_id": prompt.id,
        "version": version.version_no if version is not None else 0,
        "title": prompt.name,
        "category": prompt.status,
        "positive_prompt": version.positive_prompt if version is not None else "",
        "negative_prompt": version.negative_prompt if version is not None else "",
        "structured_fields": canonical_structured(structured),
        "tags": _tags(structured),
        "favorite": bool(prompt.favorite),
        "rating": evaluation.overall_score if evaluation is not None else None,
        "legacy_import": legacy_import(prompt, version),
        "created_at": prompt.created_at,
        "updated_at": prompt.updated_at,
    }


def stats(session: Session) -> dict[str, Any]:
    total = session.execute(select(func.count()).select_from(Prompt)).scalar_one()
    versions = session.execute(select(func.count()).select_from(PromptVersion)).scalar_one()
    favorite = session.execute(
        select(func.count()).select_from(Prompt).where(Prompt.favorite.is_(True))
    ).scalar_one()
    archived = session.execute(
        select(func.count()).select_from(Prompt).where(Prompt.archived.is_(True))
    ).scalar_one()
    by_status = dict(session.execute(select(Prompt.status, func.count()).group_by(Prompt.status)).all())
    evaluations = session.execute(select(func.count()).select_from(PromptEvaluation)).scalar_one()
    without_version = session.execute(text(
        "SELECT count(*) FROM prompts p WHERE NOT EXISTS "
        "(SELECT 1 FROM prompt_versions v WHERE v.prompt_id = p.id)"
    )).scalar_one()
    multi_version = session.execute(text(
        "SELECT count(*) FROM (SELECT prompt_id FROM prompt_versions GROUP BY prompt_id HAVING count(*) > 1)"
    )).scalar_one()

    links = session.execute(text("""
        SELECT prompt_id, count(*) AS n FROM (
          SELECT json_extract(j.workbench_snapshot_json, '$.source_prompt_id') AS prompt_id
          FROM images i JOIN jobs j ON i.job_id = j.id
          WHERE json_extract(j.workbench_snapshot_json, '$.source_prompt_id') IS NOT NULL
          UNION ALL
          SELECT jv.value ->> '$.prompt_id' AS prompt_id
          FROM images i, json_each(i.metadata_json, '$.v1_output.prompts') jv
          WHERE i.source = 'import' AND i.metadata_json LIKE '%v1_output%'
        ) GROUP BY prompt_id
    """)).mappings().all()
    linked_prompts = len(links)
    link_total = sum(int(row["n"]) for row in links)
    prompt_ids = {row[0] for row in session.execute(select(Prompt.id))}
    invalid_links = sum(int(row["n"]) for row in links if row["prompt_id"] not in prompt_ids)

    return {
        "prompts_total": total,
        "prompt_versions_total": versions,
        "prompts_without_versions": without_version,
        "prompts_multi_version": multi_version,
        "favorite": favorite,
        "archived": archived,
        "by_status": by_status,
        "evaluations": evaluations,
        "prompts_with_images": linked_prompts,
        "prompts_without_images": total - linked_prompts,
        "image_links_total": link_total,
        "invalid_image_links": invalid_links,
        "field_map": FIELD_MAP,
    }
