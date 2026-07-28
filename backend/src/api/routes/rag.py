import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.models import (
    Chapter,
    Chunk,
    ChunkEmbedding,
    IndexProfile,
    Novel,
    ReadingProgress,
)
from src.db.session import get_db
from src.services.chunking import chunk_text, fixed_chunk_text
from src.services.ollama import (
    OllamaChatClient,
    OllamaEmbeddingClient,
    OllamaError,
)

router = APIRouter()
DbSession = Annotated[AsyncSession, Depends(get_db)]


class IndexRequest(BaseModel):
    novel_id: uuid.UUID
    model: str | None = None
    strategy: str = Field(default="paragraph", pattern="^(paragraph|fixed)$")
    chapter_limit: int | None = Field(default=None, ge=1)
    target_size: int = Field(default=700, ge=100, le=4000)
    max_size: int = Field(default=900, ge=100, le=5000)
    overlap: int = Field(default=100, ge=0, le=1000)


class IndexResult(BaseModel):
    profile_id: uuid.UUID
    novel_id: uuid.UUID
    strategy: str
    model: str
    dimensions: int
    chapter_count: int
    chunk_count: int
    status: str
    is_active: bool


class IndexProfileResult(BaseModel):
    id: uuid.UUID
    novel_id: uuid.UUID
    strategy: str
    target_size: int
    max_size: int
    overlap: int
    embedding_model: str
    dimensions: int | None
    chapter_count: int
    chunk_count: int
    status: str
    is_active: bool
    created_at: datetime


class PreviewRequest(BaseModel):
    novel_id: uuid.UUID
    chapter_number: int = Field(ge=1)
    strategy: str = Field(default="paragraph", pattern="^(paragraph|fixed)$")
    target_size: int = Field(default=700, ge=100, le=4000)
    max_size: int = Field(default=900, ge=100, le=5000)
    overlap: int = Field(default=100, ge=0, le=1000)


class PreviewChunk(BaseModel):
    number: int
    start_offset: int
    end_offset: int
    length: int
    content: str


class PreviewResult(BaseModel):
    chapter_number: int
    strategy: str
    chunk_count: int
    chunks: list[PreviewChunk]


class SearchRequest(BaseModel):
    novel_id: uuid.UUID
    query: str = Field(min_length=1, max_length=2000)
    profile_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    reader_key: str = Field(default="local", min_length=1, max_length=128)
    max_chapter: int | None = Field(default=None, ge=1)
    max_offset: int | None = Field(default=None, ge=0)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    chapter_number: int
    start_offset: int
    end_offset: int
    content: str
    score: float


class SearchResult(BaseModel):
    novel_id: uuid.UUID
    profile_id: uuid.UUID
    query: str
    model: str
    hits: list[SearchHit]


class AskRequest(BaseModel):
    novel_id: uuid.UUID
    question: str = Field(min_length=1, max_length=2000)
    profile_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    reader_key: str = Field(default="local", min_length=1, max_length=128)
    max_chapter: int | None = Field(default=None, ge=1)
    max_offset: int | None = Field(default=None, ge=0)
    chat_model: str | None = None


class AskResult(BaseModel):
    novel_id: uuid.UUID
    profile_id: uuid.UUID
    question: str
    answer: str
    chat_model: str
    citations: list[SearchHit]


def _embedding_client(model: str | None) -> OllamaEmbeddingClient:
    return OllamaEmbeddingClient(
        settings.ollama_url,
        model or settings.ollama_embedding_model,
    )


async def _resolve_profile(
    db: AsyncSession,
    novel_id: uuid.UUID,
    profile_id: uuid.UUID | None,
) -> IndexProfile:
    if profile_id is not None:
        profile = await db.get(IndexProfile, profile_id)
        if profile is None or profile.novel_id != novel_id:
            raise HTTPException(status_code=404, detail="索引方案不存在")
        return profile
    profile = await db.scalar(
        select(IndexProfile).where(
            IndexProfile.novel_id == novel_id,
            IndexProfile.is_active.is_(True),
            IndexProfile.status == "ready",
        )
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="没有可用索引方案，请先建立索引")
    return profile


async def _resolve_reading_boundary(
    db: AsyncSession,
    novel_id: uuid.UUID,
    reader_key: str,
    max_chapter: int | None,
    max_offset: int | None,
) -> tuple[int, int]:
    if max_chapter is None:
        progress = await db.scalar(
            select(ReadingProgress).where(
                ReadingProgress.novel_id == novel_id,
                ReadingProgress.reader_key == reader_key,
            )
        )
        if progress is None:
            raise HTTPException(
                status_code=409,
                detail="尚无阅读进度，请先阅读或显式提供 max_chapter",
            )
        return progress.furthest_chapter_number, progress.furthest_offset
    return max_chapter, max_offset if max_offset is not None else 2**31 - 1


