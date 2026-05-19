"""Pydantic DTOs for the public idea submission feature."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

IdeaCategory = Literal["feature", "improvement", "bug", "ux", "other"]
IdeaStatus = Literal[
    "new", "reviewing", "planned", "in_progress", "shipped", "declined"
]

CATEGORY_VALUES = ("feature", "improvement", "bug", "ux", "other")
STATUS_VALUES = (
    "new",
    "reviewing",
    "planned",
    "in_progress",
    "shipped",
    "declined",
)


class IdeaImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_name: Optional[str]
    content_type: Optional[str]
    size_bytes: Optional[int]
    url: Optional[str] = None


class IdeaSubmissionCreate(BaseModel):
    """Public payload — JSON body, image upload is a separate multipart step."""

    contributor_name: str = Field(..., min_length=1, max_length=200)
    contributor_phone: Optional[str] = Field(None, max_length=50)
    contributor_email: Optional[EmailStr] = None
    contributor_department: Optional[str] = Field(None, max_length=200)
    title: Optional[str] = Field(None, max_length=300)
    description: str = Field(..., min_length=10)
    current_pain: Optional[str] = None
    expected_benefit: Optional[str] = None
    reference_system: Optional[str] = Field(None, max_length=500)
    category: IdeaCategory = "feature"


class IdeaSubmissionPublicOut(BaseModel):
    """Minimal response returned to the public submitter after success."""

    id: uuid.UUID
    created_at: datetime


class IdeaSubmissionOut(BaseModel):
    """Full record returned to admins."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contributor_name: str
    contributor_phone: Optional[str]
    contributor_email: Optional[str]
    contributor_department: Optional[str]
    title: Optional[str]
    description: str
    current_pain: Optional[str]
    expected_benefit: Optional[str]
    reference_system: Optional[str]
    category: IdeaCategory
    status: IdeaStatus
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    images: list[IdeaImageOut] = []


class IdeaSubmissionListOut(BaseModel):
    items: list[IdeaSubmissionOut]
    total: int
    page: int
    page_size: int


class IdeaSubmissionUpdate(BaseModel):
    """Admin-only patch payload."""

    status: Optional[IdeaStatus] = None
    admin_notes: Optional[str] = None
    category: Optional[IdeaCategory] = None
