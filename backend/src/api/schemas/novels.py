import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NovelSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str | None
    source_filename: str
    source_format: str
    status: str
    chapter_count: int
    created_at: datetime


class ChapterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    spine_index: int | None
    title: str
    source_href: str | None
    fragment_id: str | None
    start_offset: int
    end_offset: int


class ChapterDetail(ChapterSummary):
    content: str


class NovelDetail(NovelSummary):
    encoding: str


class UploadResult(NovelDetail):
    pass
