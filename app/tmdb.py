"""
TMDb search/lookup/details + caption formatting + poster resizing.
Port of the tmdb.tgbt.workers.dev logic to Python.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

import httpx
from PIL import Image

from app.config import settings

TMDB_BASE = "https://api.themoviedb.org/3"
CAPTION_MAX = 1024  # Telegram photo caption limit


class TmdbError(Exception):
    pass


async def tmdb_get(path: str, params: Optional[dict] = None) -> dict:
    if not settings.TMDB_API_KEY:
        raise TmdbError("TMDB_API_KEY is not configured.")
    query = {"api_key": settings.TMDB_API_KEY, **{k: v for k, v in (params or {}).items() if v not in (None, "")}}
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(f"{TMDB_BASE}{path}", params=query)
    data = res.json() if res.content else {}
    if res.status_code >= 400:
        raise TmdbError(data.get("status_message") or f"TMDb responded {res.status_code}")
    return data


def parse_query_for_year(query: str) -> tuple[str, Optional[int]]:
    """Detects a trailing year in a query like 'RRR 2022'."""
    trimmed = query.strip()
    parts = trimmed.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
        year = int(parts[1])
        if 1870 < year <= date.today().year + 2:
            return parts[0].strip(), year
    return trimmed, None


async def search(q: str) -> dict:
    q = q.strip()
    if not q:
        raise TmdbError("Missing query")

    title, year = parse_query_for_year(q)

    if year:
        movies_task = tmdb_get("/search/movie", {"query": title, "year": year})
        tv_task = tmdb_get("/search/tv", {"query": title, "first_air_date_year": year})
        try:
            movie_data = await movies_task
            movies = [{**r, "media_type": "movie"} for r in movie_data.get("results", [])]
        except TmdbError:
            movies = []
        try:
            tv_data = await tv_task
            tv = [{**r, "media_type": "tv"} for r in tv_data.get("results", [])]
        except TmdbError:
            tv = []
        merged = sorted(movies + tv, key=lambda r: r.get("popularity", 0), reverse=True)
        if merged:
            return {"results": merged, "mode": "year", "title": title, "year": year}
        multi = await tmdb_get("/search/multi", {"query": q, "include_adult": False})
        results = [r for r in multi.get("results", []) if r.get("media_type") in ("movie", "tv")]
        return {"results": results, "mode": "multi", "query": q}

    multi = await tmdb_get("/search/multi", {"query": q, "include_adult": False})
    results = [r for r in multi.get("results", []) if r.get("media_type") in ("movie", "tv")]
    return {"results": results, "mode": "multi", "query": q}


async def lookup_by_tmdb_id(tmdb_id: str, media_type: str) -> dict:
    if not tmdb_id.isdigit():
        raise TmdbError("TMDb ID must be a whole number.")
    media_type = "tv" if media_type == "tv" else "movie"
    try:
        details = await tmdb_get(f"/{media_type}/{tmdb_id}")
    except TmdbError:
        raise TmdbError(f"No {'TV show' if media_type == 'tv' else 'movie'} found with TMDb ID {tmdb_id}.")
    item = {
        "id": details.get("id"),
        "media_type": media_type,
        "title": details.get("title"),
        "name": details.get("name"),
        "release_date": details.get("release_date"),
        "first_air_date": details.get("first_air_date"),
        "poster_path": details.get("poster_path"),
    }
    return {"results": [item]}


async def lookup_by_imdb_id(imdb_id: str) -> dict:
    import re

    if not re.match(r"^tt\d{6,9}$", imdb_id, re.IGNORECASE):
        raise TmdbError("IMDb ID should look like tt1160419.")
    data = await tmdb_get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
    results = [{**r, "media_type": "movie"} for r in data.get("movie_results", [])] + [
        {**r, "media_type": "tv"} for r in data.get("tv_results", [])
    ]
    return {"results": results}


async def get_details(media_type: str, tmdb_id: str) -> dict:
    media_type = "tv" if media_type == "tv" else "movie"
    return await tmdb_get(f"/{media_type}/{tmdb_id}", {"append_to_response": "external_ids"})


def build_caption(media_type: str, details: dict, season: Optional[dict]) -> str:
    genres = ", ".join(g["name"] for g in details.get("genres", [])) or "N/A"
    imdb_id = (details.get("external_ids") or {}).get("imdb_id") or "N/A"
    lines = []

    if media_type == "movie":
        title = details.get("title") or "Untitled"
        year = (details.get("release_date") or "")[:4] or "—"
        plot_source = (details.get("overview") or "").strip() or "No plot summary available."
        lines.append(f"🎬 Title : {title}")
        lines.append(f"📅 Year : {year}")
    else:
        title = details.get("name") or "Untitled"
        year = (season.get("air_date") or "")[:4] if season and season.get("air_date") else (
            (details.get("first_air_date") or "")[:4] or "—"
        )
        plot_source = (
            ((season or {}).get("overview") or "").strip()
            or (details.get("overview") or "").strip()
            or "No plot summary available."
        )
        lines.append(f"📺 Title : {title}")
        lines.append(f"🎞 Season : {season.get('season_number')}")
        lines.append(f"📅 Year : {year}")

    lines.append(f"🎭 Genre : {genres}")
    footer = f"🆔 TMDB ID : {details.get('id')} | IMDb ID : {imdb_id}"

    def assemble(plot: str) -> str:
        return "\n".join([*lines, f"📝 Plot : {plot}", footer])

    caption = assemble(plot_source)
    if len(caption) > CAPTION_MAX:
        overflow = len(caption) - CAPTION_MAX + 1
        trimmed_len = max(0, len(plot_source) - overflow)
        trimmed_plot = plot_source[:trimmed_len].rstrip() + "…"
        caption = assemble(trimmed_plot)
        if len(caption) > CAPTION_MAX:
            caption = caption[:CAPTION_MAX]
    return caption


def stretch_to_landscape(image_bytes: bytes, size=(1280, 720), quality=92) -> bytes:
    """Stretches (not crops) a poster into a 1280x720 landscape JPEG."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    resized = img.resize(size, Image.LANCZOS)
    out = io.BytesIO()
    resized.save(out, format="JPEG", quality=quality)
    return out.getvalue()


async def download_poster(poster_path: str) -> bytes:
    url = f"https://image.tmdb.org/t/p/original{poster_path}"
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url)
    if res.status_code >= 400:
        raise TmdbError("Could not download poster from TMDb.")
    return res.content
