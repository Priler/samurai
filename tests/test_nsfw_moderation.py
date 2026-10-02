import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import DeleteMessage, SendMessage

from handlers import callbacks, group_events
from services import cache


class NSFWModerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cache.clear_all_caches()
        self.addCleanup(cache.clear_all_caches)
        patcher = patch.object(group_events.config.nsfw, "enabled", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.message = SimpleNamespace(
            reply_to_message=None, content_type=ContentType.TEXT,
            from_user=SimpleNamespace(id=123, full_name="Alex"),
            chat=SimpleNamespace(id=-100123, title="Group"),
            message_id=10, bot=AsyncMock(), delete=AsyncMock(),
        )
        self.member = SimpleNamespace(id=1, user_id=123, reputation_points=0)

    async def test_name_violation_is_enforced_on_every_message(self):
        with patch.object(group_events, "check_name_for_violations", return_value=False):
            with patch.object(group_events, "_report_nsfw", new_callable=AsyncMock) as report:
                for _ in range(2):
                    self.assertTrue(await group_events.check_for_unwanted(
                        self.message, "hello", self.member,
                    ))
                self.assertEqual(report.await_count, 2)
                self.message.bot.get_user_profile_photos.assert_not_awaited()

    async def test_unsafe_cached_profile_is_enforced_without_inference(self):
        for level in (group_events.NSFW_SOFT, group_events.NSFW_HARD):
            with self.subTest(level=level):
                cache.mark_nsfw_profile_checked(123, level)
                with patch.object(group_events, "_report_nsfw", new_callable=AsyncMock) as report:
                    for _ in range(2):
                        self.assertTrue(await group_events.check_for_unwanted(
                            self.message, "hello", self.member,
                        ))
                    self.assertEqual(report.await_count, 2)
                    self.assertTrue(report.await_args.kwargs["cleanup_recent"])
                    self.message.bot.get_user_profile_photos.assert_not_awaited()

    async def test_clean_profile_cooldown_skips_photo_requests(self):
        cache.mark_nsfw_profile_checked(123)
        self.assertFalse(await group_events.check_for_unwanted(self.message, "hello", self.member))
        self.message.bot.get_user_profile_photos.assert_not_awaited()

    async def test_detection_persists_unsafe_verdict_for_subsequent_messages(self):
        photo = SimpleNamespace(file_unique_id="photo", file_id="file")
        self.message.bot.get_user_profile_photos.return_value = SimpleNamespace(photos=[[photo]])
        cache.cache_nsfw_result(123, "photo", "hard")
        with patch.object(group_events, "_report_nsfw", new_callable=AsyncMock) as report:
            for _ in range(2):
                self.assertTrue(await group_events.check_for_unwanted(self.message, "hello", self.member))
            self.assertEqual(report.await_count, 2)
        self.message.bot.get_user_profile_photos.assert_awaited_once()
        self.assertEqual(cache.get_cached_nsfw_profile_result(123), "hard")

    async def test_expired_profile_result_triggers_recheck(self):
        cache.mark_nsfw_profile_checked(123, "hard")
        cache.nsfw_profile_cooldown.pop(123)
        self.message.bot.get_user_profile_photos.return_value = SimpleNamespace(photos=[])
        self.assertFalse(await group_events.check_for_unwanted(self.message, "hello", self.member))
        self.message.bot.get_user_profile_photos.assert_awaited_once_with(user_id=123)
        self.assertEqual(cache.get_cached_nsfw_profile_result(123), "none")

    async def test_logging_failure_does_not_prevent_delete_or_cleanup(self):
        events = []

        async def delete():
            events.append("delete")

        async def unavailable_log(*args, **kwargs):
            events.append("log")
            raise TelegramNetworkError(method=SendMessage(chat_id=1, text="log"), message="offline")

        self.message.delete.side_effect = delete
        self.message.bot.send_message.side_effect = unavailable_log
        with patch.object(group_events, "delete_recent_messages", new_callable=AsyncMock) as cleanup:
            with self.assertLogs("handlers.group_events", level="ERROR"):
                await group_events._report_nsfw(
                    self.message, "hello", self.member, "NSFW", cleanup_recent=True,
                )
            cleanup.assert_awaited_once()
        self.assertEqual(events, ["delete", "log"])

    async def test_cleanup_failure_does_not_prevent_delete_or_logging(self):
        error = TelegramNetworkError(method=SendMessage(chat_id=1, text="log"), message="offline")
        with patch.object(group_events, "delete_recent_messages", side_effect=error):
            with self.assertLogs("handlers.group_events", level="ERROR"):
                await group_events._report_nsfw(
                    self.message, "hello", self.member, "NSFW", cleanup_recent=True,
                )
        self.message.delete.assert_awaited_once()
        self.message.bot.send_message.assert_awaited_once()

    async def test_already_deleted_queued_message_does_not_prevent_cleanup(self):
        self.message.delete.side_effect = TelegramBadRequest(
            method=DeleteMessage(chat_id=-100123, message_id=10), message="message to delete not found",
        )
        with patch.object(group_events, "delete_recent_messages", new_callable=AsyncMock) as cleanup:
            await group_events._report_nsfw(self.message, "hello", self.member, "NSFW", cleanup_recent=True)
            cleanup.assert_awaited_once()
        self.message.bot.send_message.assert_awaited_once()

    async def test_moderator_safe_override_clears_cached_unsafe_verdict(self):
        cache.mark_nsfw_profile_checked(123, "hard")
        cache.cache_nsfw_result(123, "photo", "hard")
        call = SimpleNamespace(
            data="nsfw_safe_1", answer=AsyncMock(),
            message=SimpleNamespace(html_text="report", edit_text=AsyncMock()),
        )
        with patch.object(callbacks, "Member", Mock(objects=SimpleNamespace(get=AsyncMock(return_value=self.member)))):
            with patch.object(callbacks, "queue_member_update", new_callable=AsyncMock) as update:
                await callbacks.callback_nsfw_safe(call)
        update.assert_awaited_once_with(123, messages_count=1, reputation_points=10)
        self.assertEqual(cache.get_cached_nsfw_profile_result(123), "none")
        self.assertIsNone(cache.get_cached_nsfw_result(123, "photo"))
