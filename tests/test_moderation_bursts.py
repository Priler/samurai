import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram import Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import BanChatMember, DeleteMessages
from aiogram.types import Chat, Message, MessageOriginChannel, Update, User

from handlers import callbacks, group_events
from middlewares import register_all_middlewares
from middlewares.recent_messages import RecentMessagesMiddleware
from services import cache, recent_messages


class ModerationBurstTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cache.clear_all_caches()
        recent_messages.clear_recent_messages()
        self.addCleanup(cache.clear_all_caches)
        self.addCleanup(recent_messages.clear_recent_messages)
        self.bot = AsyncMock()
        self.bot.id = 999
        self.member = SimpleNamespace(id=1, user_id=123, reputation_points=0)
        patcher = patch.object(group_events.config.nsfw, "enabled", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.main_groups = patch.object(type(group_events.config.groups), "is_main_group", return_value=True)
        self.main_groups.start()
        self.addCleanup(self.main_groups.stop)

    def message(self, message_id, user_id=123, **kwargs):
        return Message(
            message_id=message_id, date=datetime.now(timezone.utc),
            chat=Chat(id=-100123, type="supergroup", title="Group"),
            from_user=User(id=user_id, is_bot=False, first_name="Alex"),
            **kwargs,
        ).as_(self.bot)

    async def test_soft_profile_detection_removes_all_recent_comments(self):
        photo = SimpleNamespace(file_unique_id="avatar", file_id="file")
        self.bot.get_user_profile_photos.return_value = SimpleNamespace(photos=[[photo]])
        cache.cache_nsfw_result(123, "avatar", "soft")
        for message_id in (1, 2, 3, 4):
            recent_messages.track_recent_message(-100123, 123, message_id)
        self.assertTrue(await group_events.check_for_unwanted(self.message(4, text="hello"), "hello", self.member))
        self.bot.delete_messages.assert_awaited_once_with(-100123, [1, 2, 3])

    async def test_spam_name_detection_removes_previous_comments(self):
        recent_messages.track_recent_message(-100123, 123, 1)
        with patch.object(group_events, "check_name_for_violations", return_value=False):
            self.assertTrue(await group_events.check_for_unwanted(self.message(2, text="hello"), "hello", self.member))
        self.bot.delete_messages.assert_awaited_once_with(-100123, [1])

    async def test_pending_burst_is_serialized_and_blocked_after_first_detection(self):
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        middleware = RecentMessagesMiddleware()

        async def handler(message, data):
            calls.append(message.message_id)
            if message.message_id == 1:
                started.set()
                await release.wait()
                cache.mark_nsfw_profile_checked(123, "soft")
                await group_events._report_nsfw(message, "hello", self.member, "NSFW", cleanup_recent=True)

        with patch("middlewares.recent_messages.retrieve_tgmember", create=True,
                   new=AsyncMock(return_value=SimpleNamespace(status="member"))):
            first = asyncio.create_task(middleware(handler, self.message(1, text="hello"), {}))
            await started.wait()
            second = asyncio.create_task(middleware(handler, self.message(2, text="another comment"), {}))
            await asyncio.sleep(0)
            queued_calls = list(calls)
            release.set()
            await asyncio.gather(first, second)
        self.assertEqual(queued_calls, [1])
        self.assertEqual(calls, [1])
        self.bot.delete_messages.assert_any_await(-100123, [2])

    async def test_four_comments_under_post_are_removed_with_one_profile_check_and_log(self):
        dispatcher = Dispatcher()
        router = Router()
        router.message.register(group_events.on_user_message, F.text)
        dispatcher.include_router(router)
        register_all_middlewares(dispatcher, enable_throttling=False)
        started, release = asyncio.Event(), asyncio.Event()
        photo = SimpleNamespace(file_unique_id="avatar", file_id="file")
        cache.cache_nsfw_result(123, "avatar", "soft")
        recent_messages.track_recent_message(-100123, 456, 99)

        async def profile_photos(**kwargs):
            started.set()
            await release.wait()
            return SimpleNamespace(photos=[[photo]])

        self.bot.get_user_profile_photos.side_effect = profile_photos
        post_date = datetime.now(timezone.utc) - timedelta(hours=1)
        post = self.message(1000, user_id=777000, text="Channel post", is_automatic_forward=True,
            forward_origin=MessageOriginChannel(
                date=post_date, chat=Chat(id=-100321, type="channel"), message_id=1,
            ))
        role = SimpleNamespace(status="member")
        member = SimpleNamespace(id=1, user_id=123, reputation_points=0, messages_count=0)
        with patch.object(group_events, "retrieve_or_create_member", new=AsyncMock(return_value=member)), \
             patch.object(group_events, "retrieve_tgmember", new=AsyncMock(return_value=role)), \
             patch("middlewares.recent_messages.retrieve_tgmember", new=AsyncMock(return_value=role)), \
             patch.object(group_events, "ruspam_predict", return_value=False), \
             patch.object(group_events, "queue_member_update", new_callable=AsyncMock) as reputation, \
             patch.object(type(group_events.config.groups), "is_linked_channel", return_value=True):
            updates = [Update(update_id=i, message=self.message(i, text=f"Обычный комментарий номер {i}",
                       reply_to_message=post)) for i in (1, 2, 3, 4)]
            first = asyncio.create_task(dispatcher.feed_update(self.bot, updates[0]))
            await started.wait()
            rest = [asyncio.create_task(dispatcher.feed_update(self.bot, update)) for update in updates[1:]]
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(first, *rest)
            reputation.assert_not_awaited()
        self.bot.get_user_profile_photos.assert_awaited_once()
        self.bot.send_message.assert_awaited_once()
        self.bot.delete_messages.assert_any_await(-100123, [2, 3, 4])
        self.assertIn((-100123, 456), recent_messages._recent_messages)

    async def test_outer_tracking_remembers_unmatched_messages(self):
        dispatcher = Dispatcher()
        router = Router()
        handler = AsyncMock()
        async def on_text(message):
            await handler(message)
        router.message.register(on_text, F.text)
        dispatcher.include_router(router)
        register_all_middlewares(dispatcher, enable_throttling=False)
        # Dice has no matching handler, but must still be available for cleanup.
        await dispatcher.feed_update(self.bot, Update(update_id=1, message=self.message(
            1, dice={"emoji": "🎲", "value": 3},
        )))
        self.assertIn((-100123, 123), recent_messages._recent_messages)
        handler.assert_not_awaited()

    async def test_known_unsafe_profile_cannot_bypass_moderation_with_commands(self):
        cache.mark_nsfw_profile_checked(123, "hard")
        handler = AsyncMock()
        with patch("middlewares.recent_messages.retrieve_tgmember", create=True,
                   new=AsyncMock(return_value=SimpleNamespace(status="member"))):
            await RecentMessagesMiddleware()(handler, self.message(1, text="!me"), {})
        handler.assert_not_awaited()

    async def test_admin_and_disabled_nsfw_exemptions_are_preserved(self):
        cache.mark_nsfw_profile_checked(123, "hard")
        handler = AsyncMock()
        with patch("middlewares.recent_messages.retrieve_tgmember",
                   new=AsyncMock(return_value=SimpleNamespace(status="administrator"))):
            await RecentMessagesMiddleware()(handler, self.message(1, text="!me"), {})
        handler.assert_awaited_once()
        handler.reset_mock()
        with patch.object(group_events.config.nsfw, "enabled", False):
            await RecentMessagesMiddleware()(handler, self.message(2, text="!me"), {})
        handler.assert_awaited_once()

    async def test_different_users_do_not_wait_for_each_others_ml_check(self):
        started, release = asyncio.Event(), asyncio.Event()
        middleware = RecentMessagesMiddleware()
        calls = []

        async def handler(message, data):
            calls.append(message.from_user.id)
            if message.from_user.id == 123:
                started.set()
                await release.wait()

        first = asyncio.create_task(middleware(handler, self.message(1, text="hello"), {}))
        await started.wait()
        try:
            await middleware(handler, self.message(2, user_id=456, text="hello"), {})
            self.assertEqual(calls, [123, 456])
        finally:
            release.set()
            await first
        self.assertEqual(len(middleware._user_locks), 0)

    async def test_nsfw_ban_requests_revocation_and_cleans_tracked_comments(self):
        recent_messages.track_recent_message(-100123, 123, 1)
        call = SimpleNamespace(
            data="nsfw_ban_123_-100123", bot=self.bot, answer=AsyncMock(),
            message=SimpleNamespace(html_text="report", edit_text=AsyncMock()),
        )
        await callbacks.callback_nsfw_ban(call)
        self.bot.ban_chat_member.assert_awaited_once_with(chat_id=-100123, user_id=123, revoke_messages=True)
        self.bot.delete_messages.assert_awaited_once_with(-100123, [1])

    async def test_failed_nsfw_ban_keeps_button_and_does_not_claim_success(self):
        self.bot.ban_chat_member.side_effect = TelegramBadRequest(
            method=BanChatMember(chat_id=-100123, user_id=123), message="not enough rights",
        )
        call = SimpleNamespace(
            data="nsfw_ban_123_-100123", bot=self.bot, answer=AsyncMock(),
            message=SimpleNamespace(html_text="report", edit_text=AsyncMock()),
        )
        with self.assertLogs("handlers.callbacks", level="ERROR"):
            await callbacks.callback_nsfw_ban(call)
        call.message.edit_text.assert_not_awaited()
        self.assertTrue(call.answer.await_args.kwargs["show_alert"])

    async def test_cleanup_failure_retains_messages_for_retry(self):
        recent_messages.track_recent_message(-100123, 123, 1)
        self.bot.delete_messages.side_effect = TelegramNetworkError(
            method=DeleteMessages(chat_id=-100123, message_ids=[1]), message="offline",
        )
        with self.assertLogs("services.recent_messages", level="ERROR"):
            self.assertEqual(await recent_messages.delete_recent_messages(self.bot, -100123, 123), 0)
        self.bot.delete_messages.side_effect = None
        self.assertEqual(await recent_messages.delete_recent_messages(self.bot, -100123, 123), 1)

    async def test_spam_ban_cleans_history_and_only_marks_record_after_success(self):
        recent_messages.track_recent_message(-100123, 123, 1)
        record = SimpleNamespace(chat_id=-100123, is_blocked=False, update=AsyncMock())
        call = SimpleNamespace(
            data="spam_ban_1_123", bot=self.bot, answer=AsyncMock(),
            message=SimpleNamespace(html_text="report", edit_text=AsyncMock()),
        )
        with patch.object(callbacks, "Spam", Mock(objects=SimpleNamespace(get=AsyncMock(return_value=record)))):
            self.bot.ban_chat_member.side_effect = TelegramBadRequest(
                method=BanChatMember(chat_id=-100123, user_id=123), message="not enough rights",
            )
            with self.assertLogs("handlers.callbacks", level="ERROR"):
                await callbacks.callback_spam_ban(call)
            self.assertFalse(record.is_blocked)
            record.update.assert_not_awaited()
            call.message.edit_text.assert_not_awaited()
            self.bot.ban_chat_member.side_effect = None
            await callbacks.callback_spam_ban(call)
        self.assertTrue(record.is_blocked)
        record.update.assert_awaited_once()
        self.bot.delete_messages.assert_awaited_once_with(-100123, [1])
        self.bot.ban_chat_member.assert_awaited_with(chat_id=-100123, user_id=123, revoke_messages=True)

    async def test_spam_autoban_also_revokes_and_cleans_recent_messages(self):
        recent_messages.track_recent_message(-100123, 123, 1)
        member = SimpleNamespace(violations_count_spam=101, reputation_points=0)
        with patch.object(group_events.config.spam, "autoban_enabled", True):
            with patch.object(group_events.config.spam, "autoban_threshold", 100):
                await group_events._maybe_autoban(self.message(2, text="spam"), member, 5, "spam")
        self.bot.ban_chat_member.assert_awaited_once_with(chat_id=-100123, user_id=123, revoke_messages=True)
        self.bot.delete_messages.assert_awaited_once_with(-100123, [1])
