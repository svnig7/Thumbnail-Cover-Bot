"""
TMDb poster picker API. This used to send posters straight to a Telegram
group/channel (TG_CHAT_IDS). It now does the opposite: it delivers the
poster to the bot's own PM (settings.OWNER_CHAT_ID) and immediately saves
the resulting file_id as that user's cover thumbnail, exactly like sending
a photo to the bot directly would.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import storage, tmdb
from app.config import settings
from app.telegram import largest_photo_file_id, send_photo_bytes

router = APIRouter()


@router.get("/api/search")
async def api_search(q: str = ""):
    try:
        return await tmdb.search(q)
    except tmdb.TmdbError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/lookup")
async def api_lookup(type: str, id: str, mediaType: str = "movie"):
    try:
        if type == "tmdbid":
            return await tmdb.lookup_by_tmdb_id(id, mediaType)
        if type == "imdbid":
            return await tmdb.lookup_by_imdb_id(id)
        raise HTTPException(status_code=400, detail="Unknown lookup type")
    except tmdb.TmdbError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/details")
async def api_details(type: str = "movie", id: str = ""):
    if not id:
        raise HTTPException(status_code=400, detail="Missing id")
    try:
        return await tmdb.get_details(type, id)
    except tmdb.TmdbError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/send")
async def api_send(request: Request):
    if not settings.BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured.")
    if not settings.OWNER_CHAT_ID:
        raise HTTPException(
            status_code=500,
            detail="OWNER_CHAT_ID is not configured — the bot needs to know which PM to deliver posters to.",
        )

    body = await request.json()
    media_type = "tv" if body.get("media_type") == "tv" else "movie"
    tmdb_id = body.get("id")
    if not tmdb_id:
        raise HTTPException(status_code=400, detail="Missing id")

    try:
        details = await tmdb.get_details(media_type, tmdb_id)
    except tmdb.TmdbError as e:
        raise HTTPException(status_code=502, detail=f"TMDb error: {e}")

    season = None
    if media_type == "movie":
        poster_path = details.get("poster_path")
        label = details.get("title") or "Untitled"
    else:
        season_number = body.get("season_number")
        season = next((s for s in details.get("seasons", []) if s.get("season_number") == season_number), None)
        if not season:
            raise HTTPException(status_code=404, detail="Season not found")
        poster_path = season.get("poster_path") or details.get("poster_path")
        label = f"{details.get('name') or 'Untitled'} — Season {season_number}"

    if not poster_path:
        raise HTTPException(status_code=400, detail="No poster available for this item.")

    caption = tmdb.build_caption(media_type, details, season)

    try:
        original_bytes = await tmdb.download_poster(poster_path)
    except tmdb.TmdbError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        jpeg_bytes = tmdb.stretch_to_landscape(original_bytes)
        stretched = True
    except Exception:
        jpeg_bytes = original_bytes
        stretched = False

    # Deliver to the bot's PM instead of a group/channel.
    caption_html = f"<code>{tmdb.build_caption(media_type, details, season)}</code>"
    tg_response = await send_photo_bytes(settings.OWNER_CHAT_ID, jpeg_bytes, caption_html)
    if not tg_response.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=tg_response.get("description") or "Failed to deliver poster to the bot PM.",
        )

    file_id = largest_photo_file_id(tg_response)
    saved_as_cover = False
    if file_id:
        await storage.set_cover(settings.OWNER_CHAT_ID, file_id, caption)
        if season is not None:
            season_number = str(season.get("season_number"))
            await storage.set_episode_counter(settings.OWNER_CHAT_ID, season_number, 0)
            await storage.set_current_season(settings.OWNER_CHAT_ID, season_number)
        saved_as_cover = True

    return {
        "ok": True,
        "stretched": stretched,
        "label": label,
        "delivered_to": "bot_pm",
        "saved_as_cover": saved_as_cover,
    }


@router.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()
