import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import databases
import sqlalchemy

from db.models import Member
from handlers import group_events
from services import cache


class MemberUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = (Path(self.directory.name) / "test.sqlite").as_posix()
        self.engine = sqlalchemy.create_engine(f"sqlite:///{path}")
        self.addCleanup(self.engine.dispose)
        Member.ormar_config.metadata.create_all(self.engine)
        self.database = databases.Database(f"sqlite+aiosqlite:///{path}")
        self.original_database = Member.ormar_config.database
        Member.ormar_config.database = self.database
        self.addCleanup(setattr, Member.ormar_config, "database", self.original_database)
        await self.database.connect()
        cache._batch_lock = asyncio.Lock()
        cache._flush_lock = asyncio.Lock()
        cache._pending_updates.clear()
        cache.clear_all_caches()
        await Member.objects.create(user_id=123, messages_count=7, reputation_points=10)

    async def asyncTearDown(self):
        await self.database.disconnect()
        cache._pending_updates.clear()
        cache.clear_all_caches()

    async def test_absolute_edit_includes_prior_pending_deltas(self):
        await cache.queue_member_update(123, messages_count=5, reputation_points=-3)
        async with cache.edit_member(123) as member:
            self.assertEqual(member.reputation_points, 7)
            member.reputation_points = member.messages_count
        stored = await Member.objects.get(user_id=123)
        self.assertEqual((stored.messages_count, stored.reputation_points), (12, 12))
        self.assertEqual(await cache.flush_member_updates(), 0)

    async def test_owner_edit_waits_for_inflight_flush(self):
        started, release = asyncio.Event(), asyncio.Event()
        actual_apply = cache._apply_member_update

        async def delayed_apply(*args):
            started.set()
            await release.wait()
            await actual_apply(*args)

        await cache.queue_member_update(123, reputation_points=1)
        with patch.object(cache, "_apply_member_update", side_effect=delayed_apply):
            flush = asyncio.create_task(cache.flush_member_updates())
            await started.wait()

            async def owner_edit():
                async with cache.edit_member(123) as member:
                    member.reputation_points = 100

            edit = asyncio.create_task(owner_edit())
            await asyncio.sleep(0)
            self.assertFalse(edit.done())
            release.set()
            await asyncio.gather(flush, edit)
        self.assertEqual((await Member.objects.get(user_id=123)).reputation_points, 100)

    async def test_cache_refresh_waits_for_inflight_deltas(self):
        started, release = asyncio.Event(), asyncio.Event()
        actual_apply = cache._apply_member_update

        async def delayed_apply(*args):
            started.set()
            await release.wait()
            await actual_apply(*args)

        await cache.queue_member_update(123, reputation_points=1)
        with patch.object(cache, "_apply_member_update", side_effect=delayed_apply):
            flush = asyncio.create_task(cache.flush_member_updates())
            await started.wait()
            refresh = asyncio.create_task(cache.retrieve_or_create_member(123))
            await asyncio.sleep(0)
            self.assertFalse(refresh.done())
            release.set()
            await flush
            self.assertEqual((await refresh).reputation_points, 11)

    async def test_failed_flush_does_not_allow_absolute_edit_to_discard_deltas(self):
        await cache.queue_member_update(123, reputation_points=1)
        with patch.object(cache, "_apply_member_update", side_effect=RuntimeError("offline")):
            with self.assertLogs("services.cache", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    async with cache.edit_member(123):
                        self.fail("Edit must wait until prior deltas are persisted")
        self.assertEqual(cache._pending_updates[123], {"reputation_points": 1})
        self.assertEqual((await Member.objects.get(user_id=123)).reputation_points, 10)

    async def test_deltas_queued_during_absolute_edit_are_applied_after_it(self):
        async with cache.edit_member(123) as member:
            member.reputation_points = 100
            await cache.queue_member_update(123, reputation_points=2)
        self.assertEqual((await cache.retrieve_or_create_member(123)).reputation_points, 102)
        await cache.flush_member_updates()
        self.assertEqual((await Member.objects.get(user_id=123)).reputation_points, 102)

    async def test_new_deltas_during_prior_flush_do_not_block_owner_edit(self):
        actual_apply = cache._apply_member_update

        async def apply_with_new_message(*args):
            await cache.queue_member_update(123, reputation_points=2)
            await actual_apply(*args)

        await cache.queue_member_update(123, reputation_points=1)
        with patch.object(cache, "_apply_member_update", side_effect=apply_with_new_message):
            async with cache.edit_member(123) as member:
                self.assertEqual(member.reputation_points, 11)
                member.reputation_points = 100
        await cache.flush_member_updates()
        self.assertEqual((await Member.objects.get(user_id=123)).reputation_points, 102)

    async def test_owner_commands_use_serialized_edits(self):
        message = SimpleNamespace(
            text="!setlvl 20", reply=AsyncMock(),
            reply_to_message=SimpleNamespace(from_user=SimpleNamespace(id=123)),
        )
        await cache.queue_member_update(123, reputation_points=2)
        await group_events.on_setlvl(message)
        stored = await Member.objects.get(user_id=123)
        self.assertEqual((stored.messages_count, stored.reputation_points), (20, 32))
        await cache.queue_member_update(123, messages_count=3, reputation_points=-5)
        await group_events.on_rep_reset(message)
        stored = await Member.objects.get(user_id=123)
        self.assertEqual((stored.messages_count, stored.reputation_points), (23, 23))
