# Kwork Category Selection

## Sources checked

- Official Kwork category tree: https://kwork.ru/categories
- English Kwork category tree: https://kwork.com/categories
- Unofficial GitHub wrapper for Kwork closed API: https://github.com/CrazyMan-IK/kwork-api
- GitHub example with projects and favourite categories methods: https://github.com/CrazyMan-IK/kwork-api/blob/main/examples/api_example.js
- Habr Q&A and Reddit search were checked for Kwork-specific category ids, but no reliable technical list of Kwork project `category_id` values was found.

## Runtime selection model

The bot discovers category ids during runtime and stores them locally. The Telegram button `📂 Категории` refreshes the catalog from Kwork API data and shows inline toggle buttons for choosing categories.

Selected ids are stored in `selected_category_ids.json`. The discovered catalog is stored in `category_catalog.json`.

The `.env` category options are only a fallback before the user makes a selection in the bot.

Active categories are resolved in this order:

1. If `selected_category_ids.json` contains ids, use them.
2. Otherwise `CATEGORY_IDS` fully replaces any preset when it is not empty.
3. Otherwise `CATEGORY_PROFILE` selects a preset.
4. `CATEGORY_EXTRA_IDS` adds ids to the fallback set.
5. `CATEGORY_EXCLUDE_IDS` removes ids from the fallback set.

Available presets:

- `automation` - scripts, parsers, bots, Telegram Mini Apps, AI bots.
- `parsers` - parser orders only.
- `bots` - chatbots, Telegram Mini Apps, AI bots.
- `scripts` - scripts and Telegram Mini Apps.

Use `CATEGORY_EXTRA_IDS` only as a startup fallback. Normal category selection should be done from the Telegram UI.
