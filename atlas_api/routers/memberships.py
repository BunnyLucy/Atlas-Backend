import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..dependencies import WorldAccess, current_user, world_access
from ..errors import AtlasError
from ..models import AuditEvent, Notification, User, UserProfile, World, WorldInvitation, WorldJoinRequest, WorldMembership, WorldRole
from ..schemas import InvitationCreate, InvitationRespond, JoinRequestCreate, JoinRequestReview, MembershipRoleUpdate, OwnershipTransfer

router = APIRouter(tags=["memberships"])


def membership_payload(row: tuple[WorldMembership, User, UserProfile | None]) -> dict:
    membership, user, profile = row
    return {
        "userID": str(user.id),
        "username": user.username,
        "displayName": profile.display_name if profile else user.username,
        "avatarURL": profile.avatar_url if profile else None,
        "role": membership.role.value,
        "joinedAt": membership.created_at.isoformat(),
    }


@router.get("/worlds/{world_id}/members")
async def members(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(
        select(WorldMembership, User, UserProfile)
        .join(User, User.id == WorldMembership.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(WorldMembership.world_id == access.world.id)
        .order_by(WorldMembership.created_at)
    )).all()
    return {"items": [membership_payload(row) for row in rows]}


@router.post("/worlds/{world_id}/invitations", status_code=201)
async def invite(body: InvitationCreate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    access.require_write()
    identifier = body.identifier.strip().lower()
    invitee = await session.scalar(select(User).where(or_(User.username == identifier, User.email == identifier), User.disabled_at.is_(None)))
    if not invitee:
        raise AtlasError(404, "USER_NOT_FOUND", "未找到该用户")
    if await session.get(WorldMembership, (access.world.id, invitee.id)):
        raise AtlasError(409, "ALREADY_MEMBER", "该用户已经是企划成员")
    pending = await session.scalar(select(WorldInvitation).where(
        WorldInvitation.world_id == access.world.id,
        WorldInvitation.invitee_id == invitee.id,
        WorldInvitation.status == "pending",
    ))
    if pending:
        raise AtlasError(409, "INVITATION_PENDING", "该用户已有待处理邀请")
    invitation = WorldInvitation(
        world_id=access.world.id,
        inviter_id=access.user.id,
        invitee_id=invitee.id,
        role=WorldRole(body.role),
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    session.add(invitation)
    await session.flush()
    session.add(Notification(
        recipient_user_id=invitee.id,
        world_id=access.world.id,
        type="world.invitation",
        title=f"邀请加入「{access.world.name}」",
        summary="你收到了一份企划邀请",
        dedupe_key=f"world-invitation:{invitation.id}",
        action_type="invitation",
        action_target=str(invitation.id),
    ))
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="membership.invited", target_type="user", target_id=str(invitee.id), payload={"role": body.role}))
    await session.commit()
    return {"id": str(invitation.id), "status": invitation.status, "expiresAt": invitation.expires_at.isoformat()}


@router.get("/memberships/invitations")
async def my_invitations(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    now = datetime.now(UTC)
    rows = (await session.execute(
        select(WorldInvitation, World)
        .join(World, World.id == WorldInvitation.world_id)
        .where(WorldInvitation.invitee_id == user.id, WorldInvitation.status == "pending", WorldInvitation.expires_at > now)
        .order_by(WorldInvitation.created_at.desc())
    )).all()
    return {"items": [{"id": str(item.id), "worldID": world.id, "worldName": world.name, "role": item.role.value, "status": item.status, "expiresAt": item.expires_at.isoformat()} for item, world in rows]}


@router.patch("/memberships/invitations/{invitation_id}")
async def respond_invitation(invitation_id: uuid.UUID, body: InvitationRespond, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    invitation = await session.scalar(select(WorldInvitation).where(WorldInvitation.id == invitation_id).with_for_update())
    if not invitation or invitation.invitee_id != user.id:
        raise AtlasError(404, "INVITATION_NOT_FOUND", "邀请不存在")
    if invitation.status != "pending" or invitation.expires_at <= datetime.now(UTC):
        raise AtlasError(409, "INVITATION_CLOSED", "邀请已处理或过期")
    invitation.status = body.decision
    invitation.responded_at = datetime.now(UTC)
    if body.decision == "accepted":
        session.add(WorldMembership(world_id=invitation.world_id, user_id=user.id, role=invitation.role))
    session.add(AuditEvent(actor_id=user.id, world_id=invitation.world_id, action=f"membership.invitation.{body.decision}", target_type="invitation", target_id=str(invitation.id)))
    await session.commit()
    return {"id": str(invitation.id), "status": invitation.status}


@router.delete("/worlds/{world_id}/invitations/{invitation_id}", status_code=204)
async def cancel_invitation(invitation_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> None:
    access.require_manage()
    invitation = await session.scalar(select(WorldInvitation).where(WorldInvitation.id == invitation_id, WorldInvitation.world_id == access.world.id).with_for_update())
    if not invitation:
        raise AtlasError(404, "INVITATION_NOT_FOUND", "邀请不存在")
    if invitation.status == "pending":
        invitation.status = "cancelled"
        invitation.responded_at = datetime.now(UTC)
        await session.commit()


@router.post("/worlds/{world_id}/join-requests", status_code=201)
async def request_join(world_id: str, body: JoinRequestCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    world = await session.get(World, world_id)
    if not world or world.visibility == "private":
        raise AtlasError(404, "WORLD_NOT_FOUND", "企划不存在")
    if await session.get(WorldMembership, (world_id, user.id)):
        raise AtlasError(409, "ALREADY_MEMBER", "你已经是企划成员")
    pending = await session.scalar(select(WorldJoinRequest).where(WorldJoinRequest.world_id == world_id, WorldJoinRequest.requester_id == user.id, WorldJoinRequest.status == "pending"))
    if pending:
        raise AtlasError(409, "JOIN_REQUEST_PENDING", "已有待处理申请")
    request = WorldJoinRequest(world_id=world_id, requester_id=user.id, message=body.message, requested_role=WorldRole(body.role))
    session.add(request)
    await session.flush()
    managers = (await session.scalars(select(WorldMembership.user_id).where(WorldMembership.world_id == world_id, WorldMembership.role.in_([WorldRole.owner, WorldRole.manager])))).all()
    for manager_id in managers:
        session.add(Notification(recipient_user_id=manager_id, world_id=world_id, type="world.join-request", title=f"「{world.name}」收到加入申请", summary=body.message, dedupe_key=f"join-request:{request.id}:{manager_id}", action_type="join-request", action_target=str(request.id)))
    await session.commit()
    return {"id": str(request.id), "status": request.status}


@router.get("/worlds/{world_id}/join-requests")
async def list_join_requests(access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    rows = (await session.execute(select(WorldJoinRequest, User, UserProfile).join(User, User.id == WorldJoinRequest.requester_id).outerjoin(UserProfile, UserProfile.user_id == User.id).where(WorldJoinRequest.world_id == access.world.id, WorldJoinRequest.status == "pending").order_by(WorldJoinRequest.created_at))).all()
    return {"items": [{"id": str(item.id), "userID": str(user.id), "displayName": profile.display_name if profile else user.username, "message": item.message, "role": item.requested_role.value, "createdAt": item.created_at.isoformat()} for item, user, profile in rows]}


@router.patch("/worlds/{world_id}/join-requests/{request_id}")
async def review_join_request(request_id: uuid.UUID, body: JoinRequestReview, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    request = await session.scalar(select(WorldJoinRequest).where(WorldJoinRequest.id == request_id, WorldJoinRequest.world_id == access.world.id).with_for_update())
    if not request:
        raise AtlasError(404, "JOIN_REQUEST_NOT_FOUND", "加入申请不存在")
    if request.status != "pending":
        raise AtlasError(409, "JOIN_REQUEST_CLOSED", "加入申请已处理")
    request.status, request.reviewer_id, request.reviewed_at = body.decision, access.user.id, datetime.now(UTC)
    if body.decision == "accepted":
        session.add(WorldMembership(world_id=access.world.id, user_id=request.requester_id, role=request.requested_role))
    session.add(Notification(recipient_user_id=request.requester_id, world_id=access.world.id, type="world.join-request.result", title=f"加入申请已{ '通过' if body.decision == 'accepted' else '拒绝' }", dedupe_key=f"join-request-result:{request.id}", action_type="world", action_target=access.world.id))
    await session.commit()
    return {"id": str(request.id), "status": request.status}


@router.patch("/worlds/{world_id}/members/{user_id}")
async def update_member_role(user_id: uuid.UUID, body: MembershipRoleUpdate, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    access.require_manage()
    membership = await session.scalar(select(WorldMembership).where(WorldMembership.world_id == access.world.id, WorldMembership.user_id == user_id).with_for_update())
    if not membership:
        raise AtlasError(404, "MEMBERSHIP_NOT_FOUND", "成员不存在")
    if membership.role == WorldRole.owner:
        raise AtlasError(409, "OWNER_ROLE_IMMUTABLE", "请使用所有权转移功能")
    membership.role = WorldRole(body.role)
    await session.commit()
    return {"userID": str(user_id), "role": membership.role.value}


@router.delete("/worlds/{world_id}/members/{user_id}", status_code=204)
async def remove_or_leave(user_id: uuid.UUID, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> None:
    if user_id != access.user.id:
        access.require_manage()
    membership = await session.scalar(select(WorldMembership).where(WorldMembership.world_id == access.world.id, WorldMembership.user_id == user_id).with_for_update())
    if not membership:
        raise AtlasError(404, "MEMBERSHIP_NOT_FOUND", "成员不存在")
    if membership.role == WorldRole.owner:
        raise AtlasError(409, "OWNER_CANNOT_LEAVE", "企主必须先转移所有权")
    await session.delete(membership)
    await session.commit()


@router.post("/worlds/{world_id}/transfer-ownership")
async def transfer_ownership(body: OwnershipTransfer, access: WorldAccess = Depends(world_access), session: AsyncSession = Depends(get_session)) -> dict:
    if access.role != WorldRole.owner and access.user.role.value != "admin":
        raise AtlasError(403, "OWNER_REQUIRED", "只有企主可以转移所有权")
    try:
        new_owner_id = uuid.UUID(body.new_owner_id)
    except ValueError:
        raise AtlasError(422, "USER_ID_INVALID", "用户 ID 无效") from None
    target = await session.scalar(select(WorldMembership).where(WorldMembership.world_id == access.world.id, WorldMembership.user_id == new_owner_id).with_for_update())
    current = await session.scalar(select(WorldMembership).where(WorldMembership.world_id == access.world.id, WorldMembership.role == WorldRole.owner).with_for_update())
    if not target or not current:
        raise AtlasError(404, "MEMBERSHIP_NOT_FOUND", "新企主必须已是企划成员")
    current.role, target.role = WorldRole.manager, WorldRole.owner
    access.world.owner_id = new_owner_id
    session.add(AuditEvent(actor_id=access.user.id, world_id=access.world.id, action="membership.ownership-transferred", target_type="user", target_id=str(new_owner_id)))
    await session.commit()
    return {"worldID": access.world.id, "ownerID": str(new_owner_id)}

