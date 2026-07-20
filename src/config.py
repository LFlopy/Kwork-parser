import os
from dataclasses import dataclass, field
from functools import cached_property

from dotenv import load_dotenv

from src.categories import resolve_category_ids

load_dotenv()

DEFAULT_POLL_INTERVAL_SECONDS = 300


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


@dataclass
class Settings:
    """Настройки приложения, загружаемые из переменных окружения."""

    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    channel_id: str = field(default_factory=lambda: os.getenv("CHANNEL_ID", ""))
    poll_interval: int = field(
        default_factory=lambda: _get_int_env("POLL_INTERVAL", DEFAULT_POLL_INTERVAL_SECONDS)
    )
    _admin_ids_raw: str = field(default_factory=lambda: os.getenv("ADMIN_IDS", ""))
    kwork_login: str = field(default_factory=lambda: os.getenv("KWORK_LOGIN", ""))
    kwork_password: str = field(default_factory=lambda: os.getenv("KWORK_PASSWORD", ""))
    kwork_phone: str = field(default_factory=lambda: os.getenv("KWORK_PHONE", ""))
    kwork_mobile_auth: str = field(default_factory=lambda: os.getenv("KWORK_MOBILE_AUTH", ""))
    category_profile: str = field(default_factory=lambda: os.getenv("CATEGORY_PROFILE", "automation"))
    category_ids: str = field(default_factory=lambda: os.getenv("CATEGORY_IDS", ""))
    category_extra_ids: str = field(default_factory=lambda: os.getenv("CATEGORY_EXTRA_IDS", ""))
    category_exclude_ids: str = field(default_factory=lambda: os.getenv("CATEGORY_EXCLUDE_IDS", ""))

    @cached_property
    def admin_ids(self) -> tuple[int, ...]:
        """Вернуть id Telegram-пользователей с доступом администратора."""

        try:
            return tuple(int(x.strip()) for x in self._admin_ids_raw.split(",") if x.strip())
        except ValueError as exc:
            raise ValueError("ADMIN_IDS must be a comma-separated list of integer Telegram user ids") from exc

    def admin_id_list(self) -> list[int]:
        """Вернуть id администраторов списком для обратной совместимости."""

        return list(self.admin_ids)

    def missing_required(self) -> list[str]:
        """Вернуть имена обязательных переменных окружения, которые не настроены."""

        required = {
            "BOT_TOKEN": self.bot_token,
            "CHANNEL_ID": self.channel_id,
            "ADMIN_IDS": self._admin_ids_raw,
            "KWORK_LOGIN": self.kwork_login,
            "KWORK_PASSWORD": self.kwork_password,
            "KWORK_PHONE": self.kwork_phone,
        }
        return [name for name, value in required.items() if not value.strip()]

    def validate(self) -> None:
        """Проверить настройки и выбросить понятную ошибку запуска при проблемах."""

        missing = self.missing_required()
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        if not self.admin_ids:
            raise RuntimeError("ADMIN_IDS must contain at least one Telegram user id")
        self.active_category_ids()

    def active_category_ids(self) -> set[int]:
        """Вернуть id категорий, выбранные для мониторинга заказов Kwork."""

        return resolve_category_ids(
            self.category_profile,
            category_ids=self.category_ids,
            extra_ids=self.category_extra_ids,
            exclude_ids=self.category_exclude_ids,
        )
