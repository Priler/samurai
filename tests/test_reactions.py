import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import databases
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine
from aiogram import Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import GetChatMember, RestrictChatMember
from aiogram.types import (
    Chat, ChatPermissions, Message, MessageReactionUpdated, ReactionTypeEmoji, Update, User,
)

from config import config
from db.models import Member, ReactionRestriction
from handlers import reactions as reaction_handlers
from middlewares.reactions import ReactionsMiddleware
from services import cache, reactions


class ReactionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = (Path(self.directory.name) / "test.sqlite").as_posix()
        self.engine = sqlalchemy.create_engine(f"sqlite:///{path}")
        self.addCleanup(self.engine.dispose)
        Member.ormar_config.metadata.create_all(self.engine)
        self.database = databases.Database(f"sqlite+aiosqlite:///{path}")
        for model in (Member, ReactionRestriction):
            original = model.ormar_config.database
            model.ormar_config.database = self.database
            self.addCleanup(setattr, model.ormar_config, "database", original)
        await self.database.connect()
        cache._batch_lock = asyncio.Lock()
        cache._flush_lock = asyncio.Lock()
        cache._pending_updates.clear()
        cache.clear_all_caches()
        reactions._retry_until = 0
        reactions._rescan = False
        reactions._dirty_users.clear()
        reactions._synced.clear()
        reactions._changed = asyncio.Event()
        self.bot = AsyncMock()
        self.bot.id = 999
        self.user = User(id=123, is_bot=False, first_name="Alex")
        self.defaults = ChatPermissions(
            can_send_messages=True, can_send_audios=True, can_send_documents=True,
            can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
            can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
            can_add_web_page_previews=True, can_react_to_messages=True,
            can_invite_users=True, can_pin_messages=False,
        )
        self.role = SimpleNamespace(status="member", user=self.user)
        self.bot.get_chat_member.side_effect = lambda *args: self.role
        self.bot.get_chat.return_value = SimpleNamespace(type="supergroup", permissions=self.defaults)

        async def restrict(**kwargs):
            self.role = SimpleNamespace(
                status="restricted", user=self.user, is_member=True,
                until_date=kwargs.get("until_date", 0),
                **kwargs["permissions"].model_dump(),
            )
            return True

        self.bot.restrict_chat_member.side_effect = restrict
        for patcher in (
            patch.object(type(config.groups), "is_main_group", return_value=True),
            patch.object(config.groups, "main", [-100123]),
            patch.object(config.reactions, "enabled", True),
            patch.object(config.reactions, "rep_threshold", 50),
            patch.object(reactions, "_bot", self.bot),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        await Member.objects.create(user_id=123, reputation_points=49, messages_count=49)

    async def asyncTearDown(self):
        await self.database.disconnect()
        cache._pending_updates.clear()
        cache.clear_all_caches()
        reactions._synced.clear()
        reactions._dirty_users.clear()
        reactions._retry_until = 0

    async def sync(self, chat_id=-100123, force=False):
        return await reactions.sync_member(self.bot, chat_id, 123, force=force)

    async def test_below_threshold_only_reactions_disabled_and_owned(self):
        self.assertTrue(await self.sync())
        kwargs = self.bot.restrict_chat_member.await_args.kwargs
        expected = self.defaults.model_copy(update={"can_react_to_messages": False})
        for name, value in expected.model_dump().items():
            if value is not None:
                self.assertEqual(getattr(kwargs["permissions"], name), value, name)
        self.assertTrue(kwargs["use_independent_chat_permissions"])
        self.assertEqual(kwargs["until_date"], 0)
        self.assertEqual(await ReactionRestriction.objects.count(), 1)

    async def test_threshold_crossings_include_unflushed_deltas(self):
        await self.sync()
        await cache.queue_member_update(123, reputation_points=1)
        self.assertIn(123, reactions._dirty_users)
        self.assertFalse(await self.sync())
        self.assertTrue(self.role.can_react_to_messages)
        self.assertEqual(await ReactionRestriction.objects.count(), 0)
        await cache.queue_member_update(123, reputation_points=-1)
        self.assertTrue(await self.sync())
        self.assertFalse(self.role.can_react_to_messages)
        self.assertEqual(self.bot.restrict_chat_member.await_count, 3)

    async def test_absolute_owner_edit_notifies_and_restores(self):
        await self.sync()
        reactions._dirty_users.clear()
        async with cache.edit_member(123) as member:
            member.reputation_points = 80
        self.assertIn(123, reactions._dirty_users)
        self.assertFalse(await self.sync())
        self.assertTrue(self.role.can_react_to_messages)

    async def test_ownership_survives_cache_reset_and_database_reload(self):
        await self.sync()
        reactions._synced.clear()
        cache.clear_all_caches()
        await Member.objects.filter(user_id=123).update(reputation_points=50)
        self.assertFalse(await self.sync())
        self.assertTrue(self.role.can_react_to_messages)
        self.assertEqual(await ReactionRestriction.objects.count(), 0)

    async def test_existing_manual_reaction_restriction_is_never_owned_or_lifted(self):
        self.role = SimpleNamespace(
            status="restricted", user=self.user, is_member=True, until_date=0,
            **self.defaults.model_copy(update={"can_react_to_messages": False}).model_dump(),
        )
        self.assertTrue(await self.sync())
        self.assertEqual(await ReactionRestriction.objects.count(), 0)
        await cache.queue_member_update(123, reputation_points=1)
        self.assertFalse(await self.sync())
        self.bot.restrict_chat_member.assert_not_awaited()

    async def test_unlock_during_mute_preserves_mute_and_deadline(self):
        await self.sync()
        deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        await reactions.restrict_member(
            self.bot, chat_id=-100123, user_id=123,
            permissions=ChatPermissions(can_send_messages=False, can_react_to_messages=False),
            until_date=deadline,
        )
        self.bot.restrict_chat_member.reset_mock()
        await cache.queue_member_update(123, reputation_points=10)
        self.assertFalse(await self.sync())
        self.bot.restrict_chat_member.assert_not_awaited()
        self.assertFalse(self.role.can_send_messages)
        self.assertEqual(self.role.until_date, deadline)
        self.assertEqual(await ReactionRestriction.objects.count(), 1)
        # Telegram lifts the timed mute; policy state is then safely retired.
        self.role = SimpleNamespace(status="member", user=self.user)
        self.assertFalse(await self.sync(force=True))
        self.assertEqual(await ReactionRestriction.objects.count(), 0)

    async def test_other_restrictions_and_deadline_preserved_when_unlocking_reactions(self):
        await self.sync()
        deadline = datetime.now(timezone.utc) + timedelta(hours=2)
        self.role.can_send_photos = False
        self.role.can_send_polls = False
        self.role.until_date = deadline
        await cache.queue_member_update(123, reputation_points=1)
        await self.sync()
        self.assertTrue(self.role.can_send_messages)
        self.assertTrue(self.role.can_react_to_messages)
        self.assertFalse(self.role.can_send_photos)
        self.assertFalse(self.role.can_send_polls)
        self.assertEqual(self.role.until_date, deadline)

    async def test_expiring_restriction_is_not_accidentally_made_permanent(self):
        self.role = SimpleNamespace(
            status="restricted", user=self.user, is_member=True,
            until_date=datetime.now(timezone.utc) + timedelta(seconds=20),
            **self.defaults.model_copy(update={"can_send_photos": False}).model_dump(),
        )
        self.assertTrue(await self.sync())
        self.bot.restrict_chat_member.assert_not_awaited()
        self.assertEqual(await ReactionRestriction.objects.count(), 0)
        self.role = SimpleNamespace(status="member", user=self.user)
        self.assertTrue(await self.sync(force=True))
        self.assertFalse(self.role.can_react_to_messages)

    async def test_disabling_policy_restores_only_owned_restrictions(self):
        await self.sync()
        with patch.object(config.reactions, "enabled", False):
            self.assertFalse(await self.sync())
        self.assertTrue(self.role.can_react_to_messages)
        self.assertEqual(await ReactionRestriction.objects.count(), 0)

    async def test_admins_nonmembers_other_chats_and_bots_are_skipped(self):
        for status in ("administrator", "creator", "left", "kicked"):
            with self.subTest(status=status):
                self.role = SimpleNamespace(status=status, user=self.user)
                self.assertFalse(await self.sync(force=True))
        with patch.object(type(config.groups), "is_main_group", return_value=False):
            self.assertFalse(await self.sync(force=True))
        self.role = SimpleNamespace(status="member", user=User(id=123, is_bot=True, first_name="Bot"))
        self.assertFalse(await self.sync(force=True))
        self.bot.restrict_chat_member.assert_not_awaited()

    async def test_independent_permission_defaults_preserved(self):
        self.defaults.can_react_to_messages = None
        self.defaults.can_pin_messages = True
        self.defaults.can_edit_tag = None
        self.defaults.can_manage_topics = None
        self.assertTrue(await self.sync())
        self.assertTrue(self.role.can_edit_tag)
        self.assertTrue(self.role.can_manage_topics)

    async def test_chatwide_reaction_disable_is_not_overridden_on_unlock(self):
        await self.sync()
        self.defaults.can_react_to_messages = False
        self.bot.restrict_chat_member.reset_mock()
        await cache.queue_member_update(123, reputation_points=1)
        await self.sync()
        self.bot.restrict_chat_member.assert_not_awaited()
        self.assertEqual(await ReactionRestriction.objects.count(), 0)

    async def test_concurrent_updates_and_repeated_messages_do_not_repeat_api_changes(self):
        await asyncio.gather(*(self.sync() for _ in range(5)))
        self.bot.restrict_chat_member.assert_awaited_once()
        self.bot.get_chat_member.assert_awaited_once()
        self.assertEqual(await ReactionRestriction.objects.count(), 1)

    async def test_failed_permission_change_is_logged_and_retryable(self):
        actual = self.bot.restrict_chat_member.side_effect
        self.bot.restrict_chat_member.side_effect = TelegramBadRequest(
            method=RestrictChatMember(chat_id=-100123, user_id=123, permissions=self.defaults),
            message="not enough rights",
        )
        with self.assertLogs("services.reactions", level="ERROR"):
            self.assertFalse(await self.sync())
        self.assertEqual(await ReactionRestriction.objects.count(), 0)
        self.bot.restrict_chat_member.side_effect = actual
        self.assertTrue(await self.sync())
        self.assertEqual(await ReactionRestriction.objects.count(), 1)

    async def test_invalid_participant_lookup_is_quiet_and_preserves_policy_ownership(self):
        await self.sync()
        self.bot.restrict_chat_member.reset_mock()
        actual = self.bot.get_chat_member.side_effect
        self.bot.get_chat_member.side_effect = TelegramBadRequest(
            method=GetChatMember(chat_id=-100123, user_id=123),
            message="Bad Request: PARTICIPANT_ID_INVALID",
        )
        with self.assertNoLogs("services.reactions", level="WARNING"):
            self.assertFalse(await self.sync(force=True))
        self.bot.restrict_chat_member.assert_not_awaited()
        self.assertEqual(await ReactionRestriction.objects.count(), 1)
        # An unavailable lookup does not permanently exempt the user or strand
        # a restriction when lookup starts working again.
        self.bot.get_chat_member.side_effect = actual
        await cache.queue_member_update(123, reputation_points=1)
        self.assertFalse(await self.sync(force=True))
        self.assertTrue(self.role.can_react_to_messages)
        self.assertEqual(await ReactionRestriction.objects.count(), 0)

    async def test_invalid_lookup_does_not_hide_other_membership_errors(self):
        for description in ("chat not found", "not enough rights", "CHAT_ADMIN_REQUIRED"):
            with self.subTest(description=description):
                self.bot.get_chat_member.side_effect = TelegramBadRequest(
                    method=GetChatMember(chat_id=-100123, user_id=123), message=description,
                )
                with self.assertLogs("services.reactions", level="ERROR"):
                    self.assertFalse(await self.sync(force=True))

    async def test_reaction_from_invalid_participant_is_quietly_skipped(self):
        self.bot.get_chat_member.side_effect = TelegramBadRequest(
            method=GetChatMember(chat_id=-100123, user_id=123),
            message="Bad Request: PARTICIPANT_ID_INVALID",
        )
        with self.assertNoLogs("services.reactions", level="WARNING"), \
             self.assertNoLogs("handlers.reactions", level="WARNING"):
            await reaction_handlers.on_reaction(self.reaction())
        self.bot.restrict_chat_member.assert_not_awaited()
        self.bot.delete_message_reaction.assert_not_awaited()

    async def test_initial_scan_continues_after_invalid_participant(self):
        await Member.objects.create(user_id=456, reputation_points=0)

        async def lookup(chat_id, user_id):
            if user_id == 123:
                raise TelegramBadRequest(
                    method=GetChatMember(chat_id=chat_id, user_id=user_id),
                    message="Bad Request: PARTICIPANT_ID_INVALID",
                )
            return SimpleNamespace(status="member", user=User(id=456, is_bot=False, first_name="Other"))

        self.bot.get_chat_member.side_effect = lookup
        with self.assertNoLogs("services.reactions", level="WARNING"), \
             patch.object(reactions.asyncio, "sleep", new_callable=AsyncMock):
            await reactions.reconcile_known_members(self.bot)
        self.bot.restrict_chat_member.assert_awaited_once()
        self.assertEqual(self.bot.restrict_chat_member.await_args.kwargs["user_id"], 456)
        self.assertEqual(await ReactionRestriction.objects.count(), 1)

    async def test_rate_limit_is_deferred_without_breaking_moderation(self):
        self.bot.get_chat_member.side_effect = TelegramRetryAfter(
            method=RestrictChatMember(chat_id=-100123, user_id=123, permissions=self.defaults),
            message="retry later", retry_after=10,
        )
        with self.assertLogs("services.reactions", level="WARNING"):
            self.assertFalse(await self.sync())
        self.assertIn(123, reactions._dirty_users)
        self.assertFalse(await self.sync())
        self.bot.get_chat_member.assert_awaited_once()

    def reaction(self, *, user=True, added=True, chat_type="supergroup"):
        return MessageReactionUpdated(
            chat=Chat(id=-100123, type=chat_type), message_id=20,
            user=self.user if user else None,
            actor_chat=None if user else Chat(id=-100456, type="channel"),
            date=datetime.now(timezone.utc), old_reaction=[],
            new_reaction=[ReactionTypeEmoji(emoji="👍")] if added else [],
        ).as_(self.bot)

    async def test_reaction_handler_via_dispatcher_removes_and_restricts(self):
        dispatcher = Dispatcher()
        router = Router()
        router.message_reaction.register(reaction_handlers.on_reaction)
        dispatcher.include_router(router)
        self.assertIn("message_reaction", dispatcher.resolve_used_update_types())
        await dispatcher.feed_update(self.bot, Update(update_id=1, message_reaction=self.reaction()))
        self.bot.delete_message_reaction.assert_awaited_once_with(
            chat_id=-100123, message_id=20, user_id=123,
        )
        self.assertFalse(self.role.can_react_to_messages)

    async def test_reaction_removed_even_if_future_permission_change_fails(self):
        self.bot.restrict_chat_member.side_effect = TelegramBadRequest(
            method=RestrictChatMember(chat_id=-100123, user_id=123, permissions=self.defaults),
            message="not enough rights",
        )
        with self.assertLogs("services.reactions", level="ERROR"):
            await reaction_handlers.on_reaction(self.reaction())
        self.bot.delete_message_reaction.assert_awaited_once()

    async def test_reaction_cleanup_failure_is_logged(self):
        self.bot.delete_message_reaction.side_effect = TelegramNetworkError(
            method=RestrictChatMember(chat_id=-100123, user_id=123, permissions=self.defaults), message="offline",
        )
        with self.assertLogs("handlers.reactions", level="ERROR"):
            await reaction_handlers.on_reaction(self.reaction())
        self.assertFalse(self.role.can_react_to_messages)

    async def test_high_rep_admin_anonymous_removals_and_channels_are_not_deleted(self):
        for event in (self.reaction(user=False), self.reaction(added=False), self.reaction(chat_type="channel")):
            await reaction_handlers.on_reaction(event)
        self.role.status = "administrator"
        await reaction_handlers.on_reaction(self.reaction())
        self.role.status = "member"
        await cache.queue_member_update(123, reputation_points=1)
        await reaction_handlers.on_reaction(self.reaction())
        self.bot.delete_message_reaction.assert_not_awaited()

    async def test_member_update_applies_policy_for_new_arrival(self):
        event = SimpleNamespace(
            bot=self.bot, chat=Chat(id=-100123, type="supergroup"),
            new_chat_member=SimpleNamespace(user=self.user),
        )
        await reaction_handlers.on_member_update(event)
        self.assertFalse(self.role.can_react_to_messages)

    async def test_outer_middleware_tracks_reputation_change_in_handler(self):
        message = Message(
            message_id=1, date=datetime.now(timezone.utc), text="hello",
            chat=Chat(id=-100123, type="supergroup"), from_user=self.user,
        ).as_(self.bot)

        async def handler(event, data):
            await cache.queue_member_update(123, reputation_points=1)
            return "handled"

        self.assertEqual(await ReactionsMiddleware()(handler, message, {}), "handled")
        self.assertTrue(self.role.can_react_to_messages)
        self.assertEqual(self.bot.restrict_chat_member.await_count, 2)

    async def test_initial_reconciliation_checks_known_members_in_configured_chats(self):
        with patch.object(reactions.asyncio, "sleep", new_callable=AsyncMock):
            await reactions.reconcile_known_members(self.bot)
        self.assertFalse(self.role.can_react_to_messages)
        self.assertEqual(await ReactionRestriction.objects.count(), 1)

    async def test_disabled_reconciliation_only_visits_owned_restrictions(self):
        await self.sync()
        await Member.objects.create(user_id=456, reputation_points=0)
        self.bot.get_chat_member.reset_mock()
        with patch.object(config.reactions, "enabled", False), \
             patch.object(reactions.asyncio, "sleep", new_callable=AsyncMock):
            await reactions.reconcile_known_members(self.bot)
            self.bot.get_chat_member.assert_awaited_once_with(-100123, 123)
            self.assertTrue(self.role.can_react_to_messages)
            self.assertEqual(await ReactionRestriction.objects.count(), 0)
            await reactions.reconcile_known_members(self.bot)
            self.bot.get_chat_member.assert_awaited_once()

    async def test_worker_processes_reputation_change_after_initial_scan(self):
        started = asyncio.Event()
        async def scan(bot):
            started.set()
        with patch.object(reactions, "reconcile_known_members", side_effect=scan):
            task = asyncio.create_task(reactions._run(self.bot))
            try:
                await started.wait()
                await self.sync()
                await cache.queue_member_update(123, reputation_points=1)
                for _ in range(100):
                    if self.role.can_react_to_messages:
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(self.role.can_react_to_messages)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

    async def test_start_creates_only_additive_table_and_stop_cancels_worker(self):
        ReactionRestriction.ormar_config.table.drop(self.engine)
        path = (Path(self.directory.name) / "test.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        started = asyncio.Event()

        async def worker(bot):
            started.set()
            await asyncio.Future()

        try:
            with patch.object(reactions, "ormar_config", SimpleNamespace(engine=engine)), \
                 patch.object(reactions, "_run", side_effect=worker):
                await reactions.start(self.bot)
                await started.wait()
                task = reactions._task
                await reactions.start(self.bot)
                self.assertIs(reactions._task, task)
                self.assertEqual(await ReactionRestriction.objects.count(), 0)
                self.assertEqual((await Member.objects.get(user_id=123)).reputation_points, 49)
                await reactions.stop()
                self.assertTrue(task.cancelled())
                self.assertFalse(reactions.is_running())
        finally:
            await reactions.stop()
            await engine.dispose()

    async def test_moderator_mute_waits_for_inflight_policy_write(self):
        started, release = asyncio.Event(), asyncio.Event()
        actual = self.bot.restrict_chat_member.side_effect

        async def delayed(**kwargs):
            started.set()
            await release.wait()
            return await actual(**kwargs)

        self.bot.restrict_chat_member.side_effect = delayed
        policy = asyncio.create_task(self.sync())
        await started.wait()
        mute = asyncio.create_task(reactions.restrict_member(
            self.bot, chat_id=-100123, user_id=123,
            permissions=ChatPermissions(can_send_messages=False, can_react_to_messages=False),
            until_date=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        try:
            await asyncio.sleep(0)
            self.assertFalse(mute.done())
        finally:
            release.set()
            await asyncio.gather(policy, mute)
        self.assertFalse(self.role.can_send_messages)
        self.assertFalse(self.role.can_react_to_messages)

    async def test_ban_waits_for_inflight_policy_and_is_not_overwritten(self):
        started, release = asyncio.Event(), asyncio.Event()
        actual = self.bot.restrict_chat_member.side_effect

        async def delayed(**kwargs):
            started.set()
            await release.wait()
            return await actual(**kwargs)

        async def banned(**kwargs):
            self.role = SimpleNamespace(status="kicked", user=self.user)
            return True

        self.bot.restrict_chat_member.side_effect = delayed
        self.bot.ban_chat_member.side_effect = banned
        policy = asyncio.create_task(self.sync())
        await started.wait()
        ban = asyncio.create_task(reactions.ban_member(self.bot, chat_id=-100123, user_id=123))
        try:
            await asyncio.sleep(0)
            self.assertFalse(ban.done())
        finally:
            release.set()
            await asyncio.gather(policy, ban)
        self.assertEqual(self.role.status, "kicked")
        self.assertFalse(await self.sync())
        self.assertEqual(self.role.status, "kicked")
        self.assertEqual(await ReactionRestriction.objects.count(), 0)
