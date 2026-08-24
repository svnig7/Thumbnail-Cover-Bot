# Thumbnail Cover Bot (Python)

A single FastAPI service that merges two previously separate Cloudflare
Workers into one Python app:

1. **Thumbnail Cover Bot** — Telegram webhook bot. Send it a photo → it's
   saved as your "cover" thumbnail. Send it a video next → it comes back
   out with that photo attached as the video's cover (via Telegram's
   `cover` parameter), plus force-subscribe gating and a `/skip` command
   for episode counters.
2. **TMDB Posters** — a small web UI to search TMDb and grab a poster.

## What changed in the merge

The poster picker used to `sendPhoto` straight into a Telegram group or
channel (`TG_CHAT_IDS`). **That's gone.** Now, picking a poster:

1. Delivers the resized poster photo to the bot's own **private chat**
   with you (`OWNER_CHAT_ID`) — never a group or channel.
2. Immediately reads back the `file_id` Telegram just gave it and stores
   it via `storage.set_cover(...)` — the exact same place a photo you
   send the bot directly gets stored.

So "pick a poster in the browser" and "send the bot a photo" both end up
as the same cover, ready to be attached to the next video you send.

## Project layout

```
app/
  config.py          settings from environment variables
  telegram.py         Telegram Bot API wrapper (JSON + multipart)
  storage.py           key/value storage: JSON file (default) or MongoDB
  tmdb.py              TMDb search/lookup/details, caption builder, poster resize
  bot_handlers.py      webhook logic: force-sub, /skip, save cover, send video
  poster_routes.py     /api/search, /api/lookup, /api/details, /api/send + UI
  webhook_routes.py    /webhook, /health
  main.py              FastAPI app assembly + /admin/set_webhook helper
static/
  index.html           the poster-picker frontend
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN, TMDB_API_KEY, OWNER_CHAT_ID
```

Find your `OWNER_CHAT_ID`: message your bot once (e.g. `/start`), then
check `https://api.telegram.org/bot<TOKEN>/getUpdates` — your numeric
Telegram user id is `message.from.id`.

Run locally:

```bash
uvicorn app.main:app --reload
```

## Deploying (Render / Railway — matches your usual stack)

1. Push this repo to GitHub.
2. Create a new **Web Service** on Render (or Railway), pointing at the
   repo. It'll pick up the `Procfile` automatically.
3. Set the environment variables from `.env.example` in the host's
   dashboard (`STORAGE_BACKEND=json` is fine for a single-owner bot; the
   JSON file lives at `JSON_STORE_PATH` inside the container — on Render
   free tier this resets on redeploy, so switch to `mongo` + `MONGO_URI`
   if you need persistence across deploys).
4. Set `PUBLIC_BASE_URL` to the deployed HTTPS URL.
5. After first deploy, register the webhook once:
   ```bash
   curl -X POST https://your-app.onrender.com/admin/set_webhook
   ```
   (equivalent to calling Telegram's `setWebhook` with `<PUBLIC_BASE_URL>/webhook`).

## Using it

- Open `/` in a browser → search TMDb → hit **Send to bot PM** (movies)
  or **Select seasons → Send selected** (TV). The poster lands in your
  bot's DM and is saved as your cover.
- Or skip the web UI entirely: DM the bot a photo yourself (optionally
  with a caption containing `🎞 Season : N` to enable auto episode
  numbering), then send a video — it comes back with that photo as the
  cover and episode number auto-incremented.
- `/skip <number>` or `/skip <season> <number>` manually adjusts the
  episode counter for the active/given season.

## Notes

- `cover=` on `sendVideo`/`editMessageMedia` requires a Bot API version
  that supports video covers — same requirement as the original worker.
- `FORCE_SUB_CHANNEL` is optional; leave blank to disable the gate.
- Switching `STORAGE_BACKEND` to `mongo` requires no code changes —
  `app/storage.py` is a drop-in abstraction over both backends.
