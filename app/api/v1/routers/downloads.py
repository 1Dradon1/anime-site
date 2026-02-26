from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os
import json
from celery.result import AsyncResult
from app.core.celery_app import celery_app
from app.tasks.media_tasks import download_and_concat_task
from app.core.config import settings
from app.services.media_service import MediaService

# Instantiate media service if needed for get_path
# However, for simply serving the file, we can keep the local logic or use the service
router = APIRouter()
templates = Jinja2Templates(directory="templates")

try:
    with open("translations.json", "r", encoding="utf-8") as f:
        translations = json.load(f)
except FileNotFoundError:
    translations = {}

ch_save = settings.SAVE_DATA
ch_use = settings.USE_SAVED_DATA
ch = None
if ch_use or ch_save:
    from app.repositories.cache_repository import CacheRepository
    ch = CacheRepository(settings.REDIS_URL, settings.CACHE_LIFE_TIME)


@router.get("/api/tasks/{task_id}")
def get_task_status(task_id: str):
    """Check status of a running Celery Fast Download task."""
    task_result = AsyncResult(task_id, app=celery_app)

    response = {"status": task_result.status, "task_id": task_id}

    if task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.info)

    return JSONResponse(content=response)


@router.get("/api/downloads/{hsh}/{filename}")
def download_prepared_file(hsh: str, filename: str):
    """Serve the final generated file."""
    try:
        media_service = MediaService(None) # Anime service not needed for path resolution
        path = media_service.get_path(hsh)
        if not path or not os.path.exists(path):
            raise FileNotFoundError()
        return FileResponse(os.path.abspath(path), filename=filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404,
                            detail="File not prepared or expired.")


@router.get("/fast_download_act/{id_type}-{id}-{seria_num}-{translation_id}-{quality}/")
@router.get("/fast_download_act/{id_type}-{id}-{seria_num}-{translation_id}-{quality}-{max_series}/")
def fast_download_act(request: Request, id_type: str, id: str, seria_num: int,
                      translation_id: str, quality: str, max_series: int = 12):
    token = request.cookies.get("token")
    if not token:
        if settings.KODIK_TOKEN:
            token = settings.KODIK_TOKEN
        else:
            raise HTTPException(status_code=401)

    translation = translations.get(translation_id, "Неизвестно")
    add_zeros = len(str(max_series))

    fname_base = (
        f"Перевод-{translation}-{quality}p" if seria_num == 0 else
        f"Серия-{str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p"
    )

    metadata = {}
    if settings.USE_SAVED_DATA and ch and ch.is_id("sh" + id):
        cached_data = ch.get_data_by_id("sh" + id)
        if seria_num != 0:
            fname_base = f"{
                cached_data['title']}-Серия-{
                str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p"
        else:
            fname_base = f"{
                cached_data['title']}-Перевод-{translation}-{quality}p"

        metadata = {
            "title": cached_data["title"] + " - Серия-" + str(seria_num) if seria_num != 0 else cached_data["title"],
            "year": cached_data.get("year", ""),
            "date": cached_data.get("year", ""),
            "comment": cached_data.get("description", ""),
            "artist": translation,
            "track": seria_num,
        }

    if len(fname_base) > 128:
        if len(translation) > 100:
            fname_base = f"{quality}p" if seria_num == 0 else f"Серия-{
                str(seria_num).zfill(add_zeros)}-{quality}p"
        else:
            fname_base = f"Перевод-{translation}-{quality}p" if seria_num == 0 else f"Серия-{
                str(seria_num).zfill(add_zeros)}-Перевод-{translation}-{quality}p"

    fname = (
        fname_base.replace("\\", "-")
        .replace("/", "-")
        .replace(":", "-")
        .replace("*", "-")
        .replace('"', "'")
        .replace("»", "'")
        .replace("«", "'")
        .replace("„", "'")
        .replace("“", "'")
        .replace("<", "[")
        .replace("]", ")")
        .replace("|", "-")
        .replace("--", "-")
        + ".mp4"
    )

    task = download_and_concat_task.delay(
        id=id,
        id_type=id_type,
        seria_num=seria_num,
        translation_id=translation_id,
        quality=quality,
        token=token,
        filename=fname,
        metadata=metadata,
    )

    return JSONResponse(content={"task_id": str(task.id)})


@router.get("/fast_download/{id_type}-{id}-{seria_num}-{translation_id}-{quality}/")
@router.get("/fast_download/{id_type}-{id}-{seria_num}-{translation_id}-{quality}-{max_series}/")
def fast_download_prepare(request: Request, id_type: str, id: str,
                          seria_num: int, translation_id: str, quality: str, max_series: int = 12):
    return templates.TemplateResponse(
        "fast_download_prepare.html",
        {
            "request": request,
            "seria_num": seria_num,
            "url": f"/fast_download_act/{id_type}-{id}-{seria_num}-{translation_id}-{quality}-{max_series}/",
            "past_url": request.headers.get("referer", f"/download/{id_type}/{id}/"),
            "is_dark": request.session.get("is_dark", False),
        }
    )


@router.get("/download/{version}")
def download_file(version: str):
    if version == "low":
        return FileResponse("static/dgnmpv-low-end.zip",
                            filename="dgnmpv-low-end.zip")
    elif version == "high":
        return FileResponse("static/dgnmpv.zip", filename="dgnmpv.zip")
    raise HTTPException(status_code=404, detail="Version not found")
