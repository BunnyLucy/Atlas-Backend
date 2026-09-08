import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session
from ..dependencies import current_user
from ..errors import AtlasError
from ..models import AuthToken, OutboxEvent, RefreshSession, User, UserProfile
from ..schemas import ChangePasswordInput, ForgotPasswordInput, LoginInput, RegisterInput, ResetPasswordInput, TokenInput
from ..security import access_token, hash_password, opaque_token, token_digest, verify_password
from ..serialization import user_payload

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "atlas_refresh"


def set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


async def issue_session(session: AsyncSession, response: Response, settings: Settings, user: User, family_id: uuid.UUID | None = None) -> dict:
    raw = opaque_token()
    refresh = RefreshSession(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=token_digest(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    session.add(refresh)
    await session.commit()
    set_refresh_cookie(response, settings, raw)
    return {"accessToken": access_token(settings, user.id, user.role.value), "user": user_payload(user)}


@router.post("/register", status_code=201)
async def register(body: RegisterInput, session: AsyncSession = Depends(get_session)) -> dict:
    email, username = body.email.lower(), body.username.lower()
    exists = await session.scalar(select(User.id).where(or_(User.email == email, User.username == username)))
    if exists:
        raise AtlasError(409, "ACCOUNT_EXISTS", "用户名或邮箱已被使用")
    user = User(username=username, email=email, password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    session.add(UserProfile(user_id=user.id, display_name=body.display_name, handle=username))
    raw = opaque_token()
    session.add(AuthToken(user_id=user.id, kind="verify_email", token_hash=token_digest(raw), expires_at=datetime.now(UTC) + timedelta(hours=24)))
    session.add(OutboxEvent(kind="email.verify", payload={"userID": str(user.id), "email": email, "token": raw}))
    await session.commit()
    return {"user": user_payload(user), "verificationRequired": True}


@router.post("/verify-email")
async def verify_email(body: TokenInput, session: AsyncSession = Depends(get_session)) -> dict:
    now = datetime.now(UTC)
    record = await session.scalar(select(AuthToken).where(
        AuthToken.kind == "verify_email", AuthToken.token_hash == token_digest(body.token),
        AuthToken.consumed_at.is_(None), AuthToken.expires_at > now,
    ).with_for_update())
    if not record:
        raise AtlasError(400, "TOKEN_INVALID", "验证链接无效或已过期")
    user = await session.get(User, record.user_id)
    assert user
    record.consumed_at = now
    user.email_verified_at = now
    await session.commit()
    return {"verified": True}


@router.post("/login")
async def login(body: LoginInput, response: Response, session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    identifier = body.identifier.strip().lower()
    user = await session.scalar(select(User).where(or_(User.email == identifier, User.username == identifier)))
    if not user or not user.password_hash or user.disabled_at or not verify_password(body.password, user.password_hash):
        raise AtlasError(401, "LOGIN_FAILED", "账号或密码不正确")
    return await issue_session(session, response, settings, user)


@router.post("/refresh")
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AtlasError(401, "REFRESH_REQUIRED", "会话已失效")
    now = datetime.now(UTC)
    record = await session.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_digest(raw)).with_for_update())
    if not record or record.expires_at <= now:
        raise AtlasError(401, "REFRESH_INVALID", "会话已失效")
    if record.revoked_at:
        if record.replaced_by_id:
            await session.execute(update(RefreshSession).where(RefreshSession.family_id == record.family_id).values(revoked_at=now))
            await session.commit()
        raise AtlasError(401, "REFRESH_REUSED", "检测到会话令牌重复使用，请重新登录")
    user = await session.get(User, record.user_id)
    if not user or user.disabled_at:
        raise AtlasError(401, "REFRESH_INVALID", "会话已失效")
    record.revoked_at = now
    result = await issue_session(session, response, settings, user, record.family_id)
    newest = await session.scalar(select(RefreshSession.id).where(RefreshSession.family_id == record.family_id).order_by(RefreshSession.created_at.desc()))
    record.replaced_by_id = newest
    await session.commit()
    return result


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        record = await session.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_digest(raw)))
        if record and not record.revoked_at:
            record.revoked_at = datetime.now(UTC)
            await session.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordInput, session: AsyncSession = Depends(get_session)) -> dict:
    user = await session.scalar(select(User).where(User.email == body.email.lower(), User.disabled_at.is_(None)))
    if user:
        raw = opaque_token()
        session.add(AuthToken(user_id=user.id, kind="reset_password", token_hash=token_digest(raw), expires_at=datetime.now(UTC) + timedelta(hours=1)))
        session.add(OutboxEvent(kind="email.reset-password", payload={"userID": str(user.id), "email": user.email, "token": raw}))
        await session.commit()
    return {"accepted": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordInput, session: AsyncSession = Depends(get_session)) -> dict:
    now = datetime.now(UTC)
    record = await session.scalar(select(AuthToken).where(
        AuthToken.kind == "reset_password", AuthToken.token_hash == token_digest(body.token),
        AuthToken.consumed_at.is_(None), AuthToken.expires_at > now,
    ).with_for_update())
    if not record:
        raise AtlasError(400, "TOKEN_INVALID", "重置链接无效或已过期")
    user = await session.get(User, record.user_id)
    assert user
    user.password_hash = hash_password(body.password)
    record.consumed_at = now
    await session.execute(update(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).values(revoked_at=now))
    await session.commit()
    return {"reset": True}


@router.post("/change-password")
async def change_password(body: ChangePasswordInput, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise AtlasError(400, "PASSWORD_INCORRECT", "当前密码不正确")
    user.password_hash = hash_password(body.new_password)
    await session.execute(update(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))
    await session.commit()
    return {"changed": True}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return {"user": user_payload(user)}

