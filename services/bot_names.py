"""Names learned from confirmed reports and per-user false-positive exemptions."""
import asyncio
import copy
import json
import logging
import os
import tempfile
import unicodedata
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from services.cache import queue_member_update, retrieve_or_create_member, retrieve_tgmember
from services.recent_messages import ban_and_cleanup, delete_message_if_present, delete_recent_messages
from utils import MemberStatus, escape_html, generate_log_message, get_message_text, user_mention

logger = logging.getLogger(__name__)
_LOOKALIKES = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к",
    "m": "м", "o": "о", "p": "р", "t": "т", "x": "х", "y": "у",
})


def normalize_name(name: str) -> str:
    """Exact full-name matching after compatibility/case/lookalike folding."""
    name = unicodedata.normalize("NFKC", name).casefold()
    name = "".join(c for c in name if unicodedata.category(c) != "Cf")
    return " ".join(name.translate(_LOOKALIKES).split())


class BotNameStore:
    """Small durable state file; atomic writes publish only after success."""
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._state = None
        self._notified: set[tuple[int, int]] = set()

    def _read(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "names": {}, "exempt_users": {}, "reports": {}, "hits": {}}
        if (not isinstance(state, dict) or state.get("version") != 1
                or any(not isinstance(state.get(k), dict) for k in ("names", "exempt_users", "reports", "hits"))):
            raise ValueError("Invalid learned bot-name state")
        for key, name in state["names"].items():
            if not isinstance(name, str) or not key or normalize_name(name) != key:
                raise ValueError("Invalid learned bot name")
        for report in state["reports"].values():
            if (not isinstance(report, dict) or not isinstance(report.get("user_id"), int)
                    or not isinstance(report.get("name"), str)):
                raise ValueError("Invalid report name snapshot")
        for hit in state["hits"].values():
            if (not isinstance(hit, dict) or not isinstance(hit.get("count"), int)
                    or hit["count"] < 0 or not isinstance(hit.get("messages"), list)
                    or any(not isinstance(mid, int) for mid in hit["messages"])):
                raise ValueError("Invalid learned-name violation state")
        return state

    def _write(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    async def _load(self) -> None:
        if self._state is None:
            self._state = await asyncio.to_thread(self._read)

    async def _save(self, state: dict) -> None:
        write = asyncio.create_task(asyncio.to_thread(self._write, state))
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            # Do not release the store lock while a background write can still
            # overwrite a later mutation or disagree with the in-memory state.
            await write
            self._state = state
            raise
        self._state = state

    async def remember_report(self, chat_id: int, message_id: int, user_id: int, name: str) -> None:
        async with self._lock:
            await self._load()
            state = copy.deepcopy(self._state)
            state["reports"][f"{chat_id}:{message_id}"] = {"user_id": user_id, "name": name}
            await self._save(state)

    async def report_name(self, chat_id: int, message_id: int, user_id: int) -> str | None:
        async with self._lock:
            await self._load()
            report = self._state["reports"].get(f"{chat_id}:{message_id}")
            return report["name"] if report and report["user_id"] == user_id else None

    async def forget_report(self, chat_id: int, message_id: int) -> None:
        async with self._lock:
            await self._load()
            key = f"{chat_id}:{message_id}"
            if key in self._state["reports"]:
                state = copy.deepcopy(self._state)
                del state["reports"][key]
                await self._save(state)

    async def learn(self, name: str) -> None:
        key = normalize_name(name)
        if not key:
            return
        async with self._lock:
            await self._load()
            if key not in self._state["names"]:
                state = copy.deepcopy(self._state)
                state["names"][key] = name
                await self._save(state)

    async def match(self, user_id: int, name: str) -> str | None:
        async with self._lock:
            await self._load()
            if str(user_id) in self._state["exempt_users"]:
                return None
            return self._state["names"].get(normalize_name(name))

    async def exempt(self, user_id: int) -> None:
        async with self._lock:
            await self._load()
            if str(user_id) not in self._state["exempt_users"]:
                state = copy.deepcopy(self._state)
                state["exempt_users"][str(user_id)] = True
                state["hits"] = {k: v for k, v in state["hits"].items() if k.split(":")[-1] != str(user_id)}
                await self._save(state)

    async def record_hit(self, chat_id: int, user_id: int, message_id: int) -> tuple[int, bool]:
        """Count distinct removed messages; edits and duplicate updates count once."""
        async with self._lock:
            await self._load()
            if str(user_id) in self._state["exempt_users"]:
                return 0, False
            key = f"{chat_id}:{user_id}"
            previous = self._state["hits"].get(key, {"count": 0, "messages": []})
            if message_id in previous["messages"]:
                return previous["count"], False
            state = copy.deepcopy(self._state)
            count = previous["count"] + 1
            state["hits"][key] = {"count": count, "messages": (previous["messages"] + [message_id])[-100:]}
            await self._save(state)
            return count, True


store = BotNameStore(Path("data/learned_bot_names.json"))


async def enforce_learned_name(message) -> bool:
    """Delete low-reputation matches before commands/media handlers can run."""
    user_id, chat_id = message.from_user.id, message.chat.id
    try:
        learned_name = await store.match(user_id, message.from_user.full_name)
    except (OSError, ValueError):
        logger.exception("Cannot read learned bot names")
        return False
    if learned_name is None:
        return False
    role = await retrieve_tgmember(message.bot, chat_id, user_id)
    if role.status in MemberStatus.admin_statuses():
        return False
    if role.status == MemberStatus.KICKED.value:
        await delete_message_if_present(message)
        await delete_recent_messages(message.bot, chat_id, user_id, exclude_message_id=message.message_id)
        return True
    member = await retrieve_or_create_member(user_id)
    if member.reputation_points >= config.spam.learned_name_rep_threshold:
        return False

    await delete_message_if_present(message)
    try:
        count, new_hit = await store.record_hit(chat_id, user_id, message.message_id)
    except (OSError, ValueError):
        logger.exception("Cannot persist learned-name violation for user %s", user_id)
        return True  # Deleted messages must not earn reputation.
    if not count:  # A moderator exempted this user while deletion was in flight.
        return True
    if new_hit:
        await queue_member_update(user_id, violations_count_spam=1, reputation_points=-5)
    await delete_recent_messages(message.bot, chat_id, user_id, exclude_message_id=message.message_id)

    banned = False
    if (config.spam.autoban_enabled and count >= config.spam.learned_name_autoban_threshold
            and member.reputation_points < config.spam.autoban_rep_threshold):
        try:
            await ban_and_cleanup(message.bot, chat_id, user_id)
            banned = True
        except TelegramAPIError:
            logger.exception("Failed to autoban learned-name match %s in chat %s", user_id, chat_id)

    # Keep a review button from the first hit, plus a log when escalation happens.
    if (chat_id, user_id) not in store._notified or banned:
        text = (
            f"{escape_html(get_message_text(message) or '[медиа без текста]')}\n\n"
            f"<i>Автор:</i> {user_mention(message.from_user)}\n"
            f"<i>Имя из подтверждённых репортов:</i> {escape_html(learned_name)}\n"
            f"<i>Репутация:</i> {member.reputation_points}\n"
            f"<i>Удалённых сообщений:</i> {count}"
        )
        if banned:
            text += "\n<b>Автобан за повторные сообщения.</b>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Это не бот", callback_data=f"notbot_{chat_id}_{user_id}",
        )]])
        try:
            await message.bot.send_message(
                config.groups.logs,
                generate_log_message(text, "🤖 Потенциальный бот", message.chat.title),
                reply_markup=keyboard,
            )
            store._notified.add((chat_id, user_id))
        except TelegramAPIError:
            logger.exception("Failed to log potential bot %s in chat %s", user_id, chat_id)
    return True
