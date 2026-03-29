import json
import logging
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)

KWORK_API = "https://api.kwork.ru"

_MOBILE_AUTH = "Basic bW9iaWxlX2FwaTpxRnZmUmw3dw=="

CATEGORY_IDS: set[int] = {41, 3587, 211, 7352, 3934090, 4158112}

# kept for backward-compat with main.py imports
KWORK_BASE = "https://kwork.ru"
HEADERS: dict = {}


async def get_token(
    session: aiohttp.ClientSession,
    login: str,
    password: str,
    phone: str,
) -> str | None:
    """Authenticate against api.kwork.ru and return a session token."""
    headers = {"Authorization": _MOBILE_AUTH}

    async def _post_sign_in(extra: dict) -> dict | None:
        try:
            async with session.post(
                f"{KWORK_API}/signIn",
                data={"login": login, "password": password, **extra},
                headers=headers,
            ) as resp:
                raw = await resp.text()
                logger.debug("signIn [HTTP %s]: %r", resp.status, raw[:400])
                if not raw.strip():
                    return None
                return json.loads(raw)
        except Exception:
            logger.exception("Error calling /signIn")
            return None

    body = await _post_sign_in({})
    if body is None:
        return None

    if not body.get("success") and str(body.get("error_code", "")) == "192":
        logger.info("Phone confirmation required — retrying with phone_last")
        body = await _post_sign_in({"phone_last": phone})
        if body is None:
            return None

    if body.get("success"):
        token = (body.get("response") or {}).get("token")
        if token:
            logger.info("Kwork API token obtained")
            return token

    logger.warning("Auth failed: %s", body)
    return None


def _parse_date(project: dict) -> datetime | None:
    for field in ("date_confirm", "date_create", "created_at"):
        val = project.get(field)
        if val:
            try:
                return datetime.fromtimestamp(int(val))
            except (ValueError, OSError, OverflowError):
                pass
    return None


def is_recent(project: dict, hours: int = 24) -> bool:
    dt = _parse_date(project)
    return dt is None or dt >= datetime.now() - timedelta(hours=hours)


async def _warm_session(session: aiohttp.ClientSession) -> None:
    """No-op — kept so main.py import doesn't break."""
    pass


async def fetch_page(
    session: aiohttp.ClientSession,
    page: int,
    *,
    token: str = "",
) -> tuple[list[dict], int]:
    """Fetch one page of buyer orders from the private Kwork API."""
    try:
        async with session.post(
            f"{KWORK_API}/projects",
            params={"token": token, "page": page},
            headers={"Authorization": _MOBILE_AUTH},
        ) as resp:
            if resp.status != 200:
                logger.warning("API HTTP %s on page %s", resp.status, page)
                return [], 1
            body = await resp.json(content_type=None)

        all_projects: list[dict] = body.get("response") or []
        paging = body.get("paging") or {}
        last_page = int(paging.get("pages", 1))

        relevant = [p for p in all_projects if int(p.get("category_id", 0)) in CATEGORY_IDS]
        logger.debug("page %s/%s: %s total → %s relevant", page, last_page, len(all_projects), len(relevant))
        return relevant, last_page

    except Exception:
        logger.exception("Error fetching page %s", page)
        return [], 1


def category_stats(html: str) -> str:
    """Stub — kept for import compatibility."""
    return "Диагностика: бот использует API вместо HTML-парсинга."
