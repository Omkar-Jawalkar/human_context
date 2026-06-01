from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    email: EmailStr
    name: str
    super_admin: bool
    created_at: datetime
    updated_at: datetime


class UserSelfUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=1)


class UserJoinOrganization(BaseModel):
    organization_id: uuid.UUID


class UserRegister(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1)
    password: str | None = Field(default=None, min_length=1)
    organization_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=1)
    organization_id: uuid.UUID | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
