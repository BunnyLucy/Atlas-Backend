import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import WorldAccess, current_user, world_access
from ..errors import AtlasError
from ..models import AuditEvent, CanvasDocument, CanvasRevision, User, WikiRevision, World, WorldMap, WorldMembership, WorldObject, WorldRole
from ..schemas import CanvasPut, MapPut, WikiPut, WorldCreate, WorldUpdate
from ..serialization import world_payload

router = APIRouter(prefix="/worlds", tags=["worlds"])


@router.get("")
async def list_worlds(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict:
    query = (
        select(World, WorldMembership.role)
        .outerjoin(WorldMembership, and_(WorldMembership.world_id == World.id, WorldMembership.user_id == user.id))
        .where(or_(WorldMembership.user_id == user.id, World.visibility == "public"))
        .order_by(World.updated_at.desc(), World.id)
        .limit(limit + 1)
    )
    if cursor:
        try:
            timestamp, world_id = cursor.split("|", 1)
            at = datetime.fromisoformat(timestamp)
        except ValueError:
            raise AtlasError(400, "CURSOR_INVALID", "分页游标无效") from None
        query = query.where(or_(World.updated_at < at, and_(World.updated_at == at, World.id > world_id)))
    rows = (await session.execute(query)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = f"{rows[-1][0].updated_at.isoformat()}|{rows[-1][0].id}" if has_more and rows else None
    return {"items": [world_payload(world, role.value if role else None) for world, role in rows], "nextCursor": next_cursor}


@router.post("", status_code=201)
async def create_world(body: WorldCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    exists = await session.scalar(select(World.id).where(or_(World.id == body.id, World.slug == body.slug)))
    if exists:
        raise AtlasError(409, "WORLD_EXISTS", "企划 ID 或 slug 已存在")
    world = World(owner_id=user.id, **body.model_dump())
    session.add(world)
    # Establish the FK target before membership and audit rows are flushed.
    await session.flush()
    session.add(WorldMembership(world_id=world.id, user_id=user.id, role=WorldRole.owner))
    session.add(AuditEvent(actor_id=user.id, world_id=world.id, action="world.created", target_type="world", target_id=world.id))
    await session.commit()
    await session.refresh(world)
    return world_payload(world, WorldRole.owner.value)


@router.get("/{world_id}")
async def get_world(access: WorldAccess = Depends(world_access)) -> dict:
    return world_payload(access.world, access.role.value if access.role else None)


@router.patch("/{world_id}")
async def update_world(body: WorldUpdate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    access.require_write()
    world = await session.scalar(select(World).where(World.id == access.world.id).with_for_update())
    assert world
    if world.revision != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "企划已在其他设备更新", {"currentRevision": world.revision})
    for key, value in body.model_dump(exclude_none=True, exclude={"expected_revision"}).items():
        setattr(world, key, value)
    world.revision += 1
    session.add(AuditEvent(actor_id=access.user.id, world_id=world.id, action="world.updated", target_type="world", target_id=world.id))
    await session.commit()
    await session.refresh(world)
    return world_payload(world, access.role.value if access.role else None)


@router.get("/{world_id}/canvas")
async def get_canvas(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    record = await session.get(CanvasDocument, access.world.id)
    if not record:
        return {"document": {"objects": [], "relations": []}, "schemaVersion": 1, "revision": 0, "updatedAt": None}
    return {"document": record.document, "schemaVersion": record.schema_version, "revision": record.revision, "updatedAt": record.updated_at.isoformat()}


@router.get("/{world_id}/map")
async def get_map(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    record = await session.get(WorldMap, access.world.id)
    if not record:
        return {"archive": {}, "schemaVersion": 1, "revision": 0, "updatedAt": None}
    return {"archive": record.archive, "schemaVersion": record.schema_version, "revision": record.revision, "updatedAt": record.updated_at.isoformat()}


@router.put("/{world_id}/map")
async def put_map(body: MapPut, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    record = await session.scalar(select(WorldMap).where(WorldMap.world_id == access.world.id).with_for_update())
    current = record.revision if record else 0
    if current != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "地图已在其他设备更新", {"currentRevision": current})
    if record:
        record.archive, record.schema_version, record.revision, record.updated_by = body.archive, body.schema_version, current + 1, access.user.id
    else:
        record = WorldMap(world_id=access.world.id, archive=body.archive, schema_version=body.schema_version, revision=1, updated_by=access.user.id)
        session.add(record)
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="map.saved", target_type="map", target_id=access.world.id, payload={"revision": current + 1}))
    await session.commit()
    return {"archive": record.archive, "schemaVersion": record.schema_version, "revision": record.revision, "updatedAt": record.updated_at.isoformat()}


@router.put("/{world_id}/canvas")
async def put_canvas(body: CanvasPut, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    record = await session.scalar(select(CanvasDocument).where(CanvasDocument.world_id == access.world.id).with_for_update())
    current_revision = record.revision if record else 0
    if current_revision != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "Canvas 已在其他设备更新", {"currentRevision": current_revision})
    next_revision = current_revision + 1
    if record:
        record.document = body.document
        record.schema_version = body.schema_version
        record.revision = next_revision
        record.updated_by = access.user.id
    else:
        record = CanvasDocument(world_id=access.world.id, document=body.document, schema_version=body.schema_version, revision=next_revision, updated_by=access.user.id)
        session.add(record)
    session.add(CanvasRevision(world_id=access.world.id, revision=next_revision, document=body.document, author_id=access.user.id))
    objects = body.document.get("objects", [])
    if not isinstance(objects, list):
        raise AtlasError(422, "CANVAS_SCHEMA_INVALID", "Canvas objects 必须是数组")
    incoming_ids: set[str] = set()
    for item in objects:
        if not isinstance(item, dict) or not item.get("id"):
            raise AtlasError(422, "CANVAS_SCHEMA_INVALID", "Canvas 对象缺少 id")
        object_id = str(item["id"])
        incoming_ids.add(object_id)
        obj = await session.get(WorldObject, (access.world.id, object_id))
        if obj:
            obj.kind = str(item.get("kind", "note"))
            obj.title = str(item.get("title") or item.get("name") or "未命名")
            obj.payload = item
            obj.revision += 1
            obj.updated_by = access.user.id
        else:
            session.add(WorldObject(world_id=access.world.id, id=object_id, kind=str(item.get("kind", "note")), title=str(item.get("title") or item.get("name") or "未命名"), payload=item, updated_by=access.user.id))
    stored = (await session.scalars(select(WorldObject).where(WorldObject.world_id == access.world.id))).all()
    for obj in stored:
        if obj.id not in incoming_ids:
            await session.delete(obj)
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="canvas.saved", target_type="canvas", target_id=access.world.id, payload={"revision": next_revision}))
    await session.commit()
    return {"document": body.document, "schemaVersion": body.schema_version, "revision": next_revision, "updatedAt": record.updated_at.isoformat()}


@router.get("/{world_id}/objects")
async def list_objects(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    objects = (await session.scalars(select(WorldObject).where(WorldObject.world_id == access.world.id).order_by(WorldObject.kind, WorldObject.title))).all()
    return {"items": [{"id": item.id, "kind": item.kind, "title": item.title, "payload": item.payload, "revision": item.revision, "updatedAt": item.updated_at.isoformat()} for item in objects]}


@router.put("/{world_id}/objects/{object_id}")
async def put_wiki_object(object_id: str, body: WikiPut, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_write()
    obj = await session.scalar(select(WorldObject).where(WorldObject.world_id == access.world.id, WorldObject.id == object_id).with_for_update())
    current_revision = obj.revision if obj else 0
    if current_revision != body.expected_revision:
        raise AtlasError(409, "REVISION_CONFLICT", "Wiki 条目已在其他设备更新", {"currentRevision": current_revision})
    next_revision = current_revision + 1
    merged_payload = {**body.payload, "id": object_id, "kind": body.kind, "title": body.title}
    if obj:
        obj.kind, obj.title, obj.payload, obj.revision, obj.updated_by = body.kind, body.title, merged_payload, next_revision, access.user.id
    else:
        obj = WorldObject(world_id=access.world.id, id=object_id, kind=body.kind, title=body.title, payload=merged_payload, revision=next_revision, updated_by=access.user.id)
        session.add(obj)
    wiki_revision = WikiRevision(world_id=access.world.id, object_id=object_id, revision=next_revision, title=body.title, payload=merged_payload, author_id=access.user.id)
    session.add(wiki_revision)
    canvas = await session.scalar(select(CanvasDocument).where(CanvasDocument.world_id == access.world.id).with_for_update())
    if canvas:
        document = dict(canvas.document)
        objects = list(document.get("objects", []))
        index = next((i for i, item in enumerate(objects) if str(item.get("id")) == object_id), None)
        if index is None:
            objects.append(merged_payload)
        else:
            objects[index] = {**objects[index], **merged_payload}
        document["objects"] = objects
        canvas.document = document
        canvas.revision += 1
        canvas.updated_by = access.user.id
        session.add(CanvasRevision(world_id=access.world.id, revision=canvas.revision, document=document, author_id=access.user.id))
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="wiki.saved", target_type="world_object", target_id=object_id, payload={"revision": next_revision}))
    await session.commit()
    return {"id": object_id, "kind": body.kind, "title": body.title, "payload": merged_payload, "revision": next_revision, "canvasRevision": canvas.revision if canvas else 0}


@router.get("/{world_id}/objects/{object_id}/revisions")
async def wiki_revisions(object_id: str, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    revisions = (await session.scalars(select(WikiRevision).where(WikiRevision.world_id == access.world.id, WikiRevision.object_id == object_id).order_by(WikiRevision.revision.desc()))).all()
    return {"items": [{"id": str(item.id), "revision": item.revision, "title": item.title, "payload": item.payload, "authorID": str(item.author_id), "createdAt": item.created_at.isoformat()} for item in revisions]}
