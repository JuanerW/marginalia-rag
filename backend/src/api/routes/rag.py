from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class QuestionRequest(BaseModel):
    novel_id: str
    question: str = Field(min_length=1, max_length=2000)
    reader_key: str = "local"


@router.post("/ask", status_code=501)
async def ask_question(payload: QuestionRequest) -> dict:
    """Stable API boundary for the upcoming LangChain retrieval chain."""
    return {
        "detail": "RAG pipeline is not implemented in the skeleton",
        "novel_id": payload.novel_id,
    }
