from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ATLAS_",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://atlas:atlas@127.0.0.1:5432/atlas_python"
    jwt_secret: SecretStr = Field(min_length=32)
    web_origin: AnyHttpUrl = "http://127.0.0.1:5173"
    cookie_secure: bool = False
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    github_callback_url: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.env == "production" and not self.cookie_secure:
            raise ValueError("Secure cookies are mandatory in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

