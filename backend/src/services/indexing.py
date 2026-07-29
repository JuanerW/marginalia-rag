import uuid

from sqlalchemy import delete, select, update

from src.core.config import settings
from src.db.models import Chapter, Chunk, ChunkEmbedding, IndexProfile
from src.db.session import SessionLocal
from src.services.chunking import TextChunk, chunk_text, fixed_chunk_text
from src.services.ollama import OllamaEmbeddingClient

EMBED_BATCH_SIZE = 16


def _chapter_chunks(
    profile: IndexProfile,
    chapter: Chapter,
) -> list[TextChunk]:
    if profile.strategy == "paragraph":
        return chunk_text(
            chapter.content,
            target_size=profile.target_size,
            max_size=profile.max_size,
            overlap=profile.overlap,
        )
    return fixed_chunk_text(
        chapter.content,
        size=profile.target_size,
        overlap=profile.overlap,
    )


async def run_index_profile(
    profile_id: uuid.UUID,
    chapter_limit: int | None,
) -> None:
    try:
        async with SessionLocal() as db:
            profile = await db.get(IndexProfile, profile_id)
            if profile is None:
                return
            profile.status = "chunking"
            profile.error_message = None
            profile.processed_chunks = 0
            await db.commit()

            statement = (
                select(Chapter)
                .where(Chapter.novel_id == profile.novel_id)
                .order_by(Chapter.number)
            )
            if chapter_limit is not None:
                statement = statement.limit(chapter_limit)
            chapters = list((await db.scalars(statement)).all())
            items = [
                (chapter, item)
                for chapter in chapters
                for item in _chapter_chunks(profile, chapter)
            ]
            profile.chapter_count = len(chapters)
            profile.chunk_count = len(items)
            profile.status = "embedding"
            await db.execute(
                delete(Chunk).where(Chunk.index_profile_id == profile.id)
            )
            await db.commit()

            client = OllamaEmbeddingClient(
                settings.ollama_url,
                profile.embedding_model,
            )
            for start in range(0, len(items), EMBED_BATCH_SIZE):
                batch = items[start : start + EMBED_BATCH_SIZE]
                vectors = await client.embed([item.content for _, item in batch])
                dimensions = len(vectors[0])
                chunks = [
                    Chunk(
                        novel_id=profile.novel_id,
                        chapter_id=chapter.id,
                        index_profile_id=profile.id,
                        chapter_number=chapter.number,
                        content=item.content,
                        start_offset=item.start_offset,
                        end_offset=item.end_offset,
                    )
                    for chapter, item in batch
                ]
                db.add_all(chunks)
                await db.flush()
                db.add_all(
                    [
                        ChunkEmbedding(
                            chunk_id=chunk.id,
                            model=profile.embedding_model,
                            dimensions=dimensions,
                            embedding=vector,
                        )
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ]
                )
                profile.dimensions = dimensions
                profile.processed_chunks = start + len(batch)
                await db.commit()

            await db.execute(
                update(IndexProfile)
                .where(IndexProfile.novel_id == profile.novel_id)
                .values(is_active=False)
            )
            profile.status = "ready"
            profile.is_active = True
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        async with SessionLocal() as db:
            profile = await db.get(IndexProfile, profile_id)
            if profile is not None:
                profile.status = "failed"
                profile.is_active = False
                profile.error_message = str(exc)[:2000]
                await db.commit()
