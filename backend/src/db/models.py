import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255))
    source_filename: Mapped[str] = mapped_column(String(512))
    source_format: Mapped[str] = mapped_column(String(16), default="txt")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    encoding: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="novel", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("novel_id", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    spine_index: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    source_href: Mapped[str | None] = mapped_column(String(1024))
    fragment_id: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)

    novel: Mapped[Novel] = relationship(back_populates="chapters")


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    __table_args__ = (UniqueConstraint("novel_id", "reader_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    reader_key: Mapped[str] = mapped_column(String(128), default="local")
    display_chapter_number: Mapped[int] = mapped_column(Integer, default=1)
    display_offset: Mapped[int] = mapped_column(Integer, default=0)
    furthest_chapter_number: Mapped[int] = mapped_column(Integer, default=1)
    furthest_offset: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IndexProfile(Base):
    __tablename__ = "index_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE")
    )
    strategy: Mapped[str] = mapped_column(String(32))
    target_size: Mapped[int] = mapped_column(Integer)
    max_size: Mapped[int] = mapped_column(Integer)
    overlap: Mapped[int] = mapped_column(Integer)
    embedding_model: Mapped[str] = mapped_column(String(255))
    dimensions: Mapped[int | None] = mapped_column(Integer)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="indexing")
    error_message: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"))
    chapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    index_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("index_profiles.id", ondelete="CASCADE")
    )
    chapter_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )
    profile: Mapped[IndexProfile] = relationship(back_populates="chunks")


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", "model"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(String(255))
    dimensions: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector())

    chunk: Mapped[Chunk] = relationship(back_populates="embeddings")
