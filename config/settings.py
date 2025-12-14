from functools import lru_cache
from pathlib import Path
from tomllib import load
from typing import Type, TypeVar, List

from pydantic import BaseModel, SecretStr, field_validator


ConfigType = TypeVar("ConfigType", bound=BaseModel)


class BotConfig(BaseModel):
    owner: int = 0
    token: SecretStr = SecretStr("")
    version: str = "0.7"
    version_codename: str = "Eternal Ronin"


class LocaleConfig(BaseModel):
    default: str = "ru"
    available: List[str] = ["ru", "en"]


class GroupsConfig(BaseModel):
    # List of main chat IDs where bot operates
    main: List[int] = []
    # Single channel for reports
    reports: int = 0
    # Single channel for logs
    logs: int = 0
    # List of linked channels (for auto-forward detection)
    linked_channels: List[int] = []
    # Time in seconds for new users media restriction
    new_users_nomedia: int = 7776000
    
    # Cached sets for O(1) lookup (populated after init)
    _main_set: set = set()
    _linked_channels_set: set = set()
    
    def model_post_init(self, __context) -> None:
        """Build sets after model initialization."""
        object.__setattr__(self, '_main_set', set(self.main))
        object.__setattr__(self, '_linked_channels_set', set(self.linked_channels))
    
    def is_main_group(self, chat_id: int) -> bool:
        """Check if chat_id is a main group (O(1) lookup)."""
        return chat_id in self._main_set
    
    def is_linked_channel(self, chat_id: int) -> bool:
        """Check if chat_id is a linked channel (O(1) lookup)."""
        return chat_id in self._linked_channels_set
    
    def rebuild_sets(self) -> None:
        """Rebuild sets after modifying lists."""
        object.__setattr__(self, '_main_set', set(self.main))
        object.__setattr__(self, '_linked_channels_set', set(self.linked_channels))


class SpamConfig(BaseModel):
    member_messages_threshold: int = 10
    member_reputation_threshold: int = 10
    allow_media_threshold: int = 20
    remove_first_comments_interval: int = 30
    allow_comments_rep_threshold: int = 50
    women_remove_first_comments_interval: int = 600
    allow_comments_rep_threshold__woman: int = 10
    
    # Forward restriction for low-rep users
    allow_forwards_threshold: int = 30  # Rep required to forward messages
    forward_violation_penalty: int = 10  # Rep penalty for forwarding


class NSFWConfig(BaseModel):
    enabled: bool = True
    comb_sensual_prediction_threshold: float = 0.15
    comb_pornography_prediction_threshold: float = 0.15
    sensual_prediction_threshold: float = 0.8
    pornography_prediction_threshold: float = 0.3
    hentai_prediction_threshold: float = 0.5
    normal_prediction_threshold: float = 0.3
    normal_comb_sensual_prediction_threshold: float = 0.5
    normal_comb_pornography_prediction_threshold: float = 0.2
    anime_prediction_threshold: float = 0.7


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///db.sqlite"


class ThrottlingConfig(BaseModel):
    enabled: bool = True
    rate_limit: float = 0.5  # Minimum seconds between messages
    max_messages: int = 20   # Max messages in time window
    time_window: int = 60    # Time window in seconds


class HealthCheckConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


class AnnouncementGroupConfig(BaseModel):
    """Per-group announcement settings override."""
    sleep_from: str | None = None  # "23:00" format
    sleep_to: str | None = None    # "07:00" format
    utc_offset: int | None = None  # UTC offset in hours (e.g., 5 for UTC+5)


class AnnouncementsConfig(BaseModel):
    enabled: bool = True
    
    # Track last N messages per group to avoid spam
    history_size: int = 20
    
    # Max announcements in recent history before pausing
    max_stack: int = 3
    
    # Don't re-send same announcement if it's in last N messages
    avoid_duplicate_in_last: int = 15
    
    # Global sleep time (when not to send announcements)
    sleep_from: str = ""  # "23:00" format, empty = no sleep
    sleep_to: str = ""    # "07:00" format
    utc_offset: int = 0   # UTC offset in hours (e.g., 5 for UTC+5)
    
    # Per-group overrides (group_id -> settings)
    groups: dict[int, AnnouncementGroupConfig] = {}
    
    @field_validator('groups', mode='before')
    @classmethod
    def convert_group_keys(cls, v):
        """Convert string keys from TOML to int."""
        if isinstance(v, dict):
            return {int(k): AnnouncementGroupConfig.model_validate(val) for k, val in v.items()}
        return v


