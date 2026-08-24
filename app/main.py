from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.poster_routes import router as poster_router
from app.webhook_routes import router as webhook_router

app = FastAPI(title="Thumbnail Cover Bot", version="1.0.0")

app.include_router(webhook_router)
app.include_router(poster_router)

# Serves anything else dropped in /static (e.g. custom assets referenced by index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/admin/set_webhook")
async def set_webhook():
    """
    Convenience endpoint: registers this deployment's /webhook URL with
    Telegram. Requires PUBLIC_BASE_URL to be set. Call once after deploy.
    """
    if not settings.BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured.")
    if not settings.PUBLIC_BASE_URL:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured.")

    payload = {"url": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/webhook"}
    if settings.WEBHOOK_SECRET:
        payload["secret_token"] = settings.WEBHOOK_SECRET

    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setWebhook", json=payload)
    return res.json()
