# Kwork Parser

Telegram bot that polls Kwork buyer projects by selected categories and publishes new orders to a channel.

## Setup

1. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   The bot can use an installed Kwork SDK (`kwork.Kwork` or `pykwork.KworkClient`) for categories and projects. If no supported SDK is available, it falls back to the legacy HTTP client.

2. Create `.env` from `.env.example` and fill in:

   - `BOT_TOKEN` - Telegram bot token.
   - `CHANNEL_ID` - target channel id.
   - `ADMIN_IDS` - comma-separated Telegram user ids allowed to use bot commands.
   - `POLL_INTERVAL` - polling interval in seconds, default is `300`.
   - `KWORK_LOGIN`, `KWORK_PASSWORD`, `KWORK_PHONE` - Kwork account credentials.
   - `KWORK_MOBILE_AUTH` - optional authorization header override for Kwork mobile API.
   - `CATEGORY_PROFILE` - fallback category preset before categories are selected in the bot.
   - `CATEGORY_IDS` - optional fallback ids that replace the selected fallback preset.
   - `CATEGORY_EXTRA_IDS` - optional fallback ids added to the selected fallback preset.
   - `CATEGORY_EXCLUDE_IDS` - optional fallback ids removed from the final fallback selection.

3. Run:

   ```bash
   python main.py
   ```

Runtime state is stored in `seen_ids.json` by default. Override it with `SEEN_IDS_FILE` when needed.
Discovered Kwork categories and selected category ids are stored in `category_catalog.json` and `selected_category_ids.json`.

Use the bot button `📂 Категории` to refresh Kwork category ids and choose which order categories should be published.
