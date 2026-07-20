import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.categories import Category, CATEGORY_CATALOG

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_FILE = Path(os.getenv("CATEGORY_CATALOG_FILE", _PROJECT_ROOT / "category_catalog.json"))
_SELECTED_FILE = Path(os.getenv("SELECTED_CATEGORY_IDS_FILE", _PROJECT_ROOT / "selected_category_ids.json"))


def load_catalog() -> dict[int, Category]:
    """Загрузить найденные категории Kwork."""

    if not _CATALOG_FILE.exists():
        return dict(CATEGORY_CATALOG)

    try:
        data = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.error("Category catalog file %s must contain a JSON list", _CATALOG_FILE)
            return dict(CATEGORY_CATALOG)
        return {
            int(item["id"]): Category(
                id=int(item["id"]),
                name=str(item.get("name") or item["id"]),
                group=str(item.get("group") or "Kwork"),
                aliases=tuple(str(alias) for alias in item.get("aliases", ())),
            )
            for item in data
            if isinstance(item, dict) and "id" in item
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        logger.exception("Could not read category catalog from %s", _CATALOG_FILE)
        return dict(CATEGORY_CATALOG)


def save_catalog(categories: dict[int, Category]) -> None:
    """Сохранить найденные категории Kwork."""

    payload = [
        {
            "id": category.id,
            "name": category.name,
            "group": category.group,
            "aliases": list(category.aliases),
        }
        for category in sorted(categories.values(), key=lambda item: (item.group, item.name, item.id))
    ]
    _write_json(_CATALOG_FILE, payload)


def load_selected_category_ids() -> set[int]:
    """Загрузить id категорий, выбранные пользователем бота."""

    if not _SELECTED_FILE.exists():
        return set()

    try:
        data = json.loads(_SELECTED_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.error("Selected category ids file %s must contain a JSON list", _SELECTED_FILE)
            return set()
        return {int(item) for item in data}
    except (TypeError, ValueError, json.JSONDecodeError, OSError):
        logger.exception("Could not read selected category ids from %s", _SELECTED_FILE)
        return set()


def save_selected_category_ids(category_ids: set[int]) -> None:
    """Сохранить id категорий, выбранные пользователем бота."""

    _write_json(_SELECTED_FILE, sorted(category_ids))


def toggle_selected_category(category_id: int) -> bool:
    """Переключить категорию и вернуть, включена ли она после переключения."""

    selected = load_selected_category_ids()
    if category_id in selected:
        selected.remove(category_id)
        save_selected_category_ids(selected)
        return False

    selected.add(category_id)
    save_selected_category_ids(selected)
    return True


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
