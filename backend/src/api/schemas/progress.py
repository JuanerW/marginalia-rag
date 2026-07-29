from pydantic import BaseModel, Field


class ProgressUpdate(BaseModel):
    display_chapter_number: int = Field(ge=1)
    display_offset: int = Field(ge=0)
    reader_key: str = Field(default="local", min_length=1, max_length=128)


class ProgressResponse(BaseModel):
    display_chapter_number: int
    display_offset: int
    furthest_chapter_number: int
    furthest_offset: int
    reader_key: str

