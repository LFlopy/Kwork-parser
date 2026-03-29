import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

from src.config import Settings
from src.notifier import publish
from src.scraper import CATEGORY_IDS, fetch_page, get_token, is_recent
from src.storage import load as load_seen, save as save_seen

settings = Settings()
bot = Bot(token=settings.bot_token)
dp = Dispatcher()

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Проверить сейчас"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="📅 Заказы за 24 часа"), KeyboardButton(text="📂 Категории")],
        [KeyboardButton(text="🔬 Диагностика")],
    ],
    resize_keyboard=True,
)


def is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in settings.admin_id_list()



async def poll_new_orders() -> int:
    """Fetch pages newest-first, stop when a full page has no unseen recent orders."""
    seen = load_seen()
    fresh: list[dict] = []
    page = 1

    async with aiohttp.ClientSession() as session:
        token = await get_token(session, settings.kwork_login, settings.kwork_password, settings.kwork_phone)
        if not token:
            logger.error("Could not obtain Kwork API token — skipping poll")
            return 0
        while True:
            projects, last_page = await fetch_page(session, page, token=token)
            new_on_page = [p for p in projects if str(p.get("id")) not in seen and is_recent(p)]
            fresh.extend(new_on_page)

            # stop if no recent projects on this page at all
            if not any(is_recent(p) for p in projects) or page >= last_page:
                break
            page += 1
            await asyncio.sleep(1)

    if not fresh:
        return 0

    for p in fresh:
        seen.add(str(p["id"]))
    save_seen(seen)
    return await publish(bot, settings.channel_id, fresh)


async def collect_last_24h() -> int:
    """Scan all pages and send orders created in the last 24 h."""
    seen = load_seen()
    fresh: list[dict] = []
    page = 1

    async with aiohttp.ClientSession() as session:
        token = await get_token(session, settings.kwork_login, settings.kwork_password, settings.kwork_phone)
        if not token:
            logger.error("Could not obtain Kwork API token — skipping 24h scan")
            return 0
        while True:
            projects, last_page = await fetch_page(session, page, token=token)
            recent = [p for p in projects if is_recent(p) and str(p.get("id")) not in seen]
            fresh.extend(recent)

            if page >= last_page or not any(is_recent(p) for p in projects):
                break
            page += 1
            await asyncio.sleep(1)

    if not fresh:
        return 0

    for p in fresh:
        seen.add(str(p["id"]))
    save_seen(seen)
    return await publish(bot, settings.channel_id, fresh)


async def polling_loop() -> None:
    logger.info("Polling loop started — interval %ss", settings.poll_interval)
    while True:
        try:
            count = await poll_new_orders()
            if count:
                logger.info("Published %s new orders to channel", count)
        except Exception:
            logger.exception("Unexpected error in polling loop")
        await asyncio.sleep(settings.poll_interval)


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not is_admin(message):
        return
    await message.answer(
        "Бот запущен!\n\n"
        "Слежу за новыми заказами на Kwork:\n"
        "• Чат-боты\n"
        "• Скрипты, боты и mini-apps\n"
        "• Парсеры\n\n"
        f"Интервал: {settings.poll_interval} сек.",
        reply_markup=MAIN_KB,
    )


@dp.message(lambda m: m.text == "📊 Статус")
async def btn_status(message: Message) -> None:
    if not is_admin(message):
        return
    seen = load_seen()
    await message.answer(
        f"<b>Статус</b>\n\n"
        f"Отслежено заказов: {len(seen)}\n"
        f"Активные category_id: {sorted(CATEGORY_IDS)}\n"
        f"Интервал: {settings.poll_interval} сек.\n"
        f"Канал: {settings.channel_id}",
        parse_mode="HTML",
    )


@dp.message(lambda m: m.text == "🔍 Проверить сейчас")
async def btn_check(message: Message) -> None:
    if not is_admin(message):
        return
    msg = await message.answer("Проверяю…")
    count = await poll_new_orders()
    await msg.edit_text(f"Новых заказов: {count}" if count else "Новых заказов нет.")


@dp.message(lambda m: m.text == "📅 Заказы за 24 часа")
async def btn_last_24h(message: Message) -> None:
    if not is_admin(message):
        return
    msg = await message.answer("Ищу заказы за последние 24 ч…")
    count = await collect_last_24h()
    await msg.edit_text(f"Найдено за 24 ч: {count}" if count else "Новых за 24 ч нет.")


@dp.message(lambda m: m.text == "📂 Категории")
async def btn_categories(message: Message) -> None:
    if not is_admin(message):
        return
    await message.answer(
        "<b>Отслеживаемые категории:</b>\n\n"
        "• <code>41</code>       — Скрипты, боты и mini apps\n"
        "• <code>3587</code>    — Чат-боты\n"
        "• <code>211</code>     — Парсеры\n"
        "• <code>7352</code>    — Скрипты\n"
        "• <code>3934090</code> — Telegram Mini Apps\n"
        "• <code>4158112</code> — ИИ-боты\n\n"
        "Изменить: <code>CATEGORY_IDS</code> в src/scraper.py",
        parse_mode="HTML",
    )


@dp.message(lambda m: m.text == "🔬 Диагностика")
async def btn_debug(message: Message) -> None:
    if not is_admin(message):
        return
    msg = await message.answer("Проверяю API…")

    try:
        async with aiohttp.ClientSession() as session:
            token = await get_token(
                session,
                settings.kwork_login,
                settings.kwork_password,
                settings.kwork_phone,
            )
            if not token:
                await msg.edit_text("❌ Не удалось получить токен Kwork API.\nПроверьте KWORK_LOGIN / KWORK_PASSWORD / KWORK_PHONE в .env")
                return

            projects, last_page = await fetch_page(session, 1, token=token)
    except Exception as e:
        await msg.edit_text(f"Ошибка запроса: {e}")
        return

    lines = [
        f"<b>Диагностика (стр. 1 из {last_page})</b>",
        f"Проектов получено: {len(projects)}",
    ]

    if projects:
        lines += ["", "<b>Первые 5:</b>"]
        for p in projects[:5]:
            lines.append(
                f"• [{p.get('category_id')}] {str(p.get('title', '?'))[:55]}\n"
                f"  date_confirm={p.get('date_confirm', '—')}"
            )
    else:
        lines.append("⚠️ Проекты не получены.")

    text = "\n".join(lines)
    await msg.delete()
    for i in range(0, len(text), 4000):
        await message.answer(text[i:i + 4000], parse_mode="HTML")


async def main() -> None:
    asyncio.create_task(polling_loop())
    await dp.start_polling(bot, allowed_updates=["message"])


if __name__ == "__main__":
    asyncio.run(main())
