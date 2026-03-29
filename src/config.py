import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    channel_id: str = field(default_factory=lambda: os.getenv("CHANNEL_ID", ""))
    poll_interval: int = field(default_factory=lambda: int(os.getenv("POLL_INTERVAL", "300")))
    _admin_ids_raw: str = field(default_factory=lambda: os.getenv("ADMIN_IDS", ""))
    kwork_login: str = field(default_factory=lambda: os.getenv("KWORK_LOGIN", ""))
    kwork_password: str = field(default_factory=lambda: os.getenv("KWORK_PASSWORD", ""))
    kwork_phone: str = field(default_factory=lambda: os.getenv("KWORK_PHONE", ""))

    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self._admin_ids_raw.split(",") if x.strip()]
