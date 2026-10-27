from functools import cached_property
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(repr=False)
    internal_api_token: str = Field(min_length=32, repr=False)
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = Field(repr=False)
    s3_secret_key: str = Field(min_length=16, repr=False)
    s3_bucket: str = "catalog-images"
    s3_region: str = "us-east-1"
    bot_token: str = Field(default="", repr=False)
    webhook_secret: str = Field(min_length=32, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    admin_ids: str = ""
    public_base_url: str = "http://localhost:8080"
    api_base_url: str = "http://gateway:8081"
    max_image_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    worker_poll_seconds: float = Field(default=0.5, ge=0.1, le=10)
    worker_timeout_seconds: int = Field(default=60, ge=10, le=90)
    job_lease_seconds: int = Field(default=120, ge=120)
    job_max_attempts: int = Field(default=8, ge=1, le=20)

    @field_validator("public_base_url")
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("PUBLIC_BASE_URL must contain only scheme and host")
        return value.rstrip("/")

    @field_validator("admin_ids")
    @classmethod
    def validate_admin_ids(cls, value: str) -> str:
        if any(not item.strip().isdigit() or int(item) <= 0 for item in value.split(",") if item.strip()):
            raise ValueError("ADMIN_IDS must be comma-separated positive Telegram user IDs")
        return value

    @cached_property
    def administrators(self) -> frozenset[int]:
        return frozenset(int(item.strip()) for item in self.admin_ids.split(",") if item.strip())
