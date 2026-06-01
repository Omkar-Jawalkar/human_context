from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    meta: dict
    created_at: datetime
    updated_at: datetime


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1)
    meta: dict = Field(default_factory=dict)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    meta: dict | None = None


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
