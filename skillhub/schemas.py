from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_admin: bool
    has_api_token: bool = False


class AuthIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)


class TokenOut(BaseModel):
    token: str
    user: UserOut


class SkillSummary(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    tags: list[str]
    author_id: int
    author_name: str
    latest_version: str
    install_count: int
    rating_avg: float
    rating_count: int
    updated_at: datetime


class VersionOut(BaseModel):
    version: str
    changelog: str
    sha256: str
    size_bytes: int
    created_at: datetime


class RatingOut(BaseModel):
    username: str
    display_name: str
    stars: int
    comment: str
    updated_at: datetime


class SkillDetail(SkillSummary):
    skill_md: str
    versions: list[VersionOut]
    ratings: list[RatingOut]
    my_rating: RatingOut | None = None


class RateIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class PublishMeta(BaseModel):
    slug: str | None = None
    category: str = "docs"
    tags: str = ""
    version: str | None = None
    changelog: str = ""
