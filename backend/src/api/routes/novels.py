import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.novels import (
    ChapterDetail,
    ChapterSummary,
    NovelDetail,
    NovelSummary,
    UploadResult,
)
from src.db.models import Chapter, Novel
from src.db.session import get_db
from src.services.epub_parser import (
    MAX_EPUB_SIZE,
    EpubParseError,
    parse_epub,
)
from src.services.text_parser import MAX_TXT_SIZE, TextDecodeError, decode_txt, split_chapters

router = APIRouter()
DbSession = Annotated[AsyncSession, Depends(get_db)]


def _safe_title(filename: str) -> str:
    return Path(filename).stem.strip()[:255] or "未命名小说"


async def _novel_or_404(db: AsyncSession, novel_id: uuid.UUID) -> Novel:
    novel = await db.get(Novel, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="小说不存在")
    return novel


@router.get("", response_model=list[NovelSummary])
async def list_novels(db: DbSession) -> list[NovelSummary]:
    statement = (
        select(Novel, func.count(Chapter.id).label("chapter_count"))
        .outerjoin(Chapter)
        .group_by(Novel.id)
        .order_by(Novel.created_at.desc())
    )
    rows = (await db.execute(statement)).all()
    return [
        NovelSummary.model_validate(
            {
                "id": novel.id,
                "title": novel.title,
                "author": novel.author,
                "source_filename": novel.source_filename,
                "source_format": novel.source_format,
                "status": novel.status,
                "chapter_count": chapter_count,
                "created_at": novel.created_at,
            }
        )
        for novel, chapter_count in rows
    ]


@router.post("", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_novel(
    db: DbSession,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    author: Annotated[str | None, Form()] = None,
) -> UploadResult:
    if not file.filename:
        raise HTTPException(status_code=422, detail="文件名不能为空")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".epub", ".txt"}:
        raise HTTPException(status_code=415, detail="目前支持 EPUB 和 TXT 文件")

    max_size = MAX_EPUB_SIZE if suffix == ".epub" else MAX_TXT_SIZE
    data = await file.read(max_size + 1)
    if len(data) > max_size:
        limit = 50 if suffix == ".epub" else 20
        raise HTTPException(status_code=413, detail=f"文件不能超过 {limit} MB")

    source_format = suffix.removeprefix(".")
    if source_format == "epub":
        try:
            parsed_epub = parse_epub(data)
        except EpubParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        parsed_chapters = parsed_epub.chapters
        encoding = "epub-xhtml"
        inferred_title = parsed_epub.title
        inferred_author = parsed_epub.author
        content_hash = hashlib.sha256(data).hexdigest()
    else:
        try:
            text, encoding = decode_txt(data)
        except TextDecodeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        parsed_chapters = split_chapters(text)
        inferred_title = None
        inferred_author = None
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    if await db.scalar(select(Novel.id).where(Novel.content_hash == content_hash)):
        raise HTTPException(status_code=409, detail="这本小说已经上传过了")

    clean_title = (title or "").strip()[:255] or inferred_title or _safe_title(file.filename)
    clean_author = (author or "").strip()[:255] or inferred_author
    novel = Novel(
        title=clean_title,
        author=clean_author,
        source_filename=Path(file.filename).name[:512],
        source_format=source_format,
        content_hash=content_hash,
        encoding=encoding,
        status="ready",
    )
    novel.chapters = [
        Chapter(
            number=chapter.number,
            spine_index=getattr(chapter, "spine_index", None),
            title=chapter.title,
            source_href=getattr(chapter, "source_href", None),
            fragment_id=getattr(chapter, "fragment_id", None),
            content=chapter.content,
            start_offset=chapter.start_offset,
            end_offset=chapter.end_offset,
        )
        for chapter in parsed_chapters
    ]
    db.add(novel)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="这本小说已经上传过了") from exc
    await db.refresh(novel)

    return UploadResult(
        id=novel.id,
        title=novel.title,
        author=novel.author,
        source_filename=novel.source_filename,
        source_format=novel.source_format,
        status=novel.status,
        chapter_count=len(parsed_chapters),
        created_at=novel.created_at,
        encoding=novel.encoding,
    )


@router.get("/{novel_id}", response_model=NovelDetail)
async def get_novel(novel_id: uuid.UUID, db: DbSession) -> NovelDetail:
    novel = await _novel_or_404(db, novel_id)
    chapter_count = await db.scalar(
        select(func.count(Chapter.id)).where(Chapter.novel_id == novel_id)
    )
    return NovelDetail(
        id=novel.id,
        title=novel.title,
        author=novel.author,
        source_filename=novel.source_filename,
        source_format=novel.source_format,
        status=novel.status,
        chapter_count=chapter_count or 0,
        created_at=novel.created_at,
        encoding=novel.encoding,
    )


@router.get("/{novel_id}/chapters", response_model=list[ChapterSummary])
async def list_chapters(novel_id: uuid.UUID, db: DbSession) -> list[Chapter]:
    await _novel_or_404(db, novel_id)
    return list(
        (
            await db.scalars(
                select(Chapter)
                .where(Chapter.novel_id == novel_id)
                .order_by(Chapter.number)
            )
        ).all()
    )


@router.get("/{novel_id}/chapters/{chapter_number}", response_model=ChapterDetail)
async def get_chapter(
    novel_id: uuid.UUID, chapter_number: int, db: DbSession
) -> Chapter:
    chapter = await db.scalar(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.number == chapter_number,
        )
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter
