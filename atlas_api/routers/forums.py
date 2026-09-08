import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import WorldAccess, world_access
from ..errors import AtlasError
from ..models import AuditEvent, ForumPost, ForumSpace, ForumTopic, Notification, WorldMembership, WorldRole
from ..schemas import ForumSpaceCreate, PostCreate, PostUpdate, TopicCreate, TopicUpdate

router = APIRouter(tags=["forums"])


@router.get("/worlds/{world_id}/forums")
async def forum_index(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    spaces = (await session.scalars(select(ForumSpace).where(ForumSpace.world_id == access.world.id).order_by(ForumSpace.position, ForumSpace.created_at))).all()
    return {"items": [{"id": str(item.id), "name": item.name, "description": item.description, "position": item.position} for item in spaces]}


@router.post("/worlds/{world_id}/forums", status_code=201)
async def create_space(body: ForumSpaceCreate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage(); access.require_write()
    if await session.scalar(select(ForumSpace.id).where(ForumSpace.world_id == access.world.id, ForumSpace.name == body.name)):
        raise AtlasError(409, "FORUM_SPACE_EXISTS", "同名论坛分区已存在")
    item = ForumSpace(world_id=access.world.id, created_by=access.user.id, **body.model_dump())
    session.add(item); await session.commit(); await session.refresh(item)
    return {"id": str(item.id), "name": item.name, "description": item.description, "position": item.position}


@router.get("/worlds/{world_id}/topics")
async def list_topics(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session), space_id: uuid.UUID | None = None) -> dict:
    counts = select(ForumPost.topic_id, func.count().label("replies")).where(ForumPost.deleted_at.is_(None)).group_by(ForumPost.topic_id).subquery()
    query = select(ForumTopic, func.coalesce(counts.c.replies, 0)).outerjoin(counts, counts.c.topic_id == ForumTopic.id).where(ForumTopic.world_id == access.world.id, ForumTopic.deleted_at.is_(None))
    if space_id: query = query.where(ForumTopic.space_id == space_id)
    rows = (await session.execute(query.order_by(ForumTopic.is_pinned.desc(), ForumTopic.updated_at.desc()))).all()
    return {"items": [{"id": str(item.id), "spaceID": str(item.space_id), "authorID": str(item.author_id), "title": item.title, "body": item.body, "isPinned": item.is_pinned, "isLocked": item.is_locked, "revision": item.revision, "replies": count} for item, count in rows]}


@router.post("/worlds/{world_id}/topics", status_code=201)
async def create_topic(body: TopicCreate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    try: space_id = uuid.UUID(body.space_id)
    except ValueError: raise AtlasError(422, "FORUM_SPACE_ID_INVALID", "论坛分区 ID 无效") from None
    space = await session.get(ForumSpace, space_id)
    if not space or space.world_id != access.world.id: raise AtlasError(404, "FORUM_SPACE_NOT_FOUND", "论坛分区不存在")
    item = ForumTopic(world_id=access.world.id, space_id=space_id, author_id=access.user.id, title=body.title, body=body.body)
    session.add(item); await session.commit(); await session.refresh(item)
    return {"id": str(item.id), "revision": item.revision}


@router.patch("/worlds/{world_id}/topics/{topic_id}")
async def update_topic(topic_id: uuid.UUID, body: TopicUpdate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    item = await session.scalar(select(ForumTopic).where(ForumTopic.id == topic_id, ForumTopic.world_id == access.world.id, ForumTopic.deleted_at.is_(None)).with_for_update())
    if not item: raise AtlasError(404, "TOPIC_NOT_FOUND", "主题不存在")
    manager = access.role in {WorldRole.owner, WorldRole.manager} or access.user.role.value == "admin"
    if item.author_id != access.user.id and not manager: raise AtlasError(403, "TOPIC_EDIT_FORBIDDEN", "无权编辑该主题")
    if item.revision != body.expected_revision: raise AtlasError(409, "REVISION_CONFLICT", "主题已更新", {"currentRevision": item.revision})
    if (body.is_pinned is not None or body.is_locked is not None) and not manager: raise AtlasError(403, "TOPIC_MODERATE_FORBIDDEN", "只有企划管理者可以置顶或锁定")
    for key, value in body.model_dump(exclude_none=True, exclude={"expected_revision"}).items(): setattr(item, key, value)
    item.revision += 1; await session.commit()
    return {"id": str(item.id), "revision": item.revision, "isPinned": item.is_pinned, "isLocked": item.is_locked}


@router.delete("/worlds/{world_id}/topics/{topic_id}", status_code=204)
async def delete_topic(topic_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> None:
    access.require_write()
    item = await session.get(ForumTopic, topic_id)
    manager = access.role in {WorldRole.owner, WorldRole.manager} or access.user.role.value == "admin"
    if not item or item.world_id != access.world.id or item.deleted_at: raise AtlasError(404, "TOPIC_NOT_FOUND", "主题不存在")
    if item.author_id != access.user.id and not manager: raise AtlasError(403, "TOPIC_DELETE_FORBIDDEN", "无权删除该主题")
    item.deleted_at = datetime.now(UTC); await session.commit()


@router.get("/worlds/{world_id}/topics/{topic_id}/posts")
async def list_posts(topic_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    topic = await session.get(ForumTopic, topic_id)
    if not topic or topic.world_id != access.world.id or topic.deleted_at: raise AtlasError(404, "TOPIC_NOT_FOUND", "主题不存在")
    posts = (await session.scalars(select(ForumPost).where(ForumPost.topic_id == topic_id).order_by(ForumPost.created_at))).all()
    return {"items": [{"id": str(item.id), "authorID": str(item.author_id), "body": None if item.deleted_at else item.body, "deleted": item.deleted_at is not None, "revision": item.revision, "createdAt": item.created_at.isoformat()} for item in posts]}


@router.post("/worlds/{world_id}/topics/{topic_id}/posts", status_code=201)
async def create_post(topic_id: uuid.UUID, body: PostCreate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    topic = await session.get(ForumTopic, topic_id)
    if not topic or topic.world_id != access.world.id or topic.deleted_at: raise AtlasError(404, "TOPIC_NOT_FOUND", "主题不存在")
    if topic.is_locked: raise AtlasError(409, "TOPIC_LOCKED", "主题已锁定")
    post = ForumPost(topic_id=topic_id, author_id=access.user.id, body=body.body)
    session.add(post); await session.flush()
    if topic.author_id != access.user.id:
        session.add(Notification(recipient_user_id=topic.author_id, world_id=access.world.id, type="forum.reply", title=f"你的主题收到回复：{topic.title}", summary=body.body[:240], dedupe_key=f"forum-reply:{post.id}", action_type="forum-topic", action_target=str(topic.id)))
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="forum.post.created", target_type="forum_post", target_id=str(post.id)))
    await session.commit(); await session.refresh(post)
    return {"id": str(post.id), "revision": post.revision}


@router.patch("/worlds/{world_id}/posts/{post_id}")
async def update_post(post_id: uuid.UUID, body: PostUpdate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    post = await session.scalar(select(ForumPost).where(ForumPost.id == post_id).with_for_update())
    topic = await session.get(ForumTopic, post.topic_id) if post else None
    if not post or not topic or topic.world_id != access.world.id or post.deleted_at: raise AtlasError(404, "POST_NOT_FOUND", "回复不存在")
    if post.author_id != access.user.id: raise AtlasError(403, "POST_EDIT_FORBIDDEN", "只能编辑自己的回复")
    if post.revision != body.expected_revision: raise AtlasError(409, "REVISION_CONFLICT", "回复已更新", {"currentRevision": post.revision})
    post.body, post.revision = body.body, post.revision + 1; await session.commit()
    return {"id": str(post.id), "revision": post.revision}


@router.delete("/worlds/{world_id}/posts/{post_id}", status_code=204)
async def delete_post(post_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> None:
    access.require_write()
    post = await session.get(ForumPost, post_id); topic = await session.get(ForumTopic, post.topic_id) if post else None
    manager = access.role in {WorldRole.owner, WorldRole.manager} or access.user.role.value == "admin"
    if not post or not topic or topic.world_id != access.world.id or post.deleted_at: raise AtlasError(404, "POST_NOT_FOUND", "回复不存在")
    if post.author_id != access.user.id and not manager: raise AtlasError(403, "POST_DELETE_FORBIDDEN", "无权删除该回复")
    post.deleted_at = datetime.now(UTC); await session.commit()

