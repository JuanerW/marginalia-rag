import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.progress import ProgressResponse, ProgressUpdate
from src.db.models import Chapter, Novel, ReadingProgress
from src.db.session import get_db

router = APIRouter()
DbSession = Annotated[AsyncSession, Depends(get_db)]


def _is_after(chapter: int, offset: int, other_chapter: int, other_offset: int) -> bool:
    return (chapter, offset) > (other_chapter, other_offset)


@router.get("/{novel_id}/progress", response_model=ProgressResponse)
async def get_progress(
    novel_id: uuid.UUID,
    db: DbSession,
    reader_key: str = "local",
) -> ProgressResponse:
    if await db.get(Novel, novel_id) is None:
        raise HTTPException(status_code=404, detail="小说不存在")
    progress = await db.scalar(
        select(ReadingProgress).where(
            ReadingProgress.novel_id == novel_id,
            ReadingProgress.reader_key == reader_key,
        )
    )
    if progress is None:
        return ProgressResponse(
            display_chapter_number=1,
            display_offset=0,
            furthest_chapter_number=1,
            furthest_offset=0,
            reader_key=reader_key,
        )
    return ProgressResponse.model_validate(progress, from_attributes=True)


@router.put("/{novel_id}/progress", response_model=ProgressResponse)
async def update_progress(
    novel_id: uuid.UUID,
    payload: ProgressUpdate,
    db: DbSession,
) -> ReadingProgress:
    chapter = await db.scalar(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.number == payload.display_chapter_number,
        )
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")

    display_offset = min(payload.display_offset, len(chapter.content))
    progress = await db.scalar(
        select(ReadingProgress)
        .where(
            ReadingProgress.novel_id == novel_id,
            ReadingProgress.reader_key == payload.reader_key,
        )
        .with_for_update()
    )
    if progress is None:
        progress = ReadingProgress(
            novel_id=novel_id,
            reader_key=payload.reader_key,
            display_chapter_number=payload.display_chapter_number,
            display_offset=display_offset,
            furthest_chapter_number=payload.display_chapter_number,
            furthest_offset=display_offset,
        )
        db.add(progress)
    else:
        progress.display_chapter_number = payload.display_chapter_number
        progress.display_offset = display_offset
        if _is_after(
            payload.display_chapter_number,
            display_offset,
            progress.furthest_chapter_number,
            progress.furthest_offset,
        ):
            progress.furthest_chapter_number = payload.display_chapter_number
            progress.furthest_offset = display_offset
    await db.commit()
    await db.refresh(progress)
    return progress

