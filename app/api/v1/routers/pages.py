from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import os
import json
from app.core.config import settings
from app.core.security import create_access_token
from app.core.watch_manager import watch_manager
from app.services.anime_service import AnimeService
from app.repositories.cache_repository import CacheRepository
import logging

try:
    with open("translations.json", "r", encoding="utf-8") as f:
        translations = json.load(f)
except FileNotFoundError:
    translations = {}

ch_save = settings.SAVE_DATA
ch_use = settings.USE_SAVED_DATA
ch = None
if ch_use or ch_save:
    ch = CacheRepository(settings.REDIS_URL, settings.CACHE_LIFE_TIME)

anime_service = AnimeService(cache_repo=ch)
logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    is_dark = request.session.get("is_dark", False)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "is_dark": is_dark}
    )

@router.get("/guide", response_class=HTMLResponse)
def guide(request: Request):
    is_dark = request.session.get("is_dark", False)
    return templates.TemplateResponse(
        "guide.html",
        {"request": request, "is_dark": is_dark}
    )

@router.get("/search/{db}/{query}/", response_class=HTMLResponse)
def search_page(request: Request, db: str, query: str):
    if db in ["kdk", "sh"]:
        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "query": query,
                "db": db,
                "is_dark": request.session.get("is_dark", False),
                "api_url": settings.API_URL,
                "jwt_token": create_access_token({"sub": settings.ADMIN_USERNAME}),
            }
        )
    raise HTTPException(status_code=400, detail="Database not supported")

@router.get("/help/")
def help_redirect():
    return RedirectResponse(
        url="https://github.com/1Dradon1/anime-site/blob/main/README.MD",
        status_code=303
    )

@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(settings.FAVICON_PATH)

@router.get("/resources/{path:path}")
def resources(path: str):
    if os.path.exists(f"resources/{path}"):
        return FileResponse(f"resources/{path}")
    else:
        raise HTTPException(status_code=404, detail="Resource not found")

@router.get("/download/{serv}/{id}/", response_class=HTMLResponse)
def download_shiki_choose_translation(request: Request, serv: str, id: str):
    cache_wasnt_used = False
    user_agent = request.headers.get("user-agent", "")
    is_mobile = "Mobile" in user_agent or "Android" in user_agent or "iPhone" in user_agent

    if serv == "sh":
        if ch_use and ch.is_id("sh" + id) and ch.get_data_by_id("sh" + id).get("serial_data", {}):
            serial_data = ch.get_data_by_id("sh" + id)["serial_data"]
        else:
            try:
                serial_data = anime_service.get_serial_info(id, "shikimori")
            except Exception as ex:
                serial_data = {
                    "translations": [],
                    "top_translations": [],
                    "etc_translations": [],
                    "series_count": 0,
                    "error": True,
                    "debug_msg": str(ex) if settings.DEBUG else None,
                }

        cache_used = False
        if ch_use and ch.is_id("sh" + id):
            cached = ch.get_data_by_id("sh" + id)
            name = cached.get("title", "Неизвестно")
            pic = cached.get("image", settings.IMAGE_NOT_FOUND)
            score = cached.get("score", "Неизвестно")
            dtype = cached.get("type", "Неизвестно")
            date = cached.get("date", "Неизвестно")
            status = cached.get("status", "Неизвестно")
            rating = cached.get("rating", "Неизвестно")
            description = cached.get("description", "Неизвестно")
            if pic and "preview" not in pic:
                cache_used = True

        if not cache_used:
            cache_wasnt_used = True
            data = None
            try:
                data = anime_service.get_shiki_data(id)
                name = data["title"]
                pic = data["image"]
                score = data["score"]
                dtype = data["type"]
                date = data["date"]
                status = data["status"]
                rating = data["rating"]
                description = data["description"]
            except BaseException:
                name = "Неизвестно"
                pic = settings.IMAGE_NOT_FOUND
                score = "Неизвестно"
                dtype = "Неизвестно"
                date = "Неизвестно"
                status = "Неизвестно"
                rating = "Неизвестно"
                description = "Неизвестно"
                data = False
            finally:
                if ch_save and not ch.is_id("sh" + id):
                    ch.add_id(
                        "sh" + id,
                        name,
                        pic,
                        score,
                        data["status"] if data else "Неизвестно",
                        data["date"] if data else "Неизвестно",
                        data["year"] if data else 1970,
                        data["type"] if data else "Неизвестно",
                        data["rating"] if data else "Неизвестно",
                        data["description"] if data else "",
                        serial_data=serial_data,
                    )

        if ch_use and ch_save and ch.is_id("sh" + id) and not ch.get_data_by_id("sh" + id).get("serial_data"):
            ch.add_serial_data("sh" + id, serial_data)

        try:
            if ch_use and ch.is_id("sh" + id) and ch.get_data_by_id("sh" + id).get("related", []):
                related = ch.get_data_by_id("sh" + id)["related"]
            else:
                related = anime_service.get_related(id, "shikimori", sequel_first=True)
                if ch_save:
                    ch.add_related("sh" + id, related)
        except BaseException:
            related = []

        return templates.TemplateResponse(
            "info.html",
            {
                "request": request,
                "title": name,
                "image": pic,
                "score": score,
                "translations": serial_data.get("translations", []),
                "top_translations": serial_data.get("top_translations", []),
                "etc_translations": serial_data.get("etc_translations", []),
                "series_count": serial_data.get("series_count", 0),
                "id": id,
                "dtype": dtype,
                "date": date,
                "status": status,
                "rating": rating,
                "related": related,
                "description": description,
                "is_shiki": True,
                "cache_wasnt_used": cache_wasnt_used,
                "serv": serv,
                "error": serial_data.get("error", False),
                "debug_msg": serial_data.get("debug_msg", None),
                "is_dark": request.session.get("is_dark", False),
                "is_mobile": is_mobile,
                "shiki_mirror": getattr(settings, "SHIKIMORI_MIRROR", "shikimori.one"),
            }
        )

    elif serv == "kp":
        try:
            serial_data = anime_service.get_serial_info(id, "kinopoisk")
        except Exception as ex:
            serial_data = {
                "translations": [],
                "series_count": 0,
                "error": True,
                "debug_msg": str(ex) if settings.DEBUG else None,
            }

        return templates.TemplateResponse(
            "info.html",
            {
                "request": request,
                "title": "...",
                "image": settings.IMAGE_NOT_FOUND,
                "score": "...",
                "translations": serial_data.get("translations", []),
                "series_count": serial_data.get("series_count", 0),
                "id": id,
                "dtype": "...",
                "date": "...",
                "status": "...",
                "description": "...",
                "is_shiki": False,
                "serv": serv,
                "error": serial_data.get("error", False),
                "debug_msg": serial_data.get("debug_msg", None),
                "is_dark": request.session.get("is_dark", False),
            }
        )
    else:
        raise HTTPException(status_code=400)