class CacheConfig(BaseModel):
    # Member data cache
    members_maxsize: int = 500
    members_ttl: int = 60  # seconds
    
    # Telegram member cache
    tgmembers_maxsize: int = 1000
    tgmembers_ttl: int = 300  # seconds
    
    # Gender detection cache (LRU, no TTL)
    gender_maxsize: int = 500
    
    # NSFW detection cache
    nsfw_maxsize: int = 200
    nsfw_ttl: int = 3600  # seconds
    
    # Batch update interval
    batch_flush_interval: int = 30  # seconds
    
    # Trusted user threshold (skip expensive checks)
    trusted_user_messages: int = 100


class MLConfig(BaseModel):
    """ML model memory management settings."""
    # Auto-unload models when not used
    auto_unload_enabled: bool = True
    
    # Time in minutes before unloading spam model
    spam_ttl_minutes: int = 10
    
    # Time in minutes before unloading nsfw model
    nsfw_ttl_minutes: int = 10
    
    # Check interval in seconds
    check_interval_seconds: int = 60


class Config(BaseModel):
    bot: BotConfig = BotConfig()
    locale: LocaleConfig = LocaleConfig()
    groups: GroupsConfig = GroupsConfig()
    spam: SpamConfig = SpamConfig()
    nsfw: NSFWConfig = NSFWConfig()
    db: DatabaseConfig = DatabaseConfig()
    throttling: ThrottlingConfig = ThrottlingConfig()
    healthcheck: HealthCheckConfig = HealthCheckConfig()
    cache: CacheConfig = CacheConfig()
    announcements: AnnouncementsConfig = AnnouncementsConfig()
    ml: MLConfig = MLConfig()


def get_config_path() -> Path:
    import os
    env_path = os.environ.get("CONFIG_FILE_PATH")
    if env_path:
        return Path(env_path)
    return Path("config.toml")


@lru_cache
def parse_config_file() -> dict:
    file_path = get_config_path()
    if not file_path.exists():
        return {}
    with open(file_path, "rb") as file:
        return load(file)


def load_config() -> Config:
    config_dict = parse_config_file()
    return Config.model_validate(config_dict) if config_dict else Config()


def _parse_int_list(value: str) -> List[int]:
    """Parse comma-separated list of integers from env var."""
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def apply_env_overrides(config: Config) -> Config:
    import os
    from dotenv import load_dotenv

    if Path(".env").exists():
        load_dotenv(".env")

    if os.environ.get("BOT_TOKEN"):
        config.bot.token = SecretStr(os.environ["BOT_TOKEN"])
    if os.environ.get("BOT_OWNER"):
        config.bot.owner = int(os.environ["BOT_OWNER"])
    if os.environ.get("BOT_LOCALE"):
        config.locale.default = os.environ["BOT_LOCALE"]
    
    # Groups - now supports comma-separated lists
    groups_changed = False
    if os.environ.get("GROUPS_MAIN"):
        config.groups.main = _parse_int_list(os.environ["GROUPS_MAIN"])
        groups_changed = True
    if os.environ.get("GROUPS_REPORTS"):
        config.groups.reports = int(os.environ["GROUPS_REPORTS"])
    if os.environ.get("GROUPS_LOGS"):
        config.groups.logs = int(os.environ["GROUPS_LOGS"])
    if os.environ.get("LINKED_CHANNELS"):
        config.groups.linked_channels = _parse_int_list(os.environ["LINKED_CHANNELS"])
        groups_changed = True
    
    # Rebuild sets after modifying lists
    if groups_changed:
        config.groups.rebuild_sets()
    
    if os.environ.get("DB_URL"):
        config.db.url = os.environ["DB_URL"]
    if os.environ.get("HEALTHCHECK_PORT"):
        config.healthcheck.port = int(os.environ["HEALTHCHECK_PORT"])

    return config


# Global config instance
config = apply_env_overrides(load_config())