async def _retrieve(
    db: AsyncSession,
    novel_id: uuid.UUID,
    profile: IndexProfile,
    query: str,
    top_k: int,
    max_chapter: int,
    max_offset: int,
) -> list[tuple[Chunk, float]]:
    client = _embedding_client(profile.embedding_model)
    try:
        query_vector = (await client.embed([query]))[0]
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    distance = ChunkEmbedding.embedding.cosine_distance(query_vector)
    statement = (
        select(Chunk, distance.label("distance"))
        .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
        .where(
            Chunk.novel_id == novel_id,
            Chunk.index_profile_id == profile.id,
            ChunkEmbedding.model == profile.embedding_model,
            ChunkEmbedding.dimensions == len(query_vector),
            or_(
                Chunk.chapter_number < max_chapter,
                (
                    (Chunk.chapter_number == max_chapter)
                    & (Chunk.end_offset <= max_offset)
                ),
            ),
        )
        .order_by(distance)
        .limit(top_k)
    )
    return [
        (chunk, float(distance_value))
        for chunk, distance_value in (await db.execute(statement)).all()
    ]


def _search_hits(rows: list[tuple[Chunk, float]]) -> list[SearchHit]:
    return [
        SearchHit(
            chunk_id=chunk.id,
            chapter_number=chunk.chapter_number,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            content=chunk.content,
            score=1 - distance,
        )
        for chunk, distance in rows
    ]


