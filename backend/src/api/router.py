from fastapi import APIRouter

from src.api.routes import novels, progress, rag

api_router = APIRouter()
api_router.include_router(novels.router, prefix="/novels", tags=["novels"])
api_router.include_router(progress.router, prefix="/novels", tags=["reading progress"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
