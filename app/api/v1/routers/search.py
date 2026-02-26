from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import json
from app.core.config import settings
from app.services.anime_service import AnimeService
from app.core.security import get_current_user
from app.repositories.cache_repository import CacheRepository

ch_save = settings.SAVE_DATA
ch_use = settings.USE_SAVED_DATA
ch = None

if ch_save or ch_use:
    ch = CacheRepository(settings.REDIS_URL, settings.CACHE_LIFE_TIME)

anime_service = AnimeService(cache_repo=ch)

router = APIRouter()


@router.get("/api/search/stream/{db}/{query}/")
def search_stream(
    db: str, query: str, user: str = Depends(get_current_user)
):
    if db not in ["kdk", "sh"]:
        raise HTTPException(
            status_code=400, detail="Unsupported search database"
        )

    def generate():
        try:
            for item in anime_service.stream_search_data(query, db):
                yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "event: close\ndata: close\n\n"

    # StreamingResponse executes synchronous generators in a background thread
    # to avoid blocking the asynchronous FastAPI event loop.
    return StreamingResponse(generate(), media_type="text/event-stream")
