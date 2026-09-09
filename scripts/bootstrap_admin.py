"""Create or update the explicitly configured Atlas administrator."""

import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import select

from atlas_api.db import SessionLocal
from atlas_api.models import PlatformRole, User, UserProfile
from atlas_api.security import hash_password


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"缺少环境变量 {name}")
    return value


async def main() -> None:
    username = required("ATLAS_BOOTSTRAP_ADMIN_USERNAME").lower()
    email = required("ATLAS_BOOTSTRAP_ADMIN_EMAIL").lower()
    password = required("ATLAS_BOOTSTRAP_ADMIN_PASSWORD")
    display_name = os.getenv("ATLAS_BOOTSTRAP_ADMIN_DISPLAY_NAME", username).strip() or username
    allow_legacy = os.getenv("ATLAS_BOOTSTRAP_ALLOW_LEGACY_PASSWORD", "").lower() == "true"
    if len(password) < 12 and not allow_legacy:
        raise SystemExit("管理员密码至少需要 12 个字符；迁移旧开发账号时可显式启用兼容开关")
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where((User.username == username) | (User.email == email)))
        if user is None:
            user = User(username=username, email=email, password_hash=hash_password(password))
            session.add(user)
            await session.flush()
            session.add(UserProfile(user_id=user.id, display_name=display_name, handle=username))
        else:
            user.username = username
            user.email = email
            user.password_hash = hash_password(password)
        user.role = PlatformRole.admin
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)
        user.disabled_at = None
        await session.commit()
    print(f"管理员 {username} 已就绪")


if __name__ == "__main__":
    asyncio.run(main())
