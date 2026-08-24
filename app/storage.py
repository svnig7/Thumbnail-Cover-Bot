"""
Storage abstraction so the same bot logic works against either a flat JSON
file (zero setup, fine for a single-owner bot) or MongoDB (matches the
Motor/FastAPI pattern used elsewhere).

Data model (all keyed by Telegram user id, as a string):
  cover:{user_id}            -> {"file_id": str, "caption": str}
  season_current:{user_id}   -> season number (str) of the last active season
  season_ep:{user_id}:{season} -> episode counter (int)
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from app.config import settings


class JsonStore:
    """A tiny, async-safe, file-backed key/value store."""

    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump({}, f)

    def _read(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            return self._read().get(key)

    async def put(self, key: str, value: Any) -> None:
        async with self._lock:
            data = self._read()
            data[key] = value
            self._write(data)

    async def delete(self, key: str) -> None:
        async with self._lock:
            data = self._read()
            data.pop(key, None)
            self._write(data)


class MongoStore:
    """Motor-backed key/value store, one document per key in a single collection."""

    def __init__(self, uri: str, db_name: str):
        from motor.motor_asyncio import AsyncIOMotorClient  # imported lazily

        self._client = AsyncIOMotorClient(uri)
        self._col = self._client[db_name]["kv_store"]

    async def get(self, key: str) -> Optional[Any]:
        doc = await self._col.find_one({"_id": key})
        return doc["value"] if doc else None

    async def put(self, key: str, value: Any) -> None:
        await self._col.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)

    async def delete(self, key: str) -> None:
        await self._col.delete_one({"_id": key})


def _build_store():
    if settings.STORAGE_BACKEND == "mongo":
        if not settings.MONGO_URI:
            raise RuntimeError("STORAGE_BACKEND=mongo but MONGO_URI is not set")
        return MongoStore(settings.MONGO_URI, settings.MONGO_DB_NAME)
    return JsonStore(settings.JSON_STORE_PATH)


store = _build_store()


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

async def get_cover(user_id: int | str) -> Optional[dict]:
    return await store.get(f"cover:{user_id}")


async def set_cover(user_id: int | str, file_id: str, caption: str = "") -> None:
    await store.put(f"cover:{user_id}", {"file_id": file_id, "caption": caption})


async def get_current_season(user_id: int | str) -> Optional[str]:
    return await store.get(f"season_current:{user_id}")


async def set_current_season(user_id: int | str, season: str) -> None:
    await store.put(f"season_current:{user_id}", season)


async def get_episode_counter(user_id: int | str, season: str) -> int:
    val = await store.get(f"season_ep:{user_id}:{season}")
    return int(val) if val is not None else 0


async def set_episode_counter(user_id: int | str, season: str, count: int) -> None:
    await store.put(f"season_ep:{user_id}:{season}", count)
