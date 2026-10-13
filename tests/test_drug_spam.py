import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.types import Chat, Message, User

from config import config
from handlers import group_events
from services import recent_messages, spam


class DrugSpamPatternTests(unittest.TestCase):
    def test_short_bait_and_weight_comments_match(self):
        for text in ("проба", "на пробу", "1гр", "0,5гр", "0.5 гр", "1 г",
                     "ПРОБА!!!", "на\nпробу", "проба 0,5гр", "1гр на пробу",
                     "прoбa", "про\u200bба", "🔥 на пробу 🔥", "１гр", "0.5gr"):
            with self.subTest(text=text):
                self.assertTrue(spam.is_drug_spam(text))

    def test_ordinary_sentences_and_substrings_do_not_match(self):
        for text in ("", "пробабилистика", "попробуй", "взял на пробу новый чай",
                     "проба пера", "1гр сахара", "добавь 0,5гр соли",
                     "проба микрофона", "1граница", "5 кг", "0,5", "проба <b>чай</b>"):
            with self.subTest(text=text):
                self.assertFalse(spam.is_drug_spam(text))


class DrugSpamModerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        recent_messages.clear_recent_messages()
        self.addCleanup(recent_messages.clear_recent_messages)
        self.bot = AsyncMock()
        self.member = SimpleNamespace(
            id=1, user_id=123, reputation_points=0, messages_count=0,
            violations_count_spam=0,
        )
        self.role = SimpleNamespace(status="member")

        async def update_member(user_id, **changes):
            for field, delta in changes.items():
                setattr(self.member, field, getattr(self.member, field, 0) + delta)

        self.update = AsyncMock(side_effect=update_member)
        self.log = AsyncMock()
        self.ml = Mock(return_value=False)
        for patcher in (
            patch.object(group_events, "retrieve_or_create_member", new=AsyncMock(return_value=self.member)),
            patch.object(group_events, "retrieve_tgmember", new=AsyncMock(return_value=self.role)),
            patch.object(group_events, "queue_member_update", self.update),
            patch.object(group_events, "write_log", self.log),
            patch.object(group_events, "ruspam_predict", self.ml),
            patch.object(group_events, "check_for_unwanted", new=AsyncMock(return_value=False)),
            patch.object(group_events, "check_for_profanity_all", return_value=(False, None)),
            patch.object(config.spam, "burst_enabled", False),
            patch.object(config.spam, "drug_spam_enabled", True),
            patch.object(config.spam, "drug_spam_rep_threshold", 30),
            patch.object(config.spam, "autoban_enabled", True),
            patch.object(config.spam, "autoban_threshold", 100),
            patch.object(config.spam, "autoban_rep_threshold", 100),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def message(self, text, message_id=10, caption=False):
        content = {"text": text}
        if caption:
            content = {"caption": text, "photo": [{
                "file_id": "photo", "file_unique_id": "photo", "width": 100, "height": 100,
            }]}
        return Message(
            message_id=message_id, date=datetime.now(timezone.utc),
            chat=Chat(id=-100123, type="supergroup", title="Group"),
            from_user=User(id=123, is_bot=False, first_name="Alex"), **content,
        ).as_(self.bot)

    async def test_low_rep_short_comments_deleted_logged_and_penalized_before_ml(self):
        for text in ("проба", "на пробу", "1гр", "0,5гр"):
            with self.subTest(text=text):
                self.bot.reset_mock()
                self.update.reset_mock()
                self.log.reset_mock()
                message = self.message(text)
                with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                    await group_events.on_user_message(message)
                    delete.assert_awaited_once()
                self.update.assert_awaited_once_with(123, violations_count_spam=1, reputation_points=-5)
                self.log.assert_awaited_once()
                self.assertIn(text, self.log.await_args.args[1])
                self.assertIn("пробы", self.log.await_args.args[2])
                self.ml.assert_not_called()
                self.bot.ban_chat_member.assert_not_awaited()

    async def test_ordinary_context_and_high_rep_users_are_not_caught(self):
        for text, reputation in (("проба пера", 0), ("1гр сахара", 0), ("на пробу", 30)):
            with self.subTest(text=text, reputation=reputation):
                self.member.reputation_points = reputation
                self.update.reset_mock()
                with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                    await group_events.on_user_message(self.message(text))
                    delete.assert_not_awaited()
                self.update.assert_awaited_once_with(123, messages_count=1, reputation_points=1)
        self.log.assert_not_awaited()

    async def test_admins_and_disabled_filter_are_exempt(self):
        self.role.status = "administrator"
        with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
            await group_events.on_user_message(self.message("проба"))
            delete.assert_not_awaited()
        self.update.assert_not_awaited()
        self.role.status = "member"
        with patch.object(config.spam, "drug_spam_enabled", False):
            with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                await group_events.on_user_message(self.message("0,5гр"))
                delete.assert_not_awaited()
        self.log.assert_not_awaited()

    async def test_edited_message_deleted_without_duplicate_penalty(self):
        with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
            await group_events.on_edited_user_message(self.message("проба"))
            delete.assert_awaited_once()
        self.update.assert_not_awaited()
        self.log.assert_awaited_once()
        self.bot.ban_chat_member.assert_not_awaited()

    async def test_matching_caption_is_checked_when_media_is_allowed(self):
        with patch.object(config.spam, "allow_media_threshold", 0):
            with patch.object(Message, "delete", new_callable=AsyncMock) as delete:
                await group_events.on_user_message(self.message("на пробу", caption=True))
                delete.assert_awaited_once()
        self.update.assert_awaited_once_with(123, violations_count_spam=1, reputation_points=-5)
        self.log.assert_awaited_once()

    async def test_repeat_offender_uses_existing_autoban_and_recent_cleanup(self):
        self.member.violations_count_spam = 99
        recent_messages.track_recent_message(-100123, 123, 9)
        with patch.object(Message, "delete", new_callable=AsyncMock):
            await group_events.on_user_message(self.message("1гр"))
        self.bot.ban_chat_member.assert_awaited_once_with(
            chat_id=-100123, user_id=123, revoke_messages=True,
        )
        self.bot.delete_messages.assert_awaited_once_with(-100123, [9])
        self.update.assert_awaited_once_with(123, violations_count_spam=1, reputation_points=-5)
