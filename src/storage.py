import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FILE = Path(os.getenv("SEEN_IDS_FILE", _PROJECT_ROOT / "seen_ids.json"))
_LOCK_FILE = _FILE.with_suffix(f"{_FILE.suffix}.lock")
DEFAULT_LOCK_TIMEOUT_SECONDS = 30
LOCK_RETRY_DELAY_SECONDS = 0.1


class SeenIdsLockTimeout(TimeoutError):
    """Ошибка при невозможности получить lock хранилища опубликованных заказов."""


@contextmanager
def locked_seen_ids(timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """Получить межпроцессный lock для операций чтения-изменения-записи seen ids."""

    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise SeenIdsLockTimeout(f"Could not acquire seen ids lock: {_LOCK_FILE}") from exc
            time.sleep(LOCK_RETRY_DELAY_SECONDS)

    try:
        yield
    finally:
        os.close(fd)
        with suppress(FileNotFoundError):
            _LOCK_FILE.unlink()


def load() -> set[str]:
    """Загрузить id заказов, которые уже были опубликованы."""

    if not _FILE.exists():
        return set()

    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.error("Seen ids file %s must contain a JSON list", _FILE)
            return set()
        return {str(item) for item in data}
    except (json.JSONDecodeError, OSError):
        logger.exception("Could not read seen ids from %s", _FILE)
        return set()


def save(ids: set[str]) -> None:
    """Сохранить id заказов, которые уже были опубликованы."""

    _FILE.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile("w", encoding="utf-8", dir=_FILE.parent, delete=False) as tmp:
        json.dump(sorted(ids), tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name)

    tmp_path.replace(_FILE)
