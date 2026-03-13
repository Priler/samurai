import sys

# ensure libs are importable (censure, gender_extractor)
if "./libs" not in sys.path:
    sys.path.insert(0, "./libs")

from .profanity import check_for_profanity_all, check_name_for_violations
from .gender import Gender, detect_gender
from .cache import (
    retrieve_or_create_member,
    retrieve_tgmember,
    detect_gender as detect_gender_cached,
    invalidate_member_cache,
    invalidate_tgmember_cache,
)
from .owners import is_owner, list_owner_ids, add_owner, remove_owner, bootstrap_owners
from .chat_registry import (
    is_main_chat,
    get_main_chat_ids,
    register_chat,
    disable_chat,
    list_managed_chats,
    is_linked_channel,
    add_linked_channel,
    remove_linked_channel,
    list_linked_channels,
    bootstrap_chat_registry,
)
from .runtime_settings import (
    get_setting,
    set_setting,
    reset_setting,
    list_setting_keys,
    parse_setting_input,
    get_logs_chat_id,
    get_reports_chat_id,
    bootstrap_runtime_defaults,
)

__all__ = [
    "check_for_profanity_all",
    "check_name_for_violations",
    "Gender",
    "detect_gender",
    "detect_gender_cached",
    "retrieve_or_create_member",
    "retrieve_tgmember",
    "invalidate_member_cache",
    "invalidate_tgmember_cache",
    "is_owner",
    "list_owner_ids",
    "add_owner",
    "remove_owner",
    "bootstrap_owners",
    "is_main_chat",
    "get_main_chat_ids",
    "register_chat",
    "disable_chat",
    "list_managed_chats",
    "is_linked_channel",
    "add_linked_channel",
    "remove_linked_channel",
    "list_linked_channels",
    "bootstrap_chat_registry",
    "get_setting",
    "set_setting",
    "reset_setting",
    "list_setting_keys",
    "parse_setting_input",
    "get_logs_chat_id",
    "get_reports_chat_id",
    "bootstrap_runtime_defaults",
]
