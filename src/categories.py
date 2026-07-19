from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    """Kwork category metadata used for order filtering."""

    id: int
    name: str
    group: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CategoryProfile:
    """Reusable category selection preset."""

    key: str
    title: str
    category_ids: frozenset[int]


CATEGORY_CATALOG: dict[int, Category] = {
    41: Category(41, "Скрипты, боты и mini apps", "Разработка и IT", ("automation", "miniapps")),
    211: Category(211, "Парсеры", "Разработка и IT", ("parser", "parsing", "scraping")),
    3587: Category(3587, "Чат-боты", "Разработка и IT", ("bot", "chatbot")),
    7352: Category(7352, "Скрипты", "Разработка и IT", ("script", "automation")),
    3934090: Category(3934090, "Telegram Mini Apps", "Разработка и IT", ("telegram", "miniapp")),
    4158112: Category(4158112, "ИИ-боты", "Разработка и IT", ("ai", "llm")),
}

DEFAULT_CATEGORY_PROFILE = "automation"

CATEGORY_PROFILES: dict[str, CategoryProfile] = {
    "automation": CategoryProfile(
        key="automation",
        title="Автоматизация, парсеры и боты",
        category_ids=frozenset(CATEGORY_CATALOG),
    ),
    "parsers": CategoryProfile(
        key="parsers",
        title="Только парсеры",
        category_ids=frozenset({211}),
    ),
    "bots": CategoryProfile(
        key="bots",
        title="Чат-боты, ИИ-боты и Telegram Mini Apps",
        category_ids=frozenset({3587, 3934090, 4158112}),
    ),
    "scripts": CategoryProfile(
        key="scripts",
        title="Скрипты и mini apps",
        category_ids=frozenset({41, 7352, 3934090}),
    ),
}


def parse_category_ids(raw: str, *, source: str = "category ids") -> set[int]:
    """Parse comma-separated category ids."""

    try:
        return {int(value.strip()) for value in raw.split(",") if value.strip()}
    except ValueError as exc:
        raise ValueError(f"{source} must be a comma-separated list of integer category ids") from exc


def resolve_category_ids(
    profile: str = DEFAULT_CATEGORY_PROFILE,
    *,
    category_ids: str = "",
    extra_ids: str = "",
    exclude_ids: str = "",
) -> set[int]:
    """Resolve active category ids from profile and optional overrides."""

    if category_ids.strip():
        selected = parse_category_ids(category_ids, source="CATEGORY_IDS")
    else:
        if profile not in CATEGORY_PROFILES:
            available_profiles = ", ".join(sorted(CATEGORY_PROFILES))
            raise ValueError(f"Unknown CATEGORY_PROFILE {profile!r}; expected one of: {available_profiles}")
        selected = set(CATEGORY_PROFILES[profile].category_ids)

    selected.update(parse_category_ids(extra_ids, source="CATEGORY_EXTRA_IDS"))
    selected.difference_update(parse_category_ids(exclude_ids, source="CATEGORY_EXCLUDE_IDS"))
    return selected


def describe_category(category_id: int) -> str:
    """Return display name for a known or custom category id."""

    category = CATEGORY_CATALOG.get(category_id)
    return category.name if category else "Пользовательская категория"


def category_profile_title(profile: str) -> str:
    """Return display title for a category profile."""

    return CATEGORY_PROFILES[profile].title
