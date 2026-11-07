from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEVELOPMENT_SECRET = "local-development-key-change-before-deploying"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHOP_", extra="ignore")

    database_url: str = "sqlite:///./shop.db"
    secret_key: str = _DEVELOPMENT_SECRET
    access_token_minutes: int = Field(default=60, gt=0, le=1440)
    order_payment_expiry_minutes: int = Field(default=30, ge=5, le=1440)
    environment: Literal["development", "production"] = "development"
    cors_origins: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "shop-images"

    @model_validator(mode="after")
    def validate_production_secret(self):
        if self.environment == "production" and (
            self.secret_key == _DEVELOPMENT_SECRET or len(self.secret_key) < 32
        ):
            raise ValueError(
                "SHOP_SECRET_KEY must be at least 32 characters and not the development default in production"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
