import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cachetools import TTLCache
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage, DeleteMessages

from services import recent_messages


class RecentMessagesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 0.0
        self.history = TTLCache(maxsize=3, ttl=10, timer=lambda: self.now)
        self.patch_history = patch.object(recent_messages, "_recent_messages", self.history)
        self.patch_history.start()
        self.addCleanup(self.patch_history.stop)
        self.patch_time = patch.object(recent_messages, "time", SimpleNamespace(monotonic=lambda: self.now))
        self.patch_time.start()
        self.addCleanup(self.patch_time.stop)

    async def test_inactive_users_expire_while_active_user_is_refreshed(self):
        recent_messages.track_recent_message(1, 1, 101)
        recent_messages.track_recent_message(1, 2, 102)
        self.now = 9
        recent_messages.track_recent_message(1, 2, 103)
        self.now = 11
        self.assertNotIn((1, 1), self.history)
        self.assertIn((1, 2), self.history)
        self.now = 20
        self.assertEqual(len(self.history), 0)

    async def test_distinct_users_are_bounded(self):
        for user_id in range(1000):
            recent_messages.track_recent_message(1, user_id, user_id)
        self.assertEqual(len(self.history), 3)
        self.assertIn((1, 999), self.history)

    async def test_cleanup_preserves_window_and_chat_boundaries(self):
        with patch.object(recent_messages.config.nsfw, "recent_cleanup_seconds", 10):
            recent_messages.track_recent_message(1, 1, 101)
            recent_messages.track_recent_message(2, 1, 201)
            self.now = 9
            recent_messages.track_recent_message(1, 1, 102)
            self.now = 11
            recent_messages.track_recent_message(1, 1, 103)
            recent_messages.track_recent_message(2, 1, 202)
            bot = AsyncMock()
            self.assertEqual(await recent_messages.delete_recent_messages(
                bot, 1, 1, exclude_message_id=103,
            ), 1)
            bot.delete_messages.assert_awaited_once_with(1, [102])
            self.assertIn((2, 1), self.history)

    async def test_bad_batch_falls_back_and_retains_only_failed_messages(self):
        for message_id in (101, 102, 103):
            recent_messages.track_recent_message(1, 1, message_id)
        bot = AsyncMock()
        bot.delete_messages.side_effect = TelegramBadRequest(
            method=DeleteMessages(chat_id=1, message_ids=[101, 102, 103]), message="can't delete message",
        )
        bot.delete_message.side_effect = [
            TelegramBadRequest(method=DeleteMessage(chat_id=1, message_id=101), message="message to delete not found"),
            TelegramBadRequest(method=DeleteMessage(chat_id=1, message_id=102), message="not enough rights"),
            True,
        ]
        with self.assertLogs("services.recent_messages", level="ERROR"):
            self.assertEqual(await recent_messages.delete_recent_messages(bot, 1, 1), 1)
        self.assertEqual([mid for _, mid in self.history[(1, 1)]], [102])
        bot.delete_messages.side_effect = None
        self.assertEqual(await recent_messages.delete_recent_messages(bot, 1, 1), 1)

    async def test_messages_arriving_during_deletion_are_retained(self):
        recent_messages.track_recent_message(1, 1, 101)
        bot = AsyncMock()

        async def delete_batch(chat_id, message_ids):
            recent_messages.track_recent_message(1, 1, 102)

        bot.delete_messages.side_effect = delete_batch
        self.assertEqual(await recent_messages.delete_recent_messages(bot, 1, 1), 1)
        self.assertEqual([mid for _, mid in self.history[(1, 1)]], [102])
