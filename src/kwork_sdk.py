import inspect
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from src.categories import Category, CATEGORY_CATALOG

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KworkSDKConfig:
    """Учётные данные и настройки для опционального адаптера Kwork SDK."""

    login: str
    password: str
    phone: str = ""
    timeout: int = 30


class KworkSDKUnavailable(RuntimeError):
    """Ошибка, когда не установлен поддерживаемый пакет Kwork SDK."""


class KworkSDKAdapter:
    """Адаптер над опциональными пакетами Kwork SDK."""

    def __init__(self, config: KworkSDKConfig) -> None:
        self._config = config
        self._client: Any = None

    async def __aenter__(self) -> "KworkSDKAdapter":
        client_cls = _load_client_class()
        self._client = _build_client(client_cls, self._config)

        enter = getattr(self._client, "__aenter__", None)
        if enter is not None:
            entered = await _maybe_await(enter())
            if entered is not None:
                self._client = entered
        await _disable_broken_env_proxy_for_pykwork(self._client, self._config)

        login = getattr(self._client, "login", None)
        if login is not None:
            await _maybe_await(login())

        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._client is None:
            return

        exit_ = getattr(self._client, "__aexit__", None)
        if exit_ is not None:
            await _maybe_await(exit_(exc_type, exc, tb))
            return

        close = getattr(self._client, "close", None) or getattr(self._client, "aclose", None)
        if close is not None:
            await _maybe_await(close())

    async def get_projects(self, *, page: int, category_ids: set[int]) -> tuple[list[dict], int]:
        """Вернуть одну страницу заказов Kwork."""

        client = self._require_client()
        categories = ",".join(str(category_id) for category_id in sorted(category_ids))

        if hasattr(client, "get_projects"):
            data = await _call_with_supported_kwargs(
                client.get_projects,
                page=page,
                categories=categories,
            )
        elif hasattr(client, "request"):
            data = await client.request("post", "projects", use_token=True, page=page, categories=categories)
        else:
            raise KworkSDKUnavailable("Installed Kwork SDK does not expose get_projects/request")

        payload = _to_mapping(data)
        projects = _extract_projects(payload)
        last_page = _extract_last_page(payload)
        if last_page == 1 and projects:
            last_page = page + 1
        return projects, last_page

    async def get_categories(self) -> dict[int, Category]:
        """Вернуть категории из Kwork SDK."""

        client = self._require_client()
        if not hasattr(client, "get_categories"):
            raise KworkSDKUnavailable("Installed Kwork SDK does not expose get_categories")

        data = await _maybe_await(client.get_categories())
        return _extract_categories(data)

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Kwork SDK adapter is not opened")
        return self._client


def is_sdk_available() -> bool:
    """Проверить, можно ли импортировать поддерживаемый пакет Kwork SDK."""

    try:
        _load_client_class()
    except KworkSDKUnavailable:
        return False
    return True


def _load_client_class() -> Any:
    with suppress(ImportError):
        from kwork import Kwork

        return Kwork

    try:
        from pykwork import KworkClient

        return KworkClient
    except ImportError as exc:
        raise KworkSDKUnavailable("Install kwork or pykwork to use SDK-backed Kwork API") from exc


def _build_client(client_cls: Any, config: KworkSDKConfig) -> Any:
    signature = inspect.signature(client_cls)
    kwargs: dict[str, Any] = {}
    parameters = signature.parameters

    for name in ("username", "login", "email"):
        if name in parameters:
            kwargs[name] = config.login
            break
    if "password" in parameters:
        kwargs["password"] = config.password
    if "phone" in parameters:
        kwargs["phone"] = config.phone
    if "timeout" in parameters:
        kwargs["timeout"] = config.timeout

    if kwargs:
        return client_cls(**kwargs)
    return client_cls(config.login, config.password)


async def _disable_broken_env_proxy_for_pykwork(client: Any, config: KworkSDKConfig) -> None:
    if not client.__class__.__module__.startswith("pykwork"):
        return
    if not hasattr(client, "_client"):
        return

    try:
        import httpx
    except ImportError:
        return

    existing_client = getattr(client, "_client", None)
    if existing_client is not None:
        await existing_client.aclose()
    client._client = httpx.AsyncClient(timeout=config.timeout, trust_env=False)


async def _call_with_supported_kwargs(method: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(method)
    supported = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return await _maybe_await(method(**supported))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {"response": _to_plain(value)}


def _to_plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _extract_projects(payload: dict[str, Any]) -> list[dict]:
    response = payload.get("response", payload)
    if isinstance(response, dict):
        for key in ("projects", "items", "data"):
            if isinstance(response.get(key), list):
                return [_to_mapping(item) for item in response[key]]
    if isinstance(response, list):
        return [_to_mapping(item) for item in response]
    return []


def _extract_last_page(payload: dict[str, Any]) -> int:
    paging = payload.get("paging")
    if isinstance(paging, dict):
        return int(paging.get("pages", 1))

    response = payload.get("response")
    if isinstance(response, dict):
        paging = response.get("paging")
        if isinstance(paging, dict):
            return int(paging.get("pages", 1))
    return 1


def _extract_categories(data: Any) -> dict[int, Category]:
    raw_categories = _flatten_categories(_to_plain(data))
    categories = dict(CATEGORY_CATALOG)

    for raw in raw_categories:
        if not isinstance(raw, dict):
            continue
        category_id = _to_int(raw.get("id", raw.get("category_id")))
        if category_id is None:
            continue
        name = str(raw.get("name") or raw.get("title") or f"Категория {category_id}")
        group = str(raw.get("group") or raw.get("parent_name") or raw.get("parent_title") or "Kwork")
        categories[category_id] = Category(category_id, name, group)

    return categories


def _flatten_categories(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items: list[dict[str, Any]] = [value]
        for key in ("response", "categories", "items", "children", "subcategories"):
            child = value.get(key)
            if child is not None:
                items.extend(_flatten_categories(child))
        return items
    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(_flatten_categories(item))
        return items
    return []


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