@router.post("/preview", response_model=PreviewResult)
async def preview_chunks(payload: PreviewRequest, db: DbSession) -> PreviewResult:
    chapter = await db.scalar(
        select(Chapter).where(
            Chapter.novel_id == payload.novel_id,
            Chapter.number == payload.chapter_number,
        )
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    if not 0 <= payload.overlap < payload.target_size <= payload.max_size:
        raise HTTPException(
            status_code=422,
            detail="Chunk 参数必须满足 overlap < target_size <= max_size",
        )
    if payload.strategy == "paragraph":
        chunks = chunk_text(
            chapter.content,
            target_size=payload.target_size,
            max_size=payload.max_size,
            overlap=payload.overlap,
        )
    else:
        chunks = fixed_chunk_text(
            chapter.content,
            size=payload.target_size,
            overlap=payload.overlap,
        )
    return PreviewResult(
        chapter_number=chapter.number,
        strategy=payload.strategy,
        chunk_count=len(chunks),
        chunks=[
            PreviewChunk(
                number=number,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                length=len(chunk.content),
                content=chunk.content,
            )
            for number, chunk in enumerate(chunks, 1)
        ],
    )


@router.get(
    "/index-profiles/{novel_id}",
    response_model=list[IndexProfileResult],
)
async def list_index_profiles(
    novel_id: uuid.UUID,
    db: DbSession,
) -> list[IndexProfile]:
    if await db.get(Novel, novel_id) is None:
        raise HTTPException(status_code=404, detail="小说不存在")
    return list(
        (
            await db.scalars(
                select(IndexProfile)
                .where(IndexProfile.novel_id == novel_id)
                .order_by(IndexProfile.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/index-profiles/{profile_id}/activate",
    response_model=IndexProfileResult,
)
async def activate_index_profile(
    profile_id: uuid.UUID,
    db: DbSession,
) -> IndexProfile:
    profile = await db.get(IndexProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="索引方案不存在")
    if profile.status != "ready":
        raise HTTPException(status_code=409, detail="只能启用已完成的索引方案")
    await db.execute(
        update(IndexProfile)
        .where(IndexProfile.novel_id == profile.novel_id)
        .values(is_active=False)
    )
    profile.is_active = True
    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/index", response_model=IndexResult)
async def index_novel(payload: IndexRequest, db: DbSession) -> IndexResult:
    novel = await db.get(Novel, payload.novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="小说不存在")
    if not 0 <= payload.overlap < payload.target_size <= payload.max_size:
        raise HTTPException(
            status_code=422,
            detail="Chunk 参数必须满足 overlap < target_size <= max_size",
        )

    statement = (
        select(Chapter)
        .where(Chapter.novel_id == payload.novel_id)
        .order_by(Chapter.number)
    )
    if payload.chapter_limit is not None:
        statement = statement.limit(payload.chapter_limit)
    chapters = list((await db.scalars(statement)).all())
    if not chapters:
        raise HTTPException(status_code=422, detail="小说没有可索引章节")

    client = _embedding_client(payload.model)
    profile = IndexProfile(
        novel_id=payload.novel_id,
        strategy=payload.strategy,
        target_size=payload.target_size,
        max_size=payload.max_size,
        overlap=payload.overlap,
        embedding_model=client.model,
        dimensions=None,
        chapter_count=len(chapters),
        chunk_count=0,
        status="indexing",
        is_active=False,
    )
    db.add(profile)
    await db.flush()
    chunks: list[Chunk] = []
    for chapter in chapters:
        if payload.strategy == "paragraph":
            chapter_chunks = chunk_text(
                chapter.content,
                target_size=payload.target_size,
                max_size=payload.max_size,
                overlap=payload.overlap,
            )
        else:
            chapter_chunks = fixed_chunk_text(
                chapter.content,
                size=payload.target_size,
                overlap=payload.overlap,
            )
        for item in chapter_chunks:
            chunks.append(
                Chunk(
                    novel_id=payload.novel_id,
                    chapter_id=chapter.id,
                    index_profile_id=profile.id,
                    chapter_number=chapter.number,
                    content=item.content,
                    start_offset=item.start_offset,
                    end_offset=item.end_offset,
                )
            )
    if not chunks:
        raise HTTPException(status_code=422, detail="没有生成任何 Chunk")

    try:
        vectors = await client.embed([chunk.content for chunk in chunks])
    except OllamaError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        await db.rollback()
        raise HTTPException(status_code=502, detail="Ollama 返回的向量维度不一致")

    db.add_all(chunks)
    await db.flush()
    model = client.model
    db.add_all(
        [
            ChunkEmbedding(
                chunk_id=chunk.id,
                model=model,
                dimensions=dimensions,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
    )
    await db.execute(
        update(IndexProfile)
        .where(IndexProfile.novel_id == payload.novel_id)
        .values(is_active=False)
    )
    profile.dimensions = dimensions
    profile.chunk_count = len(chunks)
    profile.status = "ready"
    profile.is_active = True
    await db.commit()
    return IndexResult(
        profile_id=profile.id,
        novel_id=payload.novel_id,
        strategy=payload.strategy,
        model=model,
        dimensions=dimensions,
        chapter_count=len(chapters),
        chunk_count=len(chunks),
        status=profile.status,
        is_active=profile.is_active,
    )


@router.post("/search", response_model=SearchResult)
async def search_novel(payload: SearchRequest, db: DbSession) -> SearchResult:
    if await db.get(Novel, payload.novel_id) is None:
        raise HTTPException(status_code=404, detail="小说不存在")
    profile = await _resolve_profile(db, payload.novel_id, payload.profile_id)
    max_chapter, max_offset = await _resolve_reading_boundary(
        db,
        payload.novel_id,
        payload.reader_key,
        payload.max_chapter,
        payload.max_offset,
    )
    rows = await _retrieve(
        db,
        payload.novel_id,
        profile,
        payload.query,
        payload.top_k,
        max_chapter,
        max_offset,
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="没有找到匹配模型和阅读范围的索引，请先调用 /rag/index",
        )
    return SearchResult(
        novel_id=payload.novel_id,
        profile_id=profile.id,
        query=payload.query,
        model=profile.embedding_model,
        hits=_search_hits(rows),
    )


@router.post("/ask", response_model=AskResult)
async def ask_question(payload: AskRequest, db: DbSession) -> AskResult:
    if await db.get(Novel, payload.novel_id) is None:
        raise HTTPException(status_code=404, detail="小说不存在")
    profile = await _resolve_profile(db, payload.novel_id, payload.profile_id)
    max_chapter, max_offset = await _resolve_reading_boundary(
        db,
        payload.novel_id,
        payload.reader_key,
        payload.max_chapter,
        payload.max_offset,
    )
    rows = await _retrieve(
        db,
        payload.novel_id,
        profile,
        payload.question,
        payload.top_k,
        max_chapter,
        max_offset,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="已读范围内没有可用证据")
    hits = _search_hits(rows)
    context = "\n\n".join(
        (
            f"[{number}] 第{hit.chapter_number}章，"
            f"位置 {hit.start_offset}-{hit.end_offset}\n{hit.content}"
        )
        for number, hit in enumerate(hits, 1)
    )
    system = (
        "你是一个无剧透的小说阅读助手。只能根据提供的已读原文回答。"
        "不得使用未提供的剧情或你自己的小说知识。"
        "答案中的事实必须使用 [1]、[2] 形式引用证据编号。"
        "如果证据不足，明确回答“当前已读内容中没有足够信息”。"
    )
    prompt = f"问题：{payload.question}\n\n已读原文：\n{context}"
    chat_model = payload.chat_model or settings.ollama_chat_model
    try:
        answer = await OllamaChatClient(
            settings.ollama_url,
            chat_model,
        ).answer(system, prompt)
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AskResult(
        novel_id=payload.novel_id,
        profile_id=profile.id,
        question=payload.question,
        answer=answer,
        chat_model=chat_model,
        citations=hits,
    )
