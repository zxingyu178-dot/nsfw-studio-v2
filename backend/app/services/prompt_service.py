"""PromptService（Phase 1 规范 §六、§七、§十一、§三十二、§五十五-§五十七）。

规则：
- 内容（正向/负向/结构化/模式）任何变化 → 新 PromptVersion；元数据（名称/收藏/归档）不建版本；
- 版本 immutable：禁止 UPDATE 版本内容，修改只能 INSERT 新版本；
- 恢复旧版本 = 复制其内容创建最新版（历史永远线性）；
- 创建/更新均为单事务，任何一步失败全部回滚。
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ids import PROMPT, PROMPT_VERSION, new_id
from app.models import Prompt, PromptVersion
from app.services.prompt_composer import compose_structured, dumps_structured

PROMPT_MODES = ("structured", "full")


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
) -> Prompt:
    """创建 Prompt + v1（单事务）。"""
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
        session.commit()
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
) -> tuple[list[Prompt], int]:
    """列表统一参数：search / favorite / archived / limit / offset（规范 §三十五）。"""
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    if offset < 0:
        raise ValidationError("offset 不能为负")

    query = select(Prompt)
    if archived is None:
        pass  # 不过滤
    else:
        query = query.where(Prompt.archived == archived)
    if favorite is not None:
        query = query.where(Prompt.favorite == favorite)
    if search:
        like = f"%{search.strip()}%"
        current_version = select(PromptVersion.id).where(
            PromptVersion.prompt_id == Prompt.id,
            PromptVersion.positive_prompt.like(like),
        )
        query = query.where(or_(Prompt.name.like(like), Prompt.id.in_(current_version)))

    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = list(
        session.execute(query.order_by(Prompt.updated_at.desc()).limit(limit).offset(offset)).scalars()
    )
    return items, int(total)


def set_archived(session: Session, prompt_id: str, archived: bool) -> Prompt:
    """软删除 / 恢复（规范 §五十四）：禁止普通 UI 物理删除。"""
    prompt = get_prompt(session, prompt_id)
    prompt.archived = archived
    session.commit()
    return prompt
