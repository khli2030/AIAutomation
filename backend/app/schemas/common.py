"""Common response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str


class TimestampedModel(ORMModel):
    created_at: datetime | None = None
