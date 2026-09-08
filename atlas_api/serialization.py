from .models import User, World


def user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "emailVerified": user.email_verified_at is not None,
    }


def world_payload(world: World, role: str | None = None) -> dict:
    return {
        "id": world.id,
        "slug": world.slug,
        "name": world.name,
        "tagline": world.tagline,
        "summary": world.summary,
        "status": world.status,
        "visibility": world.visibility,
        "coverUrl": world.cover_url,
        "progress": float(world.progress),
        "metadata": world.metadata_,
        "revision": world.revision,
        "role": role,
        "createdAt": world.created_at.isoformat(),
        "updatedAt": world.updated_at.isoformat(),
    }

