from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app import bot_handlers
from app.config import settings

router = APIRouter()


@router.get("/health", response_class=PlainTextResponse)
async def health():
    return "Thumbnail Cover Bot Running ✅"


@router.post("/webhook")
async def webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if settings.WEBHOOK_SECRET and x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    update = await request.json()
    try:
        if "message" in update:
            await bot_handlers.handle_message(update["message"])
        elif "callback_query" in update:
            await bot_handlers.handle_callback(update["callback_query"])
    except Exception as e:  # keep webhook resilient; Telegram retries on non-2xx
        print(f"webhook error: {e}")

    return PlainTextResponse("OK")
