"""
Handles incoming Telegram updates for the merged bot:
  - force-subscribe gate
  - /skip command (adjust episode counter)
  - photo message  -> save as this user's cover thumbnail
  - video message  -> attach the saved cover and deliver
  - callback_query -> "I've joined" force-sub re-check

This is the same behaviour as the original Thumbnail Cover Bot worker,
ported to Python. The poster-picker's "Send" action (app/poster_routes.py)
also funnels into `storage.set_cover`, so a poster picked in the web UI
and a photo sent directly to the bot both land in the same place.
"""
from __future__ import annotations

import re

from app import storage
from app.config import settings
from app.telegram import (
    answer_callback_query,
    delete_message,
    edit_message_media_video,
    edit_message_text,
    escape_html,
    get_chat_member,
    send_message,
    send_video,
)

SEASON_RE = re.compile(r"🎞\s*Season\s*:\s*(\d+)", re.IGNORECASE)


async def is_subscribed(user_id) -> bool:
    if not settings.FORCE_SUB_CHANNEL:
        return True
    res = await get_chat_member(settings.FORCE_SUB_CHANNEL, user_id)
    if not res.get("ok"):
        return True  # fail-open if bot isn't admin / lookup fails
    status = (res.get("result") or {}).get("status")
    return status in ("member", "administrator", "creator")


async def send_force_sub_prompt(chat_id) -> None:
    link = settings.FORCE_SUB_LINK or f"https://t.me/{settings.FORCE_SUB_CHANNEL.lstrip('@')}"
    await send_message(
        chat_id,
        "🔒 You must join our channel to use this bot.",
        reply_markup={
            "inline_keyboard": [
                [{"text": "📢 Join Channel", "url": link}],
                [{"text": "✅ I've Joined", "callback_data": "check_sub"}],
            ]
        },
    )


async def handle_callback(query: dict) -> None:
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    user_id = query["from"]["id"]

    if query.get("data") == "check_sub":
        if await is_subscribed(user_id):
            await answer_callback_query(query["id"], "✅ Verified! You can use the bot now.")
            await edit_message_text(chat_id, message_id, "✅ Access granted. Send a photo to set your thumbnail.")
        else:
            await answer_callback_query(query["id"], "❌ You haven't joined yet.", show_alert=True)


async def handle_skip_command(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    parts = msg["text"].strip().split()[1:]  # drop "/skip"

    if len(parts) == 1:
        count_raw = parts[0]
        season = await storage.get_current_season(user_id)
        if not season:
            await send_message(chat_id, "❌ No active season found. Use /skip <season> <number> instead.")
            return
    elif len(parts) == 2:
        season, count_raw = parts
    else:
        await send_message(chat_id, "⚠️ Usage:\n/skip <number>\n/skip <season> <number>")
        return

    if not count_raw.lstrip("-").isdigit() or not str(season).isdigit():
        await send_message(chat_id, "⚠️ Season and number must be valid numbers.")
        return

    count = int(count_raw)
    await storage.set_episode_counter(user_id, str(season), count)
    await send_message(
        chat_id,
        f"✅ Season {season} episode counter set to {count}.\nNext video will be Episode {count + 1}.",
    )


async def handle_photo(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    photo = msg["photo"][-1]  # largest size
    caption = msg.get("caption", "") or ""

    await storage.set_cover(user_id, photo["file_id"], caption)

    season_match = SEASON_RE.search(caption)
    if season_match:
        season = season_match.group(1)
        await storage.set_episode_counter(user_id, season, 0)
        await storage.set_current_season(user_id, season)

    await send_message(chat_id, "✅ Thumbnail saved.\n\nNow send a video.")


async def handle_video(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]

    cover = await storage.get_cover(user_id)
    if not cover:
        await send_message(chat_id, "❌ No thumbnail found.\n\nSend a photo first.")
        return

    cover_file_id = cover["file_id"]
    image_caption = cover.get("caption", "") or ""

    season_match = SEASON_RE.search(image_caption)
    if season_match:
        season = season_match.group(1)
        episode = await storage.get_episode_counter(user_id, season) + 1
        await storage.set_episode_counter(user_id, season, episode)
        image_caption = SEASON_RE.sub(f"🎞 Season : {season} | Episode : {episode}", image_caption)

    video_caption = msg.get("caption", "") or ""
    final_caption = f"<code>{escape_html(video_caption)}</code>"
    if image_caption:
        final_caption += f"\n\n<blockquote>{escape_html(image_caption)}</blockquote>"

    processing = await send_message(chat_id, "⏳ Processing...")
    processing_message_id = processing["result"]["message_id"]

    result = await edit_message_media_video(chat_id, processing_message_id, msg["video"]["file_id"], cover_file_id, final_caption)

    if not result.get("ok"):
        await delete_message(chat_id, processing_message_id)
        await send_video(chat_id, msg["video"]["file_id"], cover_file_id, final_caption)


async def handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]

    if settings.FORCE_SUB_CHANNEL and not await is_subscribed(user_id):
        await send_force_sub_prompt(chat_id)
        return

    text = msg.get("text", "")
    if text.startswith("/skip"):
        await handle_skip_command(msg)
        return

    if "photo" in msg:
        await handle_photo(msg)
        return

    if "video" in msg:
        await handle_video(msg)
        return
