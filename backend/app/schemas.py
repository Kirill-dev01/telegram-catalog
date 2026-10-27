from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    source_key: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9:_-]+$")
    image_base64: str = Field(min_length=4, max_length=14_000_000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Название не может быть пустым")
        return value


class ProductOut(BaseModel):
    id: int
    name: str
    image_url: str
    created_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    next_cursor: int | None
