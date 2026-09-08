from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)


class LoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(TokenInput):
    password: str = Field(min_length=12, max_length=200)


class ChangePasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class WorldCreate(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=160)
    tagline: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=10000)
    visibility: str = Field(default="private", pattern="^(private|unlisted|public)$")


class WorldUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    tagline: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=10000)
    status: str | None = Field(default=None, pattern="^(draft|recruiting|active|completed|archived)$")
    visibility: str | None = Field(default=None, pattern="^(private|unlisted|public)$")
    progress: float | None = Field(default=None, ge=0, le=1)


class CanvasPut(BaseModel):
    expected_revision: int = Field(ge=0)
    schema_version: int = Field(default=1, ge=1)
    document: dict[str, Any]


class WikiPut(BaseModel):
    expected_revision: int = Field(ge=0)
    kind: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any]


class InvitationCreate(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    role: str = Field(default="participant", pattern="^(manager|participant|observer)$")


class InvitationRespond(BaseModel):
    decision: str = Field(pattern="^(accepted|declined)$")


class JoinRequestCreate(BaseModel):
    message: str = Field(default="", max_length=2000)
    role: str = Field(default="participant", pattern="^(participant|observer)$")


class JoinRequestReview(BaseModel):
    decision: str = Field(pattern="^(accepted|declined)$")


class MembershipRoleUpdate(BaseModel):
    role: str = Field(pattern="^(manager|participant|observer)$")


class OwnershipTransfer(BaseModel):
    new_owner_id: str


class CharacterProfilePut(BaseModel):
    expected_revision: int = Field(ge=0)
    interaction_policy: str = Field(default="review", pattern="^(allowed|review|forbidden)$")
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=10000)
    status: str = Field(default="open", pattern="^(draft|open)$")
    capacity: int | None = Field(default=None, ge=1, le=10000)
    deadline_at: str | None = None
    object_ids: list[str] = Field(default_factory=list, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=10000)
    status: str | None = Field(default=None, pattern="^(draft|open|active|settling|completed|cancelled)$")
    capacity: int | None = Field(default=None, ge=1, le=10000)
    deadline_at: str | None = None


class SubmissionCreate(BaseModel):
    task_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=100000)
    destination: str = Field(default="Wiki", max_length=80)
    wiki_change_kind: str = Field(default="newEntry", pattern="^(newEntry|revision|confirmedRelationship)$")
    target_object_id: str | None = Field(default=None, max_length=100)
    affected_object_ids: list[str] = Field(default_factory=list, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class SubmissionUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=100000)
    destination: str | None = Field(default=None, max_length=80)
    target_object_id: str | None = Field(default=None, max_length=100)
    affected_object_ids: list[str] | None = Field(default=None, max_length=200)
    payload: dict[str, Any] | None = None


class ConfirmationDecision(BaseModel):
    decision: str = Field(pattern="^(accepted|declined)$")
    comment: str = Field(default="", max_length=4000)


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(accepted|revision|rejected)$")
    comment: str = Field(default="", max_length=10000)
    contribution_module: str = Field(default="writing", pattern="^(writing|illustration|video|model3D|craft|music|program|organization)$")
    scale_points: float = Field(default=1, ge=0, le=10000)
    completion_points: float = Field(default=1, ge=0, le=10000)
    specialty_points: float = Field(default=0, ge=0, le=10000)
    bonus_points: float = Field(default=0, ge=0, le=10000)
    is_polished: bool = False
    is_seasonal: bool = False


class SubmissionUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=100000)
    affected_object_ids: list[str] | None = Field(default=None, max_length=200)
    payload: dict[str, Any] | None = None


class ConfirmationDecision(BaseModel):
    decision: str = Field(pattern="^(accepted|declined)$")
    comment: str = Field(default="", max_length=2000)


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(accepted|revision|rejected)$")
    comment: str = Field(default="", max_length=5000)
    contribution_module: str = Field(default="writing", pattern="^(writing|illustration|video|model3D|craft|music|program|organization)$")
    scale_points: float = Field(default=1, ge=0, le=100)
    completion_points: float = Field(default=1, ge=0, le=100)
    specialty_points: float = Field(default=0, ge=0, le=100)
    bonus_points: float = Field(default=0, ge=0, le=100)
    is_polished: bool = False
    is_seasonal: bool = False
