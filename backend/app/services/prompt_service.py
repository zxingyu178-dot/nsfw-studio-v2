"""PromptService（Phase 1 规范 §六、§七、§十一、§三十二、§五十五-§五十七）。

规则：
- 内容（正向/负向/结构化/模式）任何变化 → 新 PromptVersion；元数据（名称/收藏/归档）不建版本；
- 版本 immutable：禁止 UPDATE 版本内容，修改只能 INSERT 新版本；
- 恢复旧版本 = 复制其内容创建最新版（历史永远线性）；
- 创建/更新均为单事务，任何一步失败全部回滚。
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ids import PROMPT, PROMPT_VERSION, new_id
from app.models import Prompt, PromptEvaluation, PromptVersion
from app.services import image_service
from app.services.prompt_composer import compose_structured, dumps_structured

PROMPT_MODES = ("structured", "full")
LIST_SORTS = ("updated_desc", "score_desc", "score_asc")


def get_prompt(session: Session, prompt_id: str) -> Prompt:
    prompt = session.get(Prompt, prompt_id)
    if prompt is None:
        raise NotFoundError("Prompt 不存在", code="PROMPT_NOT_FOUND")
    return prompt


def get_current_version(session: Session, prompt: Prompt) -> PromptVersion | None:
    if prompt.current_version_id is None:
        return None
    return session.get(PromptVersion, prompt.current_version_id)


def _next_version_no(session: Session, prompt_id: str) -> int:
    current_max = session.execute(
        select(func.max(PromptVersion.version_no)).where(PromptVersion.prompt_id == prompt_id)
    ).scalar_one()
    return (current_max or 0) + 1


def create_prompt(
    session: Session,
    *,
    name: str,
    mode: str,
    positive_prompt: str = "",
    negative_prompt: str = "",
    structured: dict | None = None,
    favorite: bool = False,
    commit: bool = True,
) -> Prompt:
    """创建 Prompt + v1。

    ``commit=False`` 时只 flush，不提交：供 Job 创建在同一事务内统一提交
    （W1.2.1 事务修复）；对外部独立创建接口保持默认 commit=True。
    """
    if not name or not name.strip():
        raise ValidationError("Prompt 名称不能为空")
    if mode not in PROMPT_MODES:
        raise ValidationError(f"非法 Prompt 模式: {mode}", code="PROMPT_MODE_INVALID")

    now_prompt = Prompt(
        id=new_id(PROMPT),
        name=name.strip(),
        favorite=favorite,
        archived=False,
    )
    mode, positive, negative, structured_json = _content_fields(mode, positive_prompt, negative_prompt, structured)
    version = PromptVersion(
        id=new_id(PROMPT_VERSION),
        prompt_id=now_prompt.id,
        version_no=1,
        mode=mode,
        positive_prompt=positive,
        negative_prompt=negative,
        structured_json=structured_json,
    )
    now_prompt.current_version_id = version.id
    try:
        session.add(now_prompt)
        session.add(version)
        if commit:
            session.commit()
        else:
            session.flush()
    except IntegrityError:
        session.rollback()
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return now_prompt


def update_prompt_meta(
    session: Session,
    prompt_id: str,
    *,
    name: str | None = None,
    favorite: bool | None = None,
) -> Prompt:
    """元数据修改（名称/收藏）：不创建内容版本（规范 §十一）。"""
    prompt = get_prompt(session, prompt_id)
    if name is not None:
        if not name.strip():
            raise ValidationError("Prompt 名称不能为空")
        prompt.name = name.strip()
    if favorite is not None:
        prompt.favorite = favorite
    session.commit()
    return prompt


def set_preview_image(session: Session, prompt_id: str, image_id: str) -> Prompt:
    """设置 / 更换封面预览图：属【元数据】，绝不创建 PromptVersion（规范 §十一）。"""
    prompt = get_prompt(session, prompt_id)
    image_service.get_image(session, image_id)  # 图片不存在 → IMAGE_NOT_FOUND
    prompt.preview_image_id = image_id
    session.commit()
    return prompt


def clear_preview_image(session: Session, prompt_id: str) -> Prompt:
    """清除封面预览图：置 None，不创建 PromptVersion。"""
    prompt = get_prompt(session, prompt_id)
    prompt.preview_image_id = None
    session.commit()
    return prompt


def _content_fields(
    mode: str, positive_prompt: str, negative_prompt: str, structured: dict | None
) -> tuple[str, str, str, str]:
    """归一化内容四元组；结构化模式下正向 Prompt 由后端权威合成（规范 §九）。"""
    if mode not in PROMPT_MODES:
        raise ValidationError(f"非法 Prompt 模式: {mode}", code="PROMPT_MODE_INVALID")
    if mode == "structured":
        positive = positive_prompt or compose_structured(structured)
    else:
        positive = positive_prompt or ""
    return (mode, positive, negative_prompt or "", dumps_structured(structured))


def assign_ai_prompt(
    session: Session, *, positive_prompt: str, negative_prompt: str = "", name: str | None = None,
    commit: bool = True,
) -> tuple[Prompt, PromptVersion, bool]:
    """AI/Agent 提交前的提示词入库保证：同一段提示词已有则复用，否则建 Prompt + v1。

    判定同一段提示词 = 「mode=full + 正向 + 反向」完全一致（且未归档）；
    避免 AI 每次提交都在库里堆重复条目，同时保证生成图始终能在提示词库追溯。
    返回 (prompt, version, created)。

    ``commit=False``：只 flush，由调用方（JobService 创建事务）最终统一提交。
    """
    positive = (positive_prompt or "").strip()
    negative = (negative_prompt or "").strip()
    if not positive:
        raise ValidationError("提示词不能为空", code="PROMPT_EMPTY")
    existing = session.execute(
        select(Prompt, PromptVersion)
        .join(PromptVersion, PromptVersion.prompt_id == Prompt.id)
        .where(
            Prompt.archived.is_(False),
            PromptVersion.mode == "full",
            PromptVersion.positive_prompt == positive,
            PromptVersion.negative_prompt == negative,
        )
        .order_by(PromptVersion.version_no.desc())
        .limit(1)
    ).first()
    if existing is not None:
        return existing[0], existing[1], False
    prompt = create_prompt(
        session, name=(name or positive[:24]), mode="full",
        positive_prompt=positive, negative_prompt=negative, commit=commit,
    )
    version = get_current_version(session, prompt)
    if version is None:  # create_prompt 必然建 v1；这里只是类型收敛，不做兜底逻辑
        raise ValidationError("提示词版本创建失败", code="PROMPT_VERSION_MISSING")
    return prompt, version, True


def attach_ai_prompt(session: Session, snapshot: dict, *, commit: bool = False) -> None:
    """为 AI / CLI 提交的工作台快照补充 source_prompt_id / source_prompt_version_id。

    默认 ``commit=False``：Prompt 与 Job 在同一事务内创建，由 JobService 统一提交；
    任一后续校验失败时调用方 rollback，不留下孤立 Prompt（W1.2.1）。
    """
    if snapshot.get("source_prompt_id"):
        return
    if (snapshot.get("prompt_mode") or "full") == "structured":
        positive = compose_structured(snapshot.get("structured_prompt") or {})
    else:
        positive = snapshot.get("full_prompt") or ""
    prompt, version, _created = assign_ai_prompt(
        session,
        positive_prompt=positive,
        negative_prompt=snapshot.get("negative_prompt") or "",
        commit=commit,
    )
    snapshot["source_prompt_id"] = prompt.id
    snapshot["source_prompt_version_id"] = version.id


def add_prompt_version(
    session: Session,
    prompt_id: str,
    *,
    mode: str,
    positive_prompt: str = "",
    negative_prompt: str = "",
    structured: dict | None = None,
) -> tuple[PromptVersion, bool]:
    """内容变化 → 新版本并更新 current_version_id；与当前版本完全一致 → 不建新版本。"""
    prompt = get_prompt(session, prompt_id)
    mode, positive, negative, structured_json = _content_fields(mode, positive_prompt, negative_prompt, structured)

    current = get_current_version(session, prompt)
    if current is not None and (
        current.mode == mode
        and current.positive_prompt == positive
        and current.negative_prompt == negative
        and current.structured_json == structured_json
    ):
        return current, False  # 内容无变化，不产生冗余版本

    version = PromptVersion(
        id=new_id(PROMPT_VERSION),
        prompt_id=prompt.id,
        version_no=_next_version_no(session, prompt.id),
        mode=mode,
        positive_prompt=positive,
        negative_prompt=negative,
        structured_json=structured_json,
    )
    prompt.current_version_id = version.id
    try:
        session.add(version)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return version, True


def restore_prompt_version(session: Session, prompt_id: str, version_id: str) -> PromptVersion:
    """恢复旧版本：复制其内容创建**新的最新版**（current_version 指针不倒退，规范 §五十五）。"""
    prompt = get_prompt(session, prompt_id)
    old = session.get(PromptVersion, version_id)
    if old is None or old.prompt_id != prompt.id:
        raise NotFoundError("Prompt 版本不存在", code="PROMPT_VERSION_NOT_FOUND")

    version = PromptVersion(
        id=new_id(PROMPT_VERSION),
        prompt_id=prompt.id,
        version_no=_next_version_no(session, prompt.id),
        mode=old.mode,
        positive_prompt=old.positive_prompt,
        negative_prompt=old.negative_prompt,
        structured_json=old.structured_json,
    )
    prompt.current_version_id = version.id
    try:
        session.add(version)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return version


def list_versions(session: Session, prompt_id: str) -> list[PromptVersion]:
    prompt = get_prompt(session, prompt_id)
    return list(
        session.execute(
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt.id)
            .order_by(PromptVersion.version_no.desc())
        ).scalars()
    )


def get_version(session: Session, prompt_id: str, version_id: str) -> PromptVersion:
    version = session.get(PromptVersion, version_id)
    if version is None or version.prompt_id != prompt_id:
        raise NotFoundError("Prompt 版本不存在", code="PROMPT_VERSION_NOT_FOUND")
    return version


def list_prompts(
    session: Session,
    *,
    search: str | None = None,
    favorite: bool | None = None,
    archived: bool | None = False,
    limit: int = 50,
    offset: int = 0,
    sort: str = "updated_desc",
    status: Sequence[str] | None = None,
    scored: bool | None = None,
) -> tuple[list[Prompt], int]:
    """列表统一筛选、排序与分页（规范 §三十五）。"""
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    if offset < 0:
        raise ValidationError("offset 不能为负")
    if sort not in LIST_SORTS:
        raise ValidationError("sort 仅支持 updated_desc / score_desc / score_asc")

    filters = []
    if archived is not None:
        filters.append(Prompt.archived == archived)
    if favorite is not None:
        filters.append(Prompt.favorite == favorite)
    if status:
        filters.append(Prompt.status.in_(status))
    if scored is not None:
        evaluation_exists = select(1).where(
            PromptEvaluation.prompt_id == Prompt.id,
        ).exists()
        filters.append(evaluation_exists if scored else ~evaluation_exists)
    if search:
        like = f"%{search.strip()}%"
        # 必须选 prompt_id：与 Prompt.id 比较（此前误选 PromptVersion.id，导致内容搜索永不命中）
        version_match = select(PromptVersion.prompt_id).where(
            PromptVersion.prompt_id == Prompt.id,
            PromptVersion.positive_prompt.like(like),
        )
        filters.append(or_(Prompt.name.like(like), Prompt.id.in_(version_match)))

    total = session.execute(
        select(func.count()).select_from(Prompt).where(*filters),
    ).scalar_one()
    query = select(Prompt).where(*filters)
    if sort in ("score_desc", "score_asc"):
        ranked = select(
            PromptEvaluation.prompt_id.label("prompt_id"),
            PromptEvaluation.overall_score.label("overall_score"),
            func.row_number().over(
                partition_by=PromptEvaluation.prompt_id,
                order_by=(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc()),
            ).label("position"),
        ).subquery()
        latest = select(
            ranked.c.prompt_id, ranked.c.overall_score,
        ).where(ranked.c.position == 1).subquery()
        score_order = (
            latest.c.overall_score.desc()
            if sort == "score_desc"
            else latest.c.overall_score.asc()
        )
        query = query.outerjoin(latest, latest.c.prompt_id == Prompt.id).order_by(
            case((latest.c.overall_score.is_(None), 1), else_=0),
            score_order,
            Prompt.updated_at.desc(),
            Prompt.id.desc(),
        )
    else:
        query = query.order_by(Prompt.updated_at.desc(), Prompt.id.desc())
    items = list(session.execute(query.limit(limit).offset(offset)).scalars())
    return items, int(total)


def set_archived(session: Session, prompt_id: str, archived: bool) -> Prompt:
    """软删除 / 恢复（规范 §五十四）：禁止普通 UI 物理删除。"""
    prompt = get_prompt(session, prompt_id)
    prompt.archived = archived
    session.commit()
    return prompt
