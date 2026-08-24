"""
Thin async wrapper around the Telegram Bot API.
"""
from __future__ import annotations

import httpx

from app.config import settings


def _api(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


async def tg(method: str, payload: dict) -> dict:
    """Call a Telegram Bot API JSON method."""
    url = f"{_api(settings.BOT_TOKEN)}/{method}"
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(url, json=payload)
    return res.json()


async def tg_multipart(method: str, data: dict, files: dict) -> dict:
    """Call a Telegram Bot API method that needs multipart upload (e.g. sendPhoto with raw bytes)."""
    url = f"{_api(settings.BOT_TOKEN)}/{method}"
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(url, data=data, files=files)
    return res.json()


def escape_html(text: str = "") -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send_message(chat_id, text: str, reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await tg("sendMessage", payload)


async def edit_message_text(chat_id, message_id, text: str) -> dict:
    return await tg("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})


async def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False) -> dict:
    return await tg(
        "answerCallbackQuery",
        {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert},
    )


async def get_chat_member(chat_id, user_id) -> dict:
    return await tg("getChatMember", {"chat_id": chat_id, "user_id": user_id})


async def delete_message(chat_id, message_id) -> dict:
    return await tg("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


async def edit_message_media_video(chat_id, message_id, video_file_id: str, cover_file_id: str | None, caption: str) -> dict:
    media = {
        "type": "video",
        "media": video_file_id,
        "caption": caption,
        "parse_mode": "HTML",
        "supports_streaming": True,
    }
    if cover_file_id:
        media["cover"] = cover_file_id
    return await tg("editMessageMedia", {"chat_id": chat_id, "message_id": message_id, "media": media})


async def send_video(chat_id, video_file_id: str, cover_file_id: str | None, caption: str) -> dict:
    payload = {
        "chat_id": chat_id,
        "video": video_file_id,
        "caption": caption,
        "parse_mode": "HTML",
        "supports_streaming": True,
    }
    if cover_file_id:
        payload["cover"] = cover_file_id
    return await tg("sendVideo", payload)


async def send_photo_bytes(chat_id, jpeg_bytes: bytes, caption_html: str) -> dict:
    """
    Send a raw JPEG (e.g. a resized TMDb poster) as a photo. Returns the raw
    Telegram API response so the caller can pull the resulting file_id back
    out (needed so it can be re-used as a video cover).
    """
    data = {"chat_id": str(chat_id), "caption": caption_html, "parse_mode": "HTML"}
    files = {"photo": ("poster.jpg", jpeg_bytes, "image/jpeg")}
    return await tg_multipart("sendPhoto", data, files)


def largest_photo_file_id(send_photo_response: dict) -> str | None:
    """Telegram returns an array of photo sizes; the last is the largest."""
    result = send_photo_response.get("result") or {}
    photos = result.get("photo") or []
    if not photos:
        return None
    return photos[-1]["file_id"]
