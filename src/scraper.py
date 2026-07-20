import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import Any

import aiohttp

from src.categories import Category, CATEGORY_CATALOG, resolve_category_ids

logger = logging.getLogger(__name__)

KWORK_API = "https://api.kwork.ru"
KWORK_BASE = "https://kwork.ru"
SIGN_IN_PATH = "/signIn"
PROJECTS_PATH = "/projects"
FAVORITE_CATEGORIES_PATH = "/favoriteCategories"

DEFAULT_LAST_PAGE = 1
RECENT_HOURS = 24
PHONE_CONFIRMATION_ERROR_CODE = "192"
LOG_RESPONSE_PREVIEW_CHARS = 400
API_RETRY_ATTEMPTS = 2
API_RETRY_DELAY_SECONDS = 1
FIRST_DISCOVERY_PAGE = 1
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
DEFAULT_KWORK_MOBILE_AUTH = "Basic bW9iaWxlX2FwaTpxRnZmUmw3dw=="

CATEGORY_NAMES: dict[int, str] = {category_id: category.name for category_id, category in CATEGORY_CATALOG.items()}
CATEGORY_IDS: set[int] = resolve_category_ids(
    os.getenv("CATEGORY_PROFILE", "automation"),
    category_ids=os.getenv("CATEGORY_IDS", ""),
    extra_ids=os.getenv("CATEGORY_EXTRA_IDS", ""),
    exclude_ids=os.getenv("CATEGORY_EXCLUDE_IDS", ""),
)

HEADERS: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class PageFetchResult:
    """Ответ страницы заказов Kwork с контекстом ошибки."""

    projects: list[dict]
    last_page: int = DEFAULT_LAST_PAGE
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Проверить, успешно ли загружена страница."""

        return self.error is None


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Ответ авторизации Kwork с контекстом ошибки."""

    token: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Проверить, успешна ли авторизация."""

        return self.token is not None and self.error is None


@dataclass(frozen=True, slots=True)
class CategoryDiscoveryResult:
    """Найденные категории Kwork с контекстом ошибки."""

    categories: dict[int, Category]
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Проверить, успешно ли найдены категории."""

        return self.error is None


def _auth_headers() -> dict[str, str]:
    return {"Authorization": os.getenv("KWORK_MOBILE_AUTH") or DEFAULT_KWORK_MOBILE_AUTH}


def _is_retryable_status(status: int) -> bool:
    return status in RETRYABLE_HTTP_STATUSES