@router.get("/download/{serv}/{id}/{data}/", response_class=HTMLResponse)
def download_choose_seria(request: Request, serv: str, id: str, data: str):
    data_parts = data.split("-")
    series = int(data_parts[0])
    return templates.TemplateResponse(
        "download.html",
        {
            "request": request,
            "series": series,
            "backlink": f"/download/{serv}/{id}/",
            "shikimori_id": id,
            "episodes": series,
            "is_dark": request.session.get("is_dark", False),
        }
    )

@router.get("/watch/{serv}/{id}/{data}/watch-{num}/")
def redirect_to_player(serv: str, id: str, data: str, num: int):
    if data[0] == "0":
        return RedirectResponse(url=f"/watch/{serv}/{id}/{data}/0/", status_code=303)
    else:
        return RedirectResponse(url=f"/watch/{serv}/{id}/{data}/{num}/", status_code=303)

@router.get("/watch/{serv}/{id}/{data}/{seria}/{old_quality}/q-{quality}/")
@router.get("/watch/{serv}/{id}/{data}/{seria}/{old_quality}/{timing}/q-{quality}/")
def change_watch_quality(serv: str, id: str, data: str, seria: int, old_quality: str, quality: str, timing: int = None):
    return RedirectResponse(
        url=f"/watch/{serv}/{id}/{data}/{seria}/{quality}/{str(timing) + '/' if timing else ''}",
        status_code=303
    )

@router.get("/watch/{serv}/{id}/{data}/{seria}/q-{quality}/")
@router.get("/watch/{serv}/{id}/{data}/{seria}/q-{quality}/{timing}/")
def redirect_to_old_type_quality(serv: str, id: str, data: str, seria: int, quality: str, timing: int = 0):
    return RedirectResponse(
        url=f"/watch/{serv}/{id}/{data}/{seria}/{quality}/{str(timing) + '/' if timing else ''}",
        status_code=303
    )

