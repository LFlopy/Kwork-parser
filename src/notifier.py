import asyncio
import logging
import re

from aiogram import Bot

logger = logging.getLogger(__name__)

MAX_DESC = 900

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    text = _BR.sub("\n", text)
    text = _TAG.sub("", text)
    return text.strip()


def format_order(project: dict) -> str:
    pid = project.get("id", "")
    name = _clean(project.get("title", "") or "Без названия")
    desc = _clean(str(project.get("description", "")))
    price = project.get("price", "—")
    price_limit = project.get("possible_price_limit", "—")

    if len(desc) > MAX_DESC:
        desc = desc[:MAX_DESC].rstrip() + "…"

    return (
        f"<b>{name}</b>\n\n"
        f"{desc}\n\n"
        f"Желаемый бюджет: {price} ₽\n"
        f"Допустимый бюджет: {price_limit} ₽\n\n"
        f"https://kwork.ru/projects/{pid}/view"
    )


async def publish(bot: Bot, channel_id: str, orders: list[dict]) -> int:
    sent = 0
    for order in orders:
        try:
            await bot.send_message(channel_id, format_order(order), parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.3)
        except Exception:
            logger.exception("Failed to send order %s", order.get("id"))
    return sent