async def _post_api(
    session: aiohttp.ClientSession,
    path: str,
    *,
    params: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            async with session.post(
                f"{KWORK_API}{path}",
                params=params,
                headers=_auth_headers(),
            ) as resp:
                if resp.status != 200:
                    error = f"API HTTP {resp.status} on {path}"
                    logger.warning(error)
                    if _is_retryable_status(resp.status) and attempt < API_RETRY_ATTEMPTS:
                        await asyncio.sleep(API_RETRY_DELAY_SECONDS)
                        continue
                    return None, error
                return await resp.json(content_type=None), None
        except Exception as exc:
            if attempt >= API_RETRY_ATTEMPTS:
                logger.exception("Error calling %s", path)
                return None, str(exc)
            await asyncio.sleep(API_RETRY_DELAY_SECONDS)
    return None, f"empty API response on {path}"


async def get_token(
    session: aiohttp.ClientSession,
    login: str,
    password: str,
    phone: str,
) -> str | None:
    """Авторизоваться в api.kwork.ru и вернуть session token."""
    result = await get_token_result(session, login, password, phone)
    return result.token


async def get_token_result(
    session: aiohttp.ClientSession,
    login: str,
    password: str,
    phone: str,
) -> AuthResult:
    """Авторизоваться в api.kwork.ru с явным контекстом ошибки."""

    headers = _auth_headers()

    async def _post_sign_in(extra: dict[str, str]) -> dict[str, Any] | None:
        for attempt in range(1, API_RETRY_ATTEMPTS + 1):
            try:
                async with session.post(
                    f"{KWORK_API}{SIGN_IN_PATH}",
                    data={"login": login, "password": password, **extra},
                    headers=headers,
                ) as resp:
                    raw = await resp.text()
                    logger.debug("signIn [HTTP %s]: %r", resp.status, raw[:LOG_RESPONSE_PREVIEW_CHARS])
                    if _is_retryable_status(resp.status) and attempt < API_RETRY_ATTEMPTS:
                        await asyncio.sleep(API_RETRY_DELAY_SECONDS)
                        continue
                    if not raw.strip():
                        logger.warning("signIn returned empty response [HTTP %s]", resp.status)
                        return None
                    try:
                        return json.loads(raw)
                    except JSONDecodeError:
                        logger.error(
                            "signIn returned non-JSON response [HTTP %s, content-type=%s]: %r",
                            resp.status,
                            resp.headers.get("content-type", ""),
                            raw[:LOG_RESPONSE_PREVIEW_CHARS],
                        )
                        return None
            except Exception:
                if attempt >= API_RETRY_ATTEMPTS:
                    logger.exception("Error calling %s", SIGN_IN_PATH)
                    return None
                await asyncio.sleep(API_RETRY_DELAY_SECONDS)
        return None

    body = await _post_sign_in({})
    if body is None:
        return AuthResult(error="empty or invalid signIn response")

    if not body.get("success") and str(body.get("error_code", "")) == PHONE_CONFIRMATION_ERROR_CODE:
        logger.info("Phone confirmation required, retrying with phone_last")
        body = await _post_sign_in({"phone_last": phone})
        if body is None:
            return AuthResult(error="empty or invalid phone confirmation response")

    if body.get("success"):
        token = (body.get("response") or {}).get("token")
        if token:
            logger.info("Kwork API token obtained")
            return AuthResult(token=token)

    error_code = body.get("error_code")
    error_message = body.get("error")
    logger.warning(
        "Auth failed: error_code=%s message=%s",
        error_code,
        error_message,
    )
    return AuthResult(error=f"auth failed: error_code={error_code} message={error_message}")


def _parse_date(project: dict) -> datetime | None:
    for field in ("date_confirm", "date_create", "created_at"):
        value = project.get(field)
        if value:
            try:
                return datetime.fromtimestamp(int(value), tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                logger.debug("Could not parse project date field %s=%r", field, value)
    return None


def is_recent(project: dict, hours: int = RECENT_HOURS) -> bool:
    """Проверить, попадает ли заказ Kwork в актуальное окно мониторинга."""

    dt = _parse_date(project)
    return dt is None or dt >= datetime.now(timezone.utc) - timedelta(hours=hours)


async def _warm_session(session: aiohttp.ClientSession) -> None:
    return None


async def fetch_page(
    session: aiohttp.ClientSession,
    page: int,
    *,
    token: str = "",
    category_ids: set[int] | None = None,
) -> tuple[list[dict], int]:
    """Загрузить одну страницу заказов из приватного API Kwork."""
    result = await fetch_page_result(session, page, token=token, category_ids=category_ids)
    return result.projects, result.last_page


async def fetch_page_result(
    session: aiohttp.ClientSession,
    page: int,
    *,
    token: str = "",
    category_ids: set[int] | None = None,
) -> PageFetchResult:
    """Загрузить одну страницу заказов с явным контекстом ошибки."""

    try:
        active_category_ids = category_ids if category_ids is not None else CATEGORY_IDS
        params: dict[str, Any] = {"token": token, "page": page}
        if active_category_ids:
            params["categories"] = ",".join(str(category_id) for category_id in sorted(active_category_ids))

        body, error = await _post_api(
            session,
            PROJECTS_PATH,
            params=params,
        )
        if body is None:
            return PageFetchResult(projects=[], error=error or f"Empty API response on page {page}")

        all_projects: list[dict] = body.get("response") or []
        paging = body.get("paging") or {}
        last_page = int(paging.get("pages", DEFAULT_LAST_PAGE))

        relevant = [
            project
            for project in all_projects
            if not active_category_ids or _is_relevant_project(project, category_ids=active_category_ids)
        ]
        logger.debug(
            "page %s/%s: %s total -> %s relevant",
            page,
            last_page,
            len(all_projects),
            len(relevant),
        )
        return PageFetchResult(projects=relevant, last_page=last_page)

    except Exception as exc:
        logger.exception("Error fetching page %s", page)
        return PageFetchResult(projects=[], error=str(exc))


def _is_relevant_project(project: dict, *, category_ids: set[int] | None = None) -> bool:
    active_category_ids = category_ids if category_ids is not None else CATEGORY_IDS
    try:
        return int(project.get("category_id", 0)) in active_category_ids
    except (TypeError, ValueError):
        logger.debug("Project has invalid category_id: %r", project.get("category_id"))
        return False


async def discover_categories(
    session: aiohttp.ClientSession,
    *,
    token: str,
) -> CategoryDiscoveryResult:
    """Найти категории Kwork, доступные текущему аккаунту."""

    categories = dict(CATEGORY_CATALOG)
    favorites, favorites_error = await _post_api(
        session,
        FAVORITE_CATEGORIES_PATH,
        params={"token": token},
    )
    if favorites is not None:
        categories.update(_extract_categories_from_favorites(favorites))

    page = FIRST_DISCOVERY_PAGE
    while True:
        result = await fetch_page_result(session, page, token=token, category_ids=set())
        if not result.ok:
            return CategoryDiscoveryResult(categories=categories, error=result.error or favorites_error)

        categories.update(_extract_categories_from_projects(result.projects))
        if page >= result.last_page:
            break
        page += 1
        await asyncio.sleep(API_RETRY_DELAY_SECONDS)

    return CategoryDiscoveryResult(categories=categories, error=favorites_error)


def _extract_categories_from_favorites(body: dict[str, Any]) -> dict[int, Category]:
    response = body.get("response") or []
    if isinstance(response, dict):
        response = response.values()

    categories: dict[int, Category] = {}
    for item in response:
        if isinstance(item, dict):
            category = _category_from_mapping(item, default_group="Избранные рубрики")
            if category is not None:
                categories[category.id] = category
    return categories


def _extract_categories_from_projects(projects: list[dict]) -> dict[int, Category]:
    categories: dict[int, Category] = {}
    for project in projects:
        category = _project_category(project)
        if category is not None:
            categories[category.id] = category
    return categories


def _project_category(project: dict) -> Category | None:
    category = _category_from_mapping(project, default_group="Категории заказов")
    if category is not None:
        return category

    parent_id = _to_int(project.get("parent_category_id"))
    if parent_id is not None:
        return Category(parent_id, f"Категория {parent_id}", "Категории заказов")
    return None


def _category_from_mapping(data: dict, *, default_group: str) -> Category | None:
    category_id = _to_int(data.get("category_id", data.get("id")))
    if category_id is None:
        return None

    name = (
        data.get("category_name")
        or data.get("name")
        or data.get("title")
        or f"Категория {category_id}"
    )
    group = data.get("parent_category_name") or data.get("group") or default_group
    return Category(category_id, str(name), str(group))


def _to_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def category_stats(html: str) -> str:
    """Вернуть legacy-текст диагностики категорий."""

    return "Диагностика: бот использует API вместо HTML-парсинга."
