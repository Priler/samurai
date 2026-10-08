import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import BanChatMember, DeleteMessage

from handlers import callbacks
from config import config
from services import recent_messages, reports


class ReportActionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        recent_messages.clear_recent_messages()
        self.addCleanup(recent_messages.clear_recent_messages)
        reports._state_lock = asyncio.Lock()
        reports._recent_reports.clear()
        reports._pending_reports.clear()
        reports._processing_report_actions.clear()
        reports._resolved_reports.clear()
        reports._active_report_by_user.clear()
        reports._report_users.clear()
        self.reward = AsyncMock()
        patcher = patch.object(callbacks, "queue_member_update", self.reward)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, action="rdelban"):
        return SimpleNamespace(
            data=f"{action}_-100123_10_123_456_11",
            from_user=SimpleNamespace(id=config.bot.owner),
            bot=AsyncMock(), answer=AsyncMock(),
            message=SimpleNamespace(html_text="report", edit_text=AsyncMock()),
        )

    async def test_failed_ban_remains_tracked_and_can_be_retried(self):
        recent_messages.track_recent_message(-100123, 123, 9)
        await reports.begin_report(-100123, 10, 123)
        await reports.finish_report(-100123, 10, success=True)
        call = self.call()
        call.bot.ban_chat_member.side_effect = TelegramNetworkError(
            method=BanChatMember(chat_id=-100123, user_id=123), message="offline",
        )
        with self.assertRaises(TelegramNetworkError):
            await callbacks.callback_report_delete_and_ban(call)
        self.assertTrue(reports.is_already_reported(-100123, 10))
        self.assertIn(123, reports._active_report_by_user)
        self.reward.assert_not_awaited()
        call.bot.delete_messages.assert_not_awaited()
        call.bot.ban_chat_member.side_effect = None
        await callbacks.callback_report_delete_and_ban(call)
        call.bot.delete_messages.assert_awaited_once_with(-100123, [9])
        self.reward.assert_awaited_once_with(456, reputation_points=20)
        self.assertFalse(reports.is_already_reported(-100123, 10))
        self.assertNotIn(123, reports._active_report_by_user)
        self.assertFalse(await reports.claim_report_action(-100123, 10))

    async def test_report_ban_cleans_only_target_user_in_reported_chat(self):
        for message_id in (9, 10, 12):
            recent_messages.track_recent_message(-100123, 123, message_id)
        recent_messages.track_recent_message(-100123, 789, 13)
        recent_messages.track_recent_message(-100456, 123, 20)
        call = self.call()

        await callbacks.callback_report_delete_and_ban(call)

        call.bot.delete_message.assert_awaited_once_with(-100123, 10)
        call.bot.ban_chat_member.assert_awaited_once_with(
            chat_id=-100123, user_id=123, revoke_messages=True,
        )
        call.bot.delete_messages.assert_awaited_once_with(-100123, [9, 10, 12])
        self.assertNotIn((-100123, 123), recent_messages._recent_messages)
        self.assertIn((-100123, 789), recent_messages._recent_messages)
        self.assertIn((-100456, 123), recent_messages._recent_messages)
        self.reward.assert_awaited_once_with(456, reputation_points=20)

    async def test_concurrent_clicks_do_not_duplicate_actions_or_rewards(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_ban(**kwargs):
            started.set()
            await release.wait()

        first, second = self.call(), self.call()
        first.bot.ban_chat_member.side_effect = delayed_ban
        task = asyncio.create_task(callbacks.callback_report_delete_and_ban(first))
        await started.wait()
        await callbacks.callback_report_delete_and_ban(second)
        second.bot.ban_chat_member.assert_not_awaited()
        release.set()
        await task
        self.reward.assert_awaited_once()

    async def test_cancellation_releases_claim(self):
        started = asyncio.Event()

        async def cancelled_ban(**kwargs):
            started.set()
            await asyncio.Future()

        call = self.call()
        call.bot.ban_chat_member.side_effect = cancelled_ban
        task = asyncio.create_task(callbacks.callback_report_delete_and_ban(call))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(await reports.claim_report_action(-100123, 10))

    async def test_ui_failure_after_success_does_not_repeat_reward(self):
        call = self.call()
        call.message.edit_text.side_effect = TelegramNetworkError(
            method=BanChatMember(chat_id=-100123, user_id=123), message="offline",
        )
        with self.assertRaises(TelegramNetworkError):
            await callbacks.callback_report_delete_and_ban(call)
        await callbacks.callback_report_delete_and_ban(call)
        self.reward.assert_awaited_once()
        call.bot.ban_chat_member.assert_awaited_once()

    async def test_delete_permission_failure_is_retryable(self):
        call = self.call("rdel")
        call.data = "rdel_-100123_10_456_11"
        call.bot.delete_message.side_effect = TelegramBadRequest(
            method=DeleteMessage(chat_id=-100123, message_id=10),
            message="not enough rights to delete messages",
        )
        with self.assertRaises(TelegramBadRequest):
            await callbacks.callback_report_delete(call)
        self.reward.assert_not_awaited()
        self.assertTrue(await reports.claim_report_action(-100123, 10))

    async def test_already_deleted_message_can_still_be_banned(self):
        call = self.call()
        call.bot.delete_message.side_effect = TelegramBadRequest(
            method=DeleteMessage(chat_id=-100123, message_id=10),
            message="message to delete not found",
        )
        await callbacks.callback_report_delete_and_ban(call)
        call.bot.ban_chat_member.assert_awaited_once()
        self.reward.assert_awaited_once()

    async def test_malformed_payload_releases_claim(self):
        call = self.call()
        call.data = "rdelban_-100123_10_invalid_456_11"
        with self.assertLogs("handlers.callbacks", level="WARNING"):
            await callbacks.callback_report_delete_and_ban(call)
        self.assertTrue(await reports.claim_report_action(-100123, 10))

    async def test_all_report_actions_commit_after_success(self):
        cases = (
            ("rdel", callbacks.callback_report_delete),
            ("rdelban", callbacks.callback_report_delete_and_ban),
            ("rmute", callbacks.callback_report_delete_and_mute_24h),
            ("rmute2", callbacks.callback_report_delete_and_mute_7d),
            ("rdismiss", callbacks.callback_report_dismiss),
            ("rdismiss2", callbacks.callback_report_dismiss_mute_reporter_1d),
            ("rdismiss3", callbacks.callback_report_dismiss_mute_reporter_7d),
            ("rdismiss4", callbacks.callback_report_dismiss_ban_reporter),
        )
        for action, handler in cases:
            with self.subTest(action=action):
                reports._resolved_reports.clear()
                call = self.call(action)
                if action == "rdel":
                    call.data = "rdel_-100123_10_456_11"
                await handler(call)
                self.assertFalse(await reports.claim_report_action(-100123, 10))

    async def test_failed_restrictions_and_reporter_ban_allow_retry(self):
        cases = (
            ("rmute", callbacks.callback_report_delete_and_mute_24h, "restrict_chat_member"),
            ("rmute2", callbacks.callback_report_delete_and_mute_7d, "restrict_chat_member"),
            ("rdismiss2", callbacks.callback_report_dismiss_mute_reporter_1d, "restrict_chat_member"),
            ("rdismiss3", callbacks.callback_report_dismiss_mute_reporter_7d, "restrict_chat_member"),
            ("rdismiss4", callbacks.callback_report_dismiss_ban_reporter, "ban_chat_member"),
        )
        for action, handler, method in cases:
            with self.subTest(action=action):
                reports._processing_report_actions.clear()
                self.reward.reset_mock()
                call = self.call(action)
                getattr(call.bot, method).side_effect = TelegramNetworkError(
                    method=BanChatMember(chat_id=-100123, user_id=123), message="offline",
                )
                with self.assertRaises(TelegramNetworkError):
                    await handler(call)
                self.reward.assert_not_awaited()
                self.assertTrue(await reports.claim_report_action(-100123, 10))
