import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram import Dispatcher, F, Router
from aiogram.types import Chat, Message, MessageEntity, User, Update

from config import config
from handlers import group_events


class CustomEmojiModerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = AsyncMock()
        self.bot.id = 999
        self.member = SimpleNamespace(
            id=1, user_id=123, reputation_points=20, messages_count=20,
            violations_count_spam=0,
        )
        self.role = SimpleNamespace(status="member")
        self.updates = AsyncMock()
        self.log = AsyncMock()
        self.ml = Mock(return_value=False)
        self.profile_check = AsyncMock(return_value=False)
        self.autoban = AsyncMock()
        for patcher in (
            patch.object(group_events, "retrieve_or_create_member", new=AsyncMock(return_value=self.member)),
            patch.object(group_events, "retrieve_tgmember", new=AsyncMock(return_value=self.role)),
            patch.object(group_events, "queue_member_update", self.updates),
            patch.object(group_events, "write_log", self.log),
            patch.object(group_events, "ruspam_predict", self.ml),
            patch.object(group_events, "check_for_unwanted", self.profile_check),
            patch.object(group_events, "_maybe_autoban", self.autoban),
            patch.object(config.spam, "burst_enabled", False),
            patch.object(config.spam, "allow_media_threshold", 15),
            patch.object(config.spam, "single_emoji_rep_threshold", 15),
            patch.object(config.spam, "custom_emoji_rep_threshold", 50),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def message(self, kind="text", text="hello 😎😎"):
        entity = MessageEntity(type="custom_emoji", offset=6, length=2, custom_emoji_id="123456")
        if kind == "text":
            payload = {"text": text, "entities": [entity]}
        elif kind == "caption":
            payload = {"caption": text, "caption_entities": [entity], "photo": [{
                "file_id": "photo", "file_unique_id": "unique", "width": 100, "height": 100,
            }]}
        else:
            payload = {"sticker": {
                "file_id": "sticker", "file_unique_id": "unique", "type": kind,
                "width": 100, "height": 100, "is_animated": False, "is_video": False,
                **({"custom_emoji_id": "123456"} if kind == "custom_emoji" else {}),
            }}
        return Message(
            message_id=10, date=datetime.now(timezone.utc),
            chat=Chat(id=-100123, type="supergroup", title="Group"),
            from_user=User(id=123, is_bot=False, first_name="Alex"), **payload,
        ).as_(self.bot)

    async def test_custom_emoji_text_caption_and_sticker_blocked_before_ml(self):
        for kind in ("text", "caption", "custom_emoji"):
            with self.subTest(kind=kind):
                self.updates.reset_mock()
                self.log.reset_mock()
                self.autoban.reset_mock()
                with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                    await group_events.on_user_message(self.message(kind))
                    delete.assert_awaited_once()
                self.updates.assert_awaited_once_with(123, violations_count_spam=1, reputation_points=-5)
                self.log.assert_awaited_once()
                self.assertIn("эмодзи", self.log.await_args.args[2])
                self.autoban.assert_awaited_once()
        self.ml.assert_not_called()
        self.profile_check.assert_not_awaited()

    async def test_custom_emoji_edits_are_deleted_without_duplicate_penalties(self):
        for kind in ("text", "caption"):
            with self.subTest(kind=kind):
                with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                    await group_events.on_edited_user_message(self.message(kind))
                    delete.assert_awaited_once()
        self.updates.assert_not_awaited()
        self.autoban.assert_not_awaited()

    async def test_admins_and_members_at_threshold_can_post_custom_emoji(self):
        self.role.status = "administrator"
        with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
            await group_events.on_user_message(self.message())
            delete.assert_not_awaited()
        self.updates.assert_not_awaited()
        self.role.status = "member"
        self.member.reputation_points = 50
        for kind in ("text", "caption", "custom_emoji"):
            with self.subTest(kind=kind):
                self.updates.reset_mock()
                with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                    await group_events.on_user_message(self.message(kind))
                    delete.assert_not_awaited()
                self.updates.assert_awaited_once_with(123, messages_count=1, reputation_points=1)
        self.log.assert_not_awaited()

    async def test_regular_emoji_and_stickers_above_existing_threshold_unchanged(self):
        plain = self.message().model_copy(update={"entities": None})
        for message in (plain, self.message("regular")):
            with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                await group_events.on_user_message(message)
                delete.assert_not_awaited()
        self.log.assert_not_awaited()

    async def test_custom_emoji_threshold_is_configurable(self):
        with patch.object(config.spam, "custom_emoji_rep_threshold", 20):
            with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                await group_events.on_user_message(self.message())
                delete.assert_not_awaited()
        with patch.object(config.spam, "custom_emoji_rep_threshold", 21):
            with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                await group_events.on_user_message(self.message())
                delete.assert_awaited_once()

    async def test_regular_sticker_below_media_threshold_is_routed_and_deleted(self):
        self.member.reputation_points = 0
        dispatcher = Dispatcher()
        router = Router()
        router.message.register(group_events.on_user_message,
            F.content_type.in_(group_events.MEDIA_CONTENT_TYPES | {"text"}))
        dispatcher.include_router(router)
        with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
            await dispatcher.feed_update(self.bot, Update(update_id=1, message=self.message("regular")))
            delete.assert_awaited_once()
        self.updates.assert_not_awaited()
