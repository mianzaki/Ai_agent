from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOLVOX_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "postgresql+psycopg://volvox:volvox@localhost:5432/volvox"
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    api_bind_host: str = "127.0.0.1"
    api_bind_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    app_secret: SecretStr = SecretStr("development-only-change-me")
    supabase_url: str = ""
    supabase_jwt_issuer: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_allow_hs256: bool = False
    supabase_jwt_secret: SecretStr | None = None

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if (
            self.environment == "production"
            and self.app_secret.get_secret_value() == "development-only-change-me"
        ):
            raise ValueError("VOLVOX_APP_SECRET must be set in production")
        if self.supabase_allow_hs256 and not self.supabase_jwt_secret:
            raise ValueError("VOLVOX_SUPABASE_JWT_SECRET is required when HS256 is enabled")
        if self.supabase_allow_hs256 and self.environment == "production":
            raise ValueError("Legacy HS256 compatibility cannot be enabled in production")
        return self

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url) and "volvox:volvox@" not in self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
