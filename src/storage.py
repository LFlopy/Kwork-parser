import json
from pathlib import Path

_FILE = Path("seen_ids.json")


def load() -> set[str]:
    if _FILE.exists():
        return set(json.loads(_FILE.read_text(encoding="utf-8")))
    return set()


def save(ids: set[str]) -> None:
    _FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")
