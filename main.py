import asyncio
import html
import logging
from collections.abc import Callable

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from src.categories import category_profile_title
from src.category_storage import (
    load_catalog,
    load_selected_category_ids,
    save_catalog,
    save_selected_category_ids,
    toggle_selected_category,
)
from src.config import Settings
from src.kwork_sdk import KworkSDKAdapter, KworkSDKConfig, KworkSDKUnavailable
from src.notifier import publish_order_ids
from src.scraper import CATEGORY_IDS, discover_categories, fetch_page_result, get_token_result, is_recent
from src.storage import load as load_seen, locked_seen_ids, save as save_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("pykwork").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

OrderPredicate = Callable[[dict, set[str]], bool]

HTTP_TIMEOUT_SECONDS = 30
PAGE_REQUEST_PAUSE_SECONDS = 1
TELEGRAM_MESSAGE_LIMIT = 4000
FIRST_PAGE = 1
CATEGORY_PAGE_SIZE = 8

BTN_CHECK_NOW = "🔍 Проверить сейчас"
BTN_STATUS = "📊 Статус"
BTN_LAST_24H = "📅 Заказы за 24 часа"
BTN_CATEGORIES = "📂 Категории"
BTN_DEBUG = "🔬 Диагностика"

settings = Settings()
bot: Bot | None = None
dp = Dispatcher()
_poll_lock = asyncio.Lock()
_active_category_ids: set[int] | None = None
_category_catalog = load_catalog()

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_CHECK_NOW), KeyboardButton(text=BTN_STATUS)],
        [KeyboardButton(text=BTN_LAST_24H), KeyboardButton(text=BTN_CATEGORIES)],
        [KeyboardButton(text=BTN_DEBUG)],
    ],
    resize_keyboard=True,
)


def is_admin(message: Message) -> bool:
    """Проверить, отправлено ли входящее сообщение администратором."""

    return message.from_user is not None and is_admin_id(message.from_user.id)


def is_admin_id(user_id: int) -> bool:
    """Проверить, относится ли Telegram user id к настроенным администраторам."""

    return user_id in settings.admin_ids


def configure_runtime(app_settings: Settings | None = None) -> None:
    """Настроить валидированные параметры, Telegram-бота и активные категории."""

    global bot, settings, _active_category_ids

    settings = app_settings or settings
    settings.validate()
    selected_category_ids = load_selected_category_ids()
    _active_category_ids = selected_category_ids or settings.active_category_ids()
    bot = Bot(token=settings.bot_token)


def active_categories() -> set[int]:
    """Вернуть id категорий, которые использует текущий процесс бота."""

    selected_category_ids = load_selected_category_ids()
    if selected_category_ids:
        return selected_category_ids
    return set(_active_category_ids or CATEGORY_IDS)


def refresh_active_categories() -> None:
    """Обновить активные категории из хранилища выбора пользователя."""

    global _active_category_ids

    selected_category_ids = load_selected_category_ids()
    _active_category_ids = selected_category_ids or settings.active_category_ids()


def get_bot() -> Bot:
    """Вернуть настроенный экземпляр Telegram-бота."""

    if bot is None:
        configure_runtime()
    if bot is None:
        raise RuntimeError("Telegram-бот не настроен")
    return bot


async def _get_kwork_token(session: aiohttp.ClientSession, log_context: str) -> str | None:
    result = await get_token_result(session, settings.kwork_login, settings.kwork_password, settings.kwork_phone)
    if not result.ok:
        logger.error("Could not obtain Kwork API token, skipping %s: %s", log_context, result.error)
    return result.token


async def refresh_category_catalog() -> tuple[int, str | None]:
    """Загрузить категории Kwork из API и сохранить их локально."""

    global _category_catalog

    sdk_result = await _refresh_category_catalog_with_sdk()
    if sdk_result is not None:
        return sdk_result

    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        token = await _get_kwork_token(session, "category discovery")
        if not token:
            return len(_category_catalog), "Не удалось получить токен Kwork API."

        result = await discover_categories(session, token=token)
        if result.categories:
            _category_catalog = result.categories
            save_catalog(_category_catalog)
        return len(_category_catalog), result.error


async def _refresh_category_catalog_with_sdk() -> tuple[int, str | None] | None:
    global _category_catalog

    try:
        async with KworkSDKAdapter(_kwork_sdk_config()) as client:
            categories = await client.get_categories()
    except KworkSDKUnavailable:
        return None
    except Exception as exc:
        logger.warning("Kwork SDK category discovery failed, falling back to legacy API: %s", exc)
        return None

    if categories:
        _category_catalog = categories
        save_catalog(_category_catalog)
    return len(_category_catalog), None


