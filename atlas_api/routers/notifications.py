import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import current_user
from ..errors import AtlasError
from ..models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


def payload(item: Notification) -> dict:
    return {"id": str(item.id), "worldID": item.world_id, "type": item.type, "title": item.title, "summary": item.summary, "payload": item.payload, "actionType": item.action_type, "actionTarget": item.action_target, "read": item.read_at is not None, "createdAt": item.created_at.isoformat()}


@router.get("")
async def list_notifications(user: User = Depends(current_user), session: AsyncSession = Depends(get_session), limit: int = Query(default=30, ge=1, le=100), before: datetime | None = Query(default=None), unread_only: bool = False) -> dict:
    query = select(Notification).where(Notification.recipient_user_id == user.id, Notification.archived_at.is_(None))
    if before: query = query.where(Notification.created_at < before)
    if unread_only: query = query.where(Notification.read_at.is_(None))
    items = (await session.scalars(query.order_by(Notification.created_at.desc()).limit(limit + 1))).all()
    has_more = len(items) > limit
    items = items[:limit]
    unread = await session.scalar(select(func.count()).select_from(Notification).where(Notification.recipient_user_id == user.id, Notification.read_at.is_(None), Notification.archived_at.is_(None))) or 0
    return {"items": [payload(item) for item in items], "nextCursor": items[-1].created_at.isoformat() if has_more else None, "unreadCount": unread}


@router.patch("/{notification_id}/read")
async def mark_read(notification_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    item = await session.get(Notification, notification_id)
    if not item or item.recipient_user_id != user.id:
        raise AtlasError(404, "NOTIFICATION_NOT_FOUND", "通知不存在")
    item.read_at = item.read_at or datetime.now(UTC)
    await session.commit()
    return payload(item)


@router.post("/read-all")
async def mark_all_read(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(update(Notification).where(Notification.recipient_user_id == user.id, Notification.read_at.is_(None), Notification.archived_at.is_(None)).values(read_at=datetime.now(UTC)))
    await session.commit()
    return {"updated": result.rowcount}


@router.patch("/{notification_id}/archive", status_code=204)
async def archive(notification_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> None:
    item = await session.get(Notification, notification_id)
    if not item or item.recipient_user_id != user.id:
        raise AtlasError(404, "NOTIFICATION_NOT_FOUND", "通知不存在")
    item.archived_at = datetime.now(UTC)
    await session.commit()

