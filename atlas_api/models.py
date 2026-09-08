import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class PlatformRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class WorldRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    participant = "participant"
    observer = "observer"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[PlatformRole] = mapped_column(Enum(PlatformRole, name="platform_role"), default=PlatformRole.member)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    handle: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    bio: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    banner_url: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class World(Base):
    __tablename__ = "worlds"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    tagline: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    visibility: Mapped[str] = mapped_column(String(24), default="private", index=True)
    cover_url: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    revision: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorldMembership(Base):
    __tablename__ = "world_memberships"
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[WorldRole] = mapped_column(Enum(WorldRole, name="world_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorldInvitation(Base):
    __tablename__ = "world_invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    inviter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    invitee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[WorldRole] = mapped_column(Enum(WorldRole, name="world_role"), default=WorldRole.participant)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("world_invitation_pending_unique", "world_id", "invitee_id", unique=True, postgresql_where=(status == "pending")),
    )


class WorldJoinRequest(Base):
    __tablename__ = "world_join_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    requested_role: Mapped[WorldRole] = mapped_column(Enum(WorldRole, name="world_role"), default=WorldRole.participant)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("world_join_request_pending_unique", "world_id", "requester_id", unique=True, postgresql_where=(status == "pending")),
    )


class CanvasDocument(Base):
    __tablename__ = "canvas_documents"
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), primary_key=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(BigInteger, default=1)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CanvasRevision(Base):
    __tablename__ = "canvas_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("world_id", "revision"),)


class WorldObject(Base):
    __tablename__ = "world_objects"
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(BigInteger, default=1)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WikiRevision(Base):
    __tablename__ = "wiki_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(String(80), index=True)
    object_id: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    restored_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("world_id", "object_id", "revision"),
        Index("wiki_revision_object_idx", "world_id", "object_id", "revision"),
    )


class CharacterProfile(Base):
    __tablename__ = "character_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    interaction_policy: Mapped[str] = mapped_column(String(24), default="review")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("world_id", "object_id"),)


class WorldTask(Base):
    __tablename__ = "world_tasks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    capacity: Mapped[int | None] = mapped_column(Integer)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    object_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskParticipant(Base):
    __tablename__ = "task_participants"
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("world_tasks.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("world_tasks.id", ondelete="SET NULL"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    destination: Mapped[str] = mapped_column(String(80), default="Wiki")
    wiki_change_kind: Mapped[str] = mapped_column(String(32), default="newEntry")
    target_object_id: Mapped[str | None] = mapped_column(String(100))
    affected_object_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(BigInteger, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SubmissionConfirmation(Base):
    __tablename__ = "submission_confirmations"
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True)
    confirmer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    character_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("character_profiles.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionReview(Base):
    __tablename__ = "submission_reviews"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(24))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContributionEvent(Base):
    __tablename__ = "contribution_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[str] = mapped_column(String(160), index=True)
    sequence_for_target: Mapped[int] = mapped_column(Integer, default=1)
    scale_points: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    completion_points: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    specialty_points: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    bonus_points: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    is_polished: Mapped[bool] = mapped_column(Boolean, default=False)
    is_seasonal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("source_type", "source_id", "user_id"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    world_id: Mapped[str | None] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    action_type: Mapped[str | None] = mapped_column(String(80))
    action_target: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    world_id: Mapped[str | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
