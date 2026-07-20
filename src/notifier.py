import asyncio
import html
import logging
import re

from aiogram import Bot

logger = logging.getLogger(__name__)

MAX_DESC = 900
TELEGRAM_MESSAGE_PAUSE_SECONDS = 0.3

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = _BR.sub("\n", text)
    text = _TAG.sub("", text)
    return text.strip()


def _html_text(value: object) -> str:
    return html.escape(_clean(str(value)), quote=False)


def _order_id(order: dict) -> str | None:
    value = order.get("id")
    return str(value) if value is not None else None


def format_order(project: dict) -> str:
    """Сформировать HTML-сообщение Telegram для одного заказа Kwork."""

    pid = project.get("id", "")
    name = _html_text(project.get("title") or "Без названия")
    desc = _clean(str(project.get("description", "")))
    price = _html_text(project.get("price", "—"))
    price_limit = _html_text(project.get("possible_price_limit", "—"))

    if len(desc) > MAX_DESC:
        desc = desc[:MAX_DESC].rstrip() + "…"
    desc = html.escape(desc, quote=False)

    return (
        f"<b>{name}</b>\n\n"
        f"{desc}\n\n"
        f"Желаемый бюджет: {price} ₽\n"
        f"Допустимый бюджет: {price_limit} ₽\n\n"
        f"https://kwork.ru/projects/{pid}/view"
    )


async def publish_order_ids(bot: Bot, channel_id: str, orders: list[dict]) -> set[str]:
    """Опубликовать заказы и вернуть id успешно отправленных сообщений."""

    sent_ids: set[str] = set()
    for order in orders:
        try:
            await bot.send_message(channel_id, format_order(order), parse_mode="HTML")
            order_id = _order_id(order)
            if order_id is not None:
                sent_ids.add(order_id)
            await asyncio.sleep(TELEGRAM_MESSAGE_PAUSE_SECONDS)
        except Exception:
            logger.exception("Failed to send order %s", order.get("id"))
    return sent_ids


async def publish(bot: Bot, channel_id: str, orders: list[dict]) -> int:
    """Опубликовать заказы и вернуть количество успешно отправленных сообщений."""

    sent_ids = await publish_order_ids(bot, channel_id, orders)
    return len(sent_ids)
