from app.core.config import settings
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, PlainTextResponse
import urllib.parse
from app.core.watch_manager import watch_manager
from app.services.anime_service import AnimeService
from app.repositories.cache_repository import CacheRepository

ch_save = settings.SAVE_DATA
ch_use = settings.USE_SAVED_DATA
ch = None
if ch_use or ch_save:
    ch = CacheRepository(settings.REDIS_URL, settings.CACHE_LIFE_TIME)

anime_service = AnimeService(cache_repo=ch)

router = APIRouter()

@router.post("/")
async def index_form(request: Request):
    form_data = await request.form()

    if form_data.get("shikimori_id") and form_data.get("shikimori_id").strip():
        return RedirectResponse(
            url=f"/download/sh/{form_data['shikimori_id'].strip()}/",
            status_code=303
        )
    elif form_data.get("kinopoisk_id") and form_data.get("kinopoisk_id").strip():
        return RedirectResponse(
            url=f"/download/kp/{form_data['kinopoisk_id'].strip()}/",
            status_code=303
        )
    elif form_data.get("kdk") and form_data.get("kdk").strip():  # Kodik
        return RedirectResponse(
            url=f"/search/kdk/{form_data['kdk'].strip()}/",
            status_code=303
        )
    elif form_data.get("query") and form_data.get("query").strip():
        engine = request.session.get("search_engine", "kdk")
        return RedirectResponse(
            url=f"/search/{engine}/{form_data['query'].strip()}/",
            status_code=303
        )
    else:
        return RedirectResponse(url="/", status_code=303)

@router.post("/change_theme/")
def change_theme(request: Request):
    if "is_dark" in request.session:
        request.session["is_dark"] = not request.session["is_dark"]
    else:
        request.session["is_dark"] = True

    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)

@router.post("/change_engine/")
async def change_engine(request: Request):
    form_data = await request.form()
    engine = form_data.get("search_engine")

    if engine in ["kdk", "sh"]:
        request.session["search_engine"] = engine

    referer = request.headers.get("referer", "/")
    if referer and "/search/" in referer:
        try:
            path = urllib.parse.urlparse(referer).path
            parts = path.strip("/").split("/")
            if len(parts) >= 3 and parts[-3] == "search":
                query = urllib.parse.unquote(parts[-1])
                return RedirectResponse(
                    url=f"/search/{engine}/{urllib.parse.quote(query)}/",
                    status_code=303
                )
        except Exception:
            pass

    return RedirectResponse(url=referer, status_code=303)

@router.post("/create_room/")
def create_room(request: Request):
    referer = request.headers.get("referer", "/")
    # Split the referer URL path. Assuming it looks like /watch/sh/123/24-xyz/1/720/
    parsed = urllib.parse.urlparse(referer)
    parts = parsed.path.strip("/").split("/")
    
    # Validation based on legacy logic
    if len(parts) >= 5 and parts[0] == "watch":
        # parts: ['watch', '{serv}', '{id}', '{data}', '{seria}', '{quality}']
        # index:    0        1        2        3         4         5
        
        serv = parts[1]
        id = parts[2]
        data_part = parts[3]
        seria = int(parts[4])
        quality = int(parts[5]) if len(parts) > 5 else 720
        
        temp_data = data_part.split("-")
        room_data = {
            "serv": serv,
            "id": id,
            "series_count": int(temp_data[0]),
            "translation_id": temp_data[1],
            "seria": seria,
            "quality": quality,
            "pause": False,
            "play_time": 0,
        }
        rid = watch_manager.new_room(room_data)
        return RedirectResponse(url=f"/room/{rid}/", status_code=303)

    return RedirectResponse(url="/", status_code=303)

@router.post("/room/{rid}/")
async def change_room_seria_form(request: Request, rid: str):
    form_data = await request.form()
    seria = form_data.get("seria")
    if not seria:
        return RedirectResponse(url=f"/room/{rid}/", status_code=303)
        
    if not watch_manager.is_room(rid):
        return RedirectResponse(url="/", status_code=303)
        
    rdata = watch_manager.get_room_data(rid)
    rdata["seria"] = int(seria)
    rdata["play_time"] = 0
    watch_manager.update_room(rid, rdata)
    watch_manager.broadcast(rid, {"status": "update_page", "time": 0})
    return RedirectResponse(url=f"/room/{rid}/", status_code=303)

@router.get("/get_episode/{serv}/{shikimori_id}/{seria}/{translation_id}", response_class=PlainTextResponse)
def get_episode_url(serv: str, shikimori_id: str, seria: int, translation_id: str):
    """Returns the raw MPV stream URL for the frontend."""
    quality = 720  # default
    try:
        if serv == "sh":
            id_prefix = "sh"
            id_type = "shikimori"
        elif serv == "kp":
            id_prefix = "kp"
            id_type = "kinopoisk"
        else:
            raise HTTPException(status_code=400, detail="Invalid service")
            
        if ch_use and ch and ch.is_seria(id_prefix + shikimori_id, translation_id, seria):
            url = ch.get_seria(id_prefix + shikimori_id, translation_id, seria)
        else:
            url = anime_service.get_seria_link(shikimori_id, seria, translation_id, id_type=id_type)
            if ch_save and ch and not ch.is_seria(id_prefix + shikimori_id, translation_id, seria):
                try:
                    ch.add_seria(id_prefix + shikimori_id, translation_id, seria, url)
                except KeyError:
                    pass
                    
        if url.startswith("http"):
            straight_url = url
        else:
            straight_url = f"https:{url}{quality}.mp4"
            
        return straight_url
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
