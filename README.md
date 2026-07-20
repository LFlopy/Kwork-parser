# Kwork Parser

Telegram-бот для мониторинга заказов на Kwork по выбранным категориям и публикации новых заказов в канал.

## Установка

1. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

   Бот использует Kwork SDK (`kwork.Kwork` или `pykwork.KworkClient`) для получения категорий и заказов. Если поддерживаемый SDK недоступен, бот откатывается на legacy HTTP-клиент.

2. Создайте `.env` на основе `.env.example` и заполните переменные:

   - `BOT_TOKEN` - токен Telegram-бота.
   - `CHANNEL_ID` - id канала, куда публиковать заказы.
   - `ADMIN_IDS` - Telegram user id администраторов через запятую.
   - `POLL_INTERVAL` - интервал проверки в секундах, по умолчанию `300`.
   - `KWORK_LOGIN`, `KWORK_PASSWORD`, `KWORK_PHONE` - данные аккаунта Kwork.
   - `KWORK_MOBILE_AUTH` - необязательная замена служебного Authorization header для мобильного API Kwork.
   - `CATEGORY_PROFILE` - fallback-профиль категорий до выбора категорий в боте.
   - `CATEGORY_IDS` - необязательный fallback-список id, полностью заменяющий профиль.
   - `CATEGORY_EXTRA_IDS` - необязательные fallback-id, добавляемые к профилю.
   - `CATEGORY_EXCLUDE_IDS` - необязательные fallback-id, исключаемые из итогового fallback-набора.

3. Запустите бота:

   ```bash
   python main.py
   ```

## Категории

Нажмите в боте кнопку `📂 Категории`, чтобы обновить каталог Kwork и выбрать категории заказов через inline-кнопки.

Состояние хранится локально:

- `seen_ids.json` - уже опубликованные заказы.
- `category_catalog.json` - найденные категории Kwork.
- `selected_category_ids.json` - категории, выбранные пользователем.

Путь к `seen_ids.json` можно переопределить через `SEEN_IDS_FILE`.
