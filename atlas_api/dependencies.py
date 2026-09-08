import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db import get_session
from .errors import AtlasError
from .models import PlatformRole, User, World, WorldMembership, WorldRole
from .security import decode_access_token


async def current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AtlasError(401, "AUTH_REQUIRED", "尚未登录")
    try:
        payload = decode_access_token(settings, authorization[7:])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AtlasError(401, "AUTH_INVALID", "登录已失效") from None
    user = await session.get(User, user_id)
    if not user or user.disabled_at:
        raise AtlasError(401, "AUTH_INVALID", "登录已失效")
    return user


@dataclass
class WorldAccess:
    world: World
    role: WorldRole | None
    user: User

    def require_write(self) -> None:
        if self.world.status in {"completed", "archived"}:
            raise AtlasError(409, "WORLD_READ_ONLY", "该企划已结企或归档")
        if self.user.role != PlatformRole.admin and self.role not in {
            WorldRole.owner, WorldRole.manager, WorldRole.participant
        }:
            raise AtlasError(403, "WORLD_WRITE_FORBIDDEN", "无权修改该企划")

    def require_manage(self) -> None:
        if self.user.role != PlatformRole.admin and self.role not in {WorldRole.owner, WorldRole.manager}:
            raise AtlasError(403, "WORLD_MANAGE_FORBIDDEN", "无权管理该企划")


async def world_access(
    world_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> WorldAccess:
    world = await session.get(World, world_id)
    if not world:
        raise AtlasError(404, "WORLD_NOT_FOUND", "企划不存在")
    membership = await session.scalar(select(WorldMembership).where(
        WorldMembership.world_id == world_id,
        WorldMembership.user_id == user.id,
    ))
    role = membership.role if membership else None
    if world.visibility == "private" and not role and user.role != PlatformRole.admin:
        raise AtlasError(404, "WORLD_NOT_FOUND", "企划不存在")
    return WorldAccess(world, role, user)