@router.get("/watch/{serv}/{id}/{data}/{seria}/", response_class=HTMLResponse)
@router.get("/watch/{serv}/{id}/{data}/{seria}/{quality}/", response_class=HTMLResponse)
@router.get("/watch/{serv}/{id}/{data}/{seria}/{quality}/{timing}/", response_class=HTMLResponse)
def watch(request: Request, serv: str, id: str, data: str, seria: int, quality: str = "720", timing: int = 0):
    try:
        data_parts = data.split("-")
        series = int(data_parts[0])
        translation_id = str(data_parts[1])
        title = None
        if serv == "sh":
            id_type = "shikimori"
            if ch_use:
                try:
                    title = ch.get_data_by_id("sh" + id)["title"] if ch.get_data_by_id("sh" + id) else None
                except BaseException:
                    title = None

            if ch_use and ch.is_seria("sh" + id, translation_id, seria):
                url = ch.get_seria("sh" + id, translation_id, seria)
            else:
                url = anime_service.get_seria_link(id, seria, translation_id)
                if ch_save and not ch.is_seria("sh" + id, translation_id, seria):
                    try:
                        ch.add_seria("sh" + id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif serv == "kp":
            id_type = "kinopoisk"
            if ch_use:
                try:
                    title = ch.get_data_by_id("kp" + id)["title"] if ch.get_data_by_id("kp" + id) else None
                except BaseException:
                    title = None
            if ch_use and ch.is_seria("kp" + id, translation_id, seria):
                url = ch.get_seria("kp" + id, translation_id, seria)
            else:
                url = anime_service.get_seria_link(id, seria, translation_id)
                if ch_save and not ch.is_seria("kp" + id, translation_id, seria):
                    try:
                        ch.add_seria("kp" + id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            raise HTTPException(status_code=400)

        if url.startswith("http"):
            straight_url = url
        else:
            straight_url = f"https:{url}{quality}.mp4"
        data_joined = "-".join(data_parts)
        redirect_url = f"/download/{serv}/{id}/{data_joined}/old-{quality}-{seria}"

        return templates.TemplateResponse(
            "watch.html",
            {
                "request": request,
                "url": redirect_url,
                "seria": seria,
                "series": series,
                "id": id,
                "id_type": id_type,
                "data": "-".join(data_parts),
                "quality": quality,
                "serv": serv,
                "straight_url": straight_url,
                "allow_watch_together": getattr(settings, "ALLOW_WATCH_TOGETHER", True),
                "is_dark": request.session.get("is_dark", False),
                "timing": timing,
                "title": title,
            }
        )
    except BaseException:
        raise HTTPException(status_code=404)

@router.get("/room/{rid}/", response_class=HTMLResponse)
def room(request: Request, rid: str):
    if not watch_manager.is_room(rid):
        raise HTTPException(status_code=404)
    rd = watch_manager.get_room_data(rid)
    watch_manager.room_used(rid)
    try:
        id = rd["id"]
        seria = rd["seria"]
        series = rd["series_count"]
        translation_id = str(rd["translation_id"])
        quality = rd["quality"]

        if rd["serv"] == "sh":
            id_type = "shikimori"
            if ch_use and ch.is_seria("sh" + id, translation_id, seria):
                url = ch.get_seria("sh" + id, translation_id, seria)
            else:
                url = anime_service.get_seria_link(id, seria, translation_id)
                if ch_save and not ch.is_seria("sh" + id, translation_id, seria):
                    try:
                        ch.add_seria("sh" + id, translation_id, seria, url)
                    except KeyError:
                        pass
        elif rd["serv"] == "kp":
            id_type = "kinopoisk"
            if ch_use and ch.is_seria("kp" + id, translation_id, seria):
                url = ch.get_seria("kp" + id, translation_id, seria)
            else:
                url = anime_service.get_seria_link(id, seria, translation_id)
                if ch_save and not ch.is_seria("kp" + id, translation_id, seria):
                    try:
                        ch.add_seria("kp" + id, translation_id, seria, url)
                    except KeyError:
                        pass
        else:
            raise HTTPException(status_code=400)

        if url.startswith("http"):
            straight_url = url
        else:
            straight_url = f"https:{url}{quality}.mp4"
        download_url = f"/download/{rd['serv']}/{id}/{series}-{translation_id}/{quality}-{seria}"

        return templates.TemplateResponse(
            "room.html",
            {
                "request": request,
                "url": download_url,
                "seria": seria,
                "series": series,
                "id": id,
                "id_type": id_type,
                "data": f"{series}-{translation_id}",
                "quality": quality,
                "serv": rd["serv"],
                "straight_url": straight_url,
                "start_time": rd["play_time"],
                "is_dark": request.session.get("is_dark", False),
                "ws_url": settings.WS_URL,
                "jwt_token": create_access_token({"sub": settings.ADMIN_USERNAME}),
            }
        )
    except BaseException:
        raise HTTPException(status_code=500)

@router.get("/room/{rid}/cs-{seria}/")
def change_room_seria(rid: str, seria: int):
    if not watch_manager.is_room(rid):
        raise HTTPException(status_code=400)
    rdata = watch_manager.get_room_data(rid)
    rdata["seria"] = seria
    rdata["play_time"] = 0
    watch_manager.room_used(rid)
    watch_manager.broadcast(rid, {"status": "update_page", "time": 0})
    return RedirectResponse(url=f"/room/{rid}/", status_code=303)

@router.get("/room/{rid}/cq-{quality}/")
def change_room_quality(rid: str, quality: int):
    if not watch_manager.is_room(rid):
        raise HTTPException(status_code=400)
    rdata = watch_manager.get_room_data(rid)
    rdata["quality"] = quality
    watch_manager.room_used(rid)
    watch_manager.broadcast(rid, {"status": "update_page", "time": rdata.get("play_time", 0)})
    return RedirectResponse(url=f"/room/{rid}/", status_code=303)
