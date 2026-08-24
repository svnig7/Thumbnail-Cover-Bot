"""
Central configuration, loaded from environment variables.
Copy .env.example to .env and fill in values, or set these directly
on your host (Render / Railway / etc).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


class Settings:
    # --- Telegram ---
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")  # optional, checked on /webhook

    # The chat the poster picker delivers posters to, and where covers are
    # saved against. This must be a chat the bot can message directly, i.e.
    # the numeric Telegram user id of the admin/owner who has started a PM
    # with the bot. Group/channel ids are intentionally NOT used here.
    OWNER_CHAT_ID: str = os.getenv("OWNER_CHAT_ID", "")

    # --- Force subscribe (optional) ---
    FORCE_SUB_CHANNEL: str = os.getenv("FORCE_SUB_CHANNEL", "")  # e.g. @yourchannel
    FORCE_SUB_LINK: str = os.getenv("FORCE_SUB_LINK", "")

    # --- TMDb ---
    TMDB_API_KEY: str = os.getenv("TMDB_API_KEY", "")

    # --- Storage backend ---
    # "json"  -> flat JSON file on disk (default, zero setup)
    # "mongo" -> MongoDB via MONGO_URI
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "json")
    JSON_STORE_PATH: str = os.getenv("JSON_STORE_PATH", "data/store.json")
    MONGO_URI: str = os.getenv("MONGO_URI", "")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "thumbnail_cover_bot")

    # --- App ---
    PORT: int = int(os.getenv("PORT", "8000"))
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")  # used for /set_webhook helper


settings = Settings()
