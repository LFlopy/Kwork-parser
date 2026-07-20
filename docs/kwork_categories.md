# Подбор категорий Kwork

## Проверенные источники

- Официальный каталог Kwork: https://kwork.ru/categories
- Английский каталог Kwork: https://kwork.com/categories
- Неофициальная библиотека Kwork API на GitHub: https://github.com/CrazyMan-IK/kwork-api
- Пример методов `getProjects()` и `getFavouriteCategories()`: https://github.com/CrazyMan-IK/kwork-api/blob/main/examples/api_example.js
- Habr Q&A и Reddit были проверены на наличие готового списка `category_id`, но надёжного технического справочника по id категорий Kwork там не нашлось.

## Как бот выбирает категории

Бот получает категории во время работы и сохраняет их локально. Кнопка `📂 Категории` обновляет каталог через Kwork API и показывает inline-кнопки для включения или отключения категорий.

Выбранные id хранятся в `selected_category_ids.json`. Найденный каталог хранится в `category_catalog.json`.

Переменные `.env`, связанные с категориями, используются только как fallback до первого выбора в Telegram.

Порядок выбора активных категорий:

1. Если в `selected_category_ids.json` есть id, используются они.
2. Иначе, если задан `CATEGORY_IDS`, он полностью заменяет профиль.
3. Иначе используется профиль из `CATEGORY_PROFILE`.
4. `CATEGORY_EXTRA_IDS` добавляет id к fallback-набору.
5. `CATEGORY_EXCLUDE_IDS` удаляет id из fallback-набора.

Доступные fallback-профили:

- `automation` - скрипты, парсеры, боты, Telegram Mini Apps и ИИ-боты.
- `parsers` - только парсеры.
- `bots` - чат-боты, Telegram Mini Apps и ИИ-боты.
- `scripts` - скрипты и mini apps.
