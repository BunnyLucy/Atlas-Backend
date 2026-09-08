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