def _kwork_sdk_config() -> KworkSDKConfig:
    return KworkSDKConfig(
        login=settings.kwork_login,
        password=settings.kwork_password,
        phone=settings.kwork_phone,
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def category_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    """Собрать inline-клавиатуру для выбора категорий."""

    categories = sorted(_category_catalog.values(), key=lambda item: (item.group, item.name, item.id))
    selected = load_selected_category_ids()
    pages = max(1, (len(categories) + CATEGORY_PAGE_SIZE - 1) // CATEGORY_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * CATEGORY_PAGE_SIZE
    page_categories = categories[start : start + CATEGORY_PAGE_SIZE]

    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if category.id in selected else '☐'} {category.id} · {category.name}",
                callback_data=f"cat:toggle:{category.id}:{page}",
            )
        ]
        for category in page_categories
    ]

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="←", callback_data=f"cat:page:{page - 1}"))
    navigation.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=f"cat:page:{page}"))
    if page < pages - 1:
        navigation.append(InlineKeyboardButton(text="→", callback_data=f"cat:page:{page + 1}"))
    rows.append(navigation)
    rows.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data=f"cat:refresh:{page}")])
    rows.append([InlineKeyboardButton(text="Сбросить выбор", callback_data=f"cat:reset:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_selection_text() -> str:
    """Собрать текст со сводкой выбора категорий."""

    selected = load_selected_category_ids()
    active = sorted(active_categories())
    mode = "выбор пользователя" if selected else "профиль по умолчанию"
    return (
        "<b>Категории заказов</b>\n\n"
        f"Режим: {html.escape(mode, quote=False)}\n"
        f"Активные category_id: {active}\n\n"
        "Нажмите категорию, чтобы включить или выключить её."
    )


async def _collect_unseen_recent_orders(
    *,
    log_context: str,
    include_order: OrderPredicate,
) -> tuple[list[dict], set[str]]:
    seen = load_seen()
    fresh: list[dict] = []
    page = FIRST_PAGE
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        token = await _get_kwork_token(session, log_context)
        if not token:
            return [], seen

        while True:
            result = await fetch_page_result(session, page, token=token, category_ids=active_categories())
            if not result.ok:
                logger.error("Could not fetch Kwork page %s: %s", page, result.error)
                break

            projects = result.projects
            last_page = result.last_page
            fresh.extend(project for project in projects if include_order(project, seen))

            has_recent_projects = any(is_recent(project) for project in projects)
            if page >= last_page or not has_recent_projects:
                break

            page += 1
            await asyncio.sleep(PAGE_REQUEST_PAUSE_SECONDS)

    return fresh, seen


async def _collect_unseen_recent_orders_with_sdk(
    *,
    include_order: OrderPredicate,
) -> tuple[list[dict], set[str]] | None:
    seen = load_seen()
    fresh: list[dict] = []
    page = FIRST_PAGE

    try:
        async with KworkSDKAdapter(_kwork_sdk_config()) as client:
            while True:
                projects, last_page = await client.get_projects(page=page, category_ids=active_categories())
                fresh.extend(project for project in projects if include_order(project, seen))

                has_recent_projects = any(is_recent(project) for project in projects)
                if page >= last_page or not has_recent_projects:
                    break

                page += 1
                await asyncio.sleep(PAGE_REQUEST_PAUSE_SECONDS)
    except KworkSDKUnavailable:
        return None
    except Exception:
        logger.exception("Kwork SDK project scan failed")
        return None

    return fresh, seen


async def _publish_and_remember(orders: list[dict], seen: set[str]) -> int:
    if not orders:
        return 0

    sent_ids = await publish_order_ids(get_bot(), settings.channel_id, orders)
    if sent_ids:
        seen.update(sent_ids)
        save_seen(seen)
    return len(sent_ids)


async def poll_new_orders() -> int:
    """Загрузить и опубликовать новые актуальные заказы Kwork."""

    async with _poll_lock:
        with locked_seen_ids():
            include_order = lambda project, seen_ids: str(project.get("id")) not in seen_ids and is_recent(project)
            result = await _collect_unseen_recent_orders_with_sdk(include_order=include_order)
            if result is None:
                result = await _collect_unseen_recent_orders(log_context="poll", include_order=include_order)
            orders, seen = result
            return await _publish_and_remember(orders, seen)


async def collect_last_24h() -> int:
    """Загрузить и опубликовать новые заказы Kwork за последние 24 часа."""

    async with _poll_lock:
        with locked_seen_ids():
            include_order = lambda project, seen_ids: is_recent(project) and str(project.get("id")) not in seen_ids
            result = await _collect_unseen_recent_orders_with_sdk(include_order=include_order)
            if result is None:
                result = await _collect_unseen_recent_orders(log_context="24h scan", include_order=include_order)
            orders, seen = result
            return await _publish_and_remember(orders, seen)


async def polling_loop() -> None:
    """Постоянно выполнять фоновую проверку заказов."""

    logger.info("Polling loop started, interval %ss", settings.poll_interval)
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
    """Обработать команду Telegram /start."""

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


@dp.message(lambda m: m.text == BTN_STATUS)
async def btn_status(message: Message) -> None:
    """Обработать кнопку статуса."""

    if not is_admin(message):
        return
    seen = load_seen()
    await message.answer(
        f"<b>Статус</b>\n\n"
        f"Отслежено заказов: {len(seen)}\n"
        f"Профиль категорий: {html.escape(category_profile_title(settings.category_profile), quote=False)}\n"
        f"Активные category_id: {sorted(active_categories())}\n"
        f"Интервал: {settings.poll_interval} сек.\n"
        f"Канал: {settings.channel_id}",
        parse_mode="HTML",
    )


@dp.message(lambda m: m.text == BTN_CHECK_NOW)
async def btn_check(message: Message) -> None:
    """Обработать кнопку ручной проверки."""

    if not is_admin(message):
        return
    msg = await message.answer("Проверяю…")
    count = await poll_new_orders()
    await msg.edit_text(f"Новых заказов: {count}" if count else "Новых заказов нет.")


@dp.message(lambda m: m.text == BTN_LAST_24H)
async def btn_last_24h(message: Message) -> None:
    """Обработать кнопку сканирования за последние 24 часа."""

    if not is_admin(message):
        return
    msg = await message.answer("Ищу заказы за последние 24 ч…")
    count = await collect_last_24h()
    await msg.edit_text(f"Найдено за 24 ч: {count}" if count else "Новых за 24 ч нет.")


@dp.message(lambda m: m.text == BTN_CATEGORIES)
async def btn_categories(message: Message) -> None:
    """Обработать кнопку выбора категорий."""

    if not is_admin(message):
        return
    msg = await message.answer("Обновляю список категорий Kwork…")
    await refresh_category_catalog()
    await msg.edit_text(
        category_selection_text(),
        reply_markup=category_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(lambda c: c.data is not None and c.data.startswith("cat:"))
async def category_callback(callback: CallbackQuery) -> None:
    """Обработать callback-и выбора категорий."""

    if callback.message is None:
        await callback.answer()
        return
    if not is_admin_id(callback.from_user.id):
        await callback.answer()
        return

    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    page = int(parts[-1]) if parts[-1].isdigit() else 0

    if action == "toggle" and len(parts) >= 4:
        try:
            category_id = int(parts[2])
        except ValueError:
            await callback.answer("Некорректная категория")
            return
        enabled = toggle_selected_category(category_id)
        refresh_active_categories()
        await callback.answer("Категория включена" if enabled else "Категория выключена")
    elif action == "reset":
        save_selected_category_ids(set())
        refresh_active_categories()
        await callback.answer("Выбор сброшен")
    elif action == "refresh":
        count, error = await refresh_category_catalog()
        await callback.answer(f"Найдено категорий: {count}" if not error else error[:200])
    else:
        await callback.answer()

    await callback.message.edit_text(
        category_selection_text(),
        reply_markup=category_keyboard(page),
        parse_mode="HTML",
    )


@dp.message(lambda m: m.text == BTN_DEBUG)
async def btn_debug(message: Message) -> None:
    """Обработать кнопку диагностики API."""

    if not is_admin(message):
        return
    msg = await message.answer("Проверяю API…")
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            auth = await get_token_result(
                session,
                settings.kwork_login,
                settings.kwork_password,
                settings.kwork_phone,
            )
            if not auth.ok:
                await msg.edit_text(
                    "❌ Не удалось получить токен Kwork API.\n"
                    "Проверьте KWORK_LOGIN / KWORK_PASSWORD / KWORK_PHONE в .env"
                )
                return

            result = await fetch_page_result(session, FIRST_PAGE, token=auth.token or "", category_ids=active_categories())
            if not result.ok:
                await msg.edit_text(f"Ошибка запроса: {result.error}")
                return
            projects = result.projects
            last_page = result.last_page
    except Exception as exc:
        await msg.edit_text(f"Ошибка запроса: {exc}")
        return

    lines = [
        f"<b>Диагностика (стр. 1 из {last_page})</b>",
        f"Проектов получено: {len(projects)}",
    ]

    if projects:
        lines += ["", "<b>Первые 5:</b>"]
        for project in projects[:5]:
            category_id = html.escape(str(project.get("category_id")), quote=False)
            title = html.escape(str(project.get("title", "?"))[:55], quote=False)
            date_confirm = html.escape(str(project.get("date_confirm", "—")), quote=False)
            lines.append(
                f"• [{category_id}] {title}\n"
                f"  date_confirm={date_confirm}"
            )
    else:
        lines.append("⚠️ Проекты не получены.")

    text = "\n".join(lines)
    await msg.delete()
    for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        await message.answer(text[i : i + TELEGRAM_MESSAGE_LIMIT], parse_mode="HTML")


async def main() -> None:
    """Запустить фоновый мониторинг и polling обновлений Telegram."""

    configure_runtime()
    asyncio.create_task(polling_loop())
    await dp.start_polling(get_bot(), allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
