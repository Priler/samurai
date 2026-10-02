import asyncio
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import BanChatMember, SendMessage
from aiogram.types import Chat, Message, User

from config import config
from handlers import callbacks, user_actions
from middlewares.recent_messages import RecentMessagesMiddleware
from services import bot_names, cache, recent_messages, reports


class LearnedBotNameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "names.json"
        self.store = bot_names.BotNameStore(self.path)
        patcher = patch.object(bot_names, "store", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        reports._state_lock = asyncio.Lock()
        for collection in (reports._pending_reports, reports._processing_report_actions,
                           reports._resolved_reports, reports._active_report_by_user,
                           reports._report_users, reports._recent_reports):
            collection.clear()
        cache.clear_all_caches()
        recent_messages.clear_recent_messages()
        self.addCleanup(cache.clear_all_caches)
        self.addCleanup(recent_messages.clear_recent_messages)
        self.bot = AsyncMock()
        self.member = SimpleNamespace(id=1, user_id=123, reputation_points=0)
        self.role = SimpleNamespace(status="member")

        async def update_member(user_id, **changes):
            for field, delta in changes.items():
                setattr(self.member, field, getattr(self.member, field, 0) + delta)

        self.penalty = AsyncMock(side_effect=update_member)
        patches = (
            patch.object(bot_names, "retrieve_or_create_member", new=AsyncMock(return_value=self.member)),
            patch.object(bot_names, "retrieve_tgmember", new=AsyncMock(return_value=self.role)),
            patch.object(bot_names, "queue_member_update", self.penalty),
            patch.object(config.spam, "learned_name_rep_threshold", 30),
            patch.object(config.spam, "learned_name_autoban_threshold", 5),
            patch.object(config.spam, "autoban_enabled", True),
            patch.object(config.spam, "autoban_rep_threshold", 100),
            patch.object(config.bot, "owner", 999),
            patch.object(type(config.groups), "is_main_group", return_value=True),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def message(self, message_id=1, name="Miras", user_id=123):
        return Message(
            message_id=message_id, date=datetime.now(timezone.utc), text="hello",
            chat=Chat(id=-100123, type="supergroup", title="Group"),
            from_user=User(id=user_id, is_bot=False, first_name=name),
        ).as_(self.bot)

    def callback(self, data="rdelban_-100123_10_123_456_11", actor=999):
        return SimpleNamespace(
            data=data, bot=self.bot, from_user=SimpleNamespace(id=actor), answer=AsyncMock(),
            message=SimpleNamespace(html_text="report", edit_text=AsyncMock()),
        )

    async def test_normalization_matches_exact_names_and_visual_lookalikes(self):
        await self.store.learn("Oлюша")
        self.assertEqual(await self.store.match(123, "  ОЛЮША\u200b  "), "Oлюша")
        self.assertIsNone(await self.store.match(123, "Олюша Иванова"))
        self.assertIsNone(await self.store.match(123, "Олюшенька"))
        await self.store.learn("Miras")
        self.assertEqual(await self.store.match(123, "ＭＩＲＡＳ"), "Miras")

    async def test_names_snapshots_counts_and_exemptions_survive_reload(self):
        await self.store.learn("Miras")
        await self.store.remember_report(-100123, 10, 123, "Василиса")
        self.assertEqual(await self.store.record_hit(-100123, 123, 1), (1, True))
        reloaded = bot_names.BotNameStore(self.path)
        self.assertEqual(await reloaded.match(123, "miras"), "Miras")
        self.assertEqual(await reloaded.report_name(-100123, 10, 123), "Василиса")
        self.assertEqual(await reloaded.record_hit(-100123, 123, 2), (2, True))
        await reloaded.exempt(123)
        reloaded = bot_names.BotNameStore(self.path)
        self.assertIsNone(await reloaded.match(123, "Miras"))
        self.assertEqual(await reloaded.match(456, "Miras"), "Miras")
        self.assertEqual(await reloaded.record_hit(-100123, 123, 3), (0, False))

    async def test_duplicate_message_ids_count_once(self):
        self.assertEqual(await self.store.record_hit(-100123, 123, 1), (1, True))
        self.assertEqual(await self.store.record_hit(-100123, 123, 1), (1, False))
        self.assertEqual(await self.store.record_hit(-100456, 123, 1), (1, True))

    async def test_report_command_captures_name_and_ban_learns_snapshot_after_restart(self):
        reported = SimpleNamespace(
            from_user=SimpleNamespace(id=123, full_name="Василиса"), message_id=10,
            date=datetime.now(timezone.utc),
            reply=AsyncMock(return_value=SimpleNamespace(message_id=11, delete=AsyncMock())),
            forward=AsyncMock(),
        )
        message = SimpleNamespace(
            reply_to_message=reported, text="!report spam", bot=self.bot,
            from_user=SimpleNamespace(id=456, full_name="Reporter"),
            chat=SimpleNamespace(id=-100123, title="Group"), delete=AsyncMock(), reply=AsyncMock(),
        )
        self.bot.get_chat_member.return_value = SimpleNamespace(status="member")
        await user_actions.cmd_report(message)
        self.assertIsNone(await self.store.match(789, "Василиса"))
        self.assertEqual(await self.store.report_name(-100123, 10, 123), "Василиса")
        reported.from_user.full_name = "Different name now"
        bot_names.store = bot_names.BotNameStore(self.path)
        with patch.object(callbacks, "queue_member_update", new_callable=AsyncMock):
            await callbacks.callback_report_delete_and_ban(self.callback())
        self.assertEqual(await bot_names.store.match(789, "Василиса"), "Василиса")
        self.assertIsNone(await bot_names.store.match(789, "Different name now"))
        self.assertIsNone(await bot_names.store.report_name(-100123, 10, 123))

    async def test_failed_ban_does_not_learn_name_and_successful_retry_does(self):
        await reports.begin_report(-100123, 10, 123, "Miras")
        await reports.finish_report(-100123, 10, success=True)
        self.bot.ban_chat_member.side_effect = TelegramBadRequest(
            method=BanChatMember(chat_id=-100123, user_id=123), message="not enough rights",
        )
        call = self.callback()
        with self.assertRaises(TelegramBadRequest):
            await callbacks.callback_report_delete_and_ban(call)
        self.assertIsNone(await self.store.match(789, "Miras"))
        self.assertEqual(await self.store.report_name(-100123, 10, 123), "Miras")
        self.bot.ban_chat_member.side_effect = None
        with patch.object(callbacks, "queue_member_update", new_callable=AsyncMock):
            await callbacks.callback_report_delete_and_ban(call)
        self.assertEqual(await self.store.match(789, "Miras"), "Miras")

    async def test_delete_only_and_dismissed_reports_do_not_teach_names(self):
        for action, handler in (("rdel", callbacks.callback_report_delete), ("rdismiss", callbacks.callback_report_dismiss)):
            with self.subTest(action=action):
                reports._resolved_reports.clear()
                await self.store.remember_report(-100123, 10, 123, "Miras")
                data = "rdel_-100123_10_456_11" if action == "rdel" else "rdismiss_-100123_10_123_456_11"
                with patch.object(callbacks, "queue_member_update", new_callable=AsyncMock):
                    await handler(self.callback(data))
                self.assertIsNone(await self.store.match(789, "Miras"))
                self.assertIsNone(await self.store.report_name(-100123, 10, 123))

    async def test_ordinary_user_cannot_teach_or_exempt_names(self):
        await self.store.remember_report(-100123, 10, 123, "Miras")
        self.bot.get_chat_member.return_value = SimpleNamespace(status="member")
        await callbacks.callback_report_delete_and_ban(self.callback(actor=888))
        self.bot.ban_chat_member.assert_not_awaited()
        self.assertIsNone(await self.store.match(789, "Miras"))
        await self.store.learn("Miras")
        call = self.callback("notbot_-100123_123", actor=888)
        await callbacks.callback_not_a_bot(call)
        self.assertEqual(await self.store.match(123, "Miras"), "Miras")
        self.assertTrue(call.answer.await_args.kwargs["show_alert"])

    async def test_chat_admin_can_exempt_specific_user_across_names_and_chats(self):
        await self.store.learn("Miras")
        await self.store.learn("Василиса")
        self.bot.get_chat_member.return_value = SimpleNamespace(status="administrator")
        await callbacks.callback_not_a_bot(self.callback("notbot_-100123_123", actor=888))
        self.bot.get_chat_member.assert_awaited_once_with(-100123, 888)
        self.assertIsNone(await self.store.match(123, "Miras"))
        self.assertIsNone(await self.store.match(123, "Василиса"))
        self.assertEqual(await self.store.match(456, "Miras"), "Miras")

    async def test_low_rep_match_removed_logged_and_autobanned_after_five_hits(self):
        await self.store.learn("Miras")
        for message_id in range(1, 6):
            self.assertTrue(await bot_names.enforce_learned_name(self.message(message_id)))
            self.assertEqual(self.bot.ban_chat_member.await_count, int(message_id == 5))
        self.assertEqual(self.penalty.await_count, 5)
        self.assertEqual(self.member.violations_count_spam, 5)
        self.bot.ban_chat_member.assert_awaited_once_with(chat_id=-100123, user_id=123, revoke_messages=True)
        self.assertEqual(self.bot.send_message.await_count, 2)
        first_log = self.bot.send_message.await_args_list[0]
        self.assertIn("ПОТЕНЦИАЛЬНЫЙ БОТ", first_log.args[1])
        button = first_log.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual((button.text, button.callback_data), ("Это не бот", "notbot_-100123_123"))

    async def test_exemption_stops_future_deletion_but_does_not_exempt_other_users(self):
        await self.store.learn("Miras")
        self.assertTrue(await bot_names.enforce_learned_name(self.message(1)))
        await callbacks.callback_not_a_bot(self.callback("notbot_-100123_123"))
        self.assertFalse(await bot_names.enforce_learned_name(self.message(2)))
        self.assertTrue(await bot_names.enforce_learned_name(self.message(3, user_id=456)))

    async def test_admins_high_rep_users_and_distinct_full_names_pass(self):
        await self.store.learn("Miras")
        self.role.status = "administrator"
        self.assertFalse(await bot_names.enforce_learned_name(self.message()))
        self.role.status = "member"
        self.member.reputation_points = 30
        self.assertFalse(await bot_names.enforce_learned_name(self.message()))
        self.member.reputation_points = 0
        self.assertFalse(await bot_names.enforce_learned_name(self.message(name="Miras Smith")))
        self.penalty.assert_not_awaited()

    async def test_commands_cannot_bypass_learned_name_check(self):
        await self.store.learn("Miras")
        handler = AsyncMock()
        await RecentMessagesMiddleware()(handler, self.message().model_copy(update={"text": "!me"}), {})
        handler.assert_not_awaited()

    async def test_edits_and_duplicate_updates_do_not_add_penalties_or_logs(self):
        await self.store.learn("Miras")
        for _ in range(6):
            self.assertTrue(await bot_names.enforce_learned_name(self.message(1)))
        self.penalty.assert_awaited_once()
        self.bot.ban_chat_member.assert_not_awaited()
        self.bot.send_message.assert_awaited_once()

    async def test_disabled_autoban_continues_deleting_without_banning(self):
        await self.store.learn("Miras")
        with patch.object(config.spam, "autoban_enabled", False):
            for message_id in range(1, 7):
                self.assertTrue(await bot_names.enforce_learned_name(self.message(message_id)))
        self.bot.ban_chat_member.assert_not_awaited()

    async def test_logging_failure_does_not_allow_message_or_reputation_gain(self):
        await self.store.learn("Miras")
        self.bot.send_message.side_effect = TelegramNetworkError(
            method=SendMessage(chat_id=1, text="log"), message="offline",
        )
        with self.assertLogs("services.bot_names", level="ERROR"):
            self.assertTrue(await bot_names.enforce_learned_name(self.message()))
        self.penalty.assert_awaited_once_with(123, violations_count_spam=1, reputation_points=-5)
        self.bot.send_message.side_effect = None
        self.assertTrue(await bot_names.enforce_learned_name(self.message(2)))
        self.assertEqual(self.bot.send_message.await_count, 2)

    async def test_failed_atomic_write_does_not_publish_exemption(self):
        await self.store.learn("Miras")
        before = self.path.read_bytes()
        with patch.object(self.store, "_write", side_effect=OSError("disk full")):
            with self.assertLogs("handlers.callbacks", level="ERROR"):
                call = self.callback("notbot_-100123_123")
                await callbacks.callback_not_a_bot(call)
        call.message.edit_text.assert_not_awaited()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(await self.store.match(123, "Miras"), "Miras")

    async def test_corrupt_store_is_not_silently_overwritten(self):
        self.path.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            await self.store.learn("Miras")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken")

    async def test_cancelled_write_finishes_before_later_mutations(self):
        await self.store.learn("Miras")
        started, release = threading.Event(), threading.Event()
        actual_write = self.store._write

        def delayed_write(state):
            started.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release writer")
            actual_write(state)

        with patch.object(self.store, "_write", side_effect=delayed_write):
            task = asyncio.create_task(self.store.exempt(123))
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            later = asyncio.create_task(self.store.learn("Василиса"))
            await asyncio.sleep(0)
            self.assertFalse(later.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await later
        reloaded = bot_names.BotNameStore(self.path)
        self.assertIsNone(await reloaded.match(123, "Miras"))
        self.assertEqual(await reloaded.match(456, "Василиса"), "Василиса")

    async def test_failed_ban_at_threshold_is_retried_on_next_message(self):
        await self.store.learn("Miras")
        self.bot.ban_chat_member.side_effect = TelegramBadRequest(
            method=BanChatMember(chat_id=-100123, user_id=123), message="not enough rights",
        )
        for message_id in range(1, 5):
            await bot_names.enforce_learned_name(self.message(message_id))
        with self.assertLogs("services.bot_names", level="ERROR"):
            self.assertTrue(await bot_names.enforce_learned_name(self.message(5)))
        self.bot.ban_chat_member.side_effect = None
        self.assertTrue(await bot_names.enforce_learned_name(self.message(6)))
        self.assertEqual(self.bot.ban_chat_member.await_count, 2)

    async def test_failed_report_delivery_removes_snapshot_and_does_not_teach_name(self):
        self.assertTrue(await reports.begin_report(-100123, 10, 123, "Miras"))
        await reports.finish_report(-100123, 10, success=False)
        self.assertIsNone(await self.store.report_name(-100123, 10, 123))
        self.assertIsNone(await self.store.match(789, "Miras"))
        self.assertTrue(await reports.begin_report(-100123, 10, 123, "Miras"))
