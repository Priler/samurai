import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, PhotoSize, Update

from handlers import group_events


class ChannelCommentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.object(group_events, "_random", return_value="Comment")
        patcher.start()
        self.addCleanup(patcher.stop)
        group_events._commented_albums.clear()
        self.addCleanup(group_events._commented_albums.clear)

    def message(self, album="album-1", chat_id=-100123):
        return SimpleNamespace(
            media_group_id=album, chat=SimpleNamespace(id=chat_id), reply=AsyncMock(),
        )

    async def test_five_album_photos_through_dispatcher_receive_one_comment(self):
        dispatcher = Dispatcher()
        router = Router()
        router.message.register(group_events.on_channel_post, F.is_automatic_forward)
        dispatcher.include_router(router)
        bot = AsyncMock()
        bot.id = 999
        with patch.object(Message, "reply", new_callable=AsyncMock) as reply:
            for message_id in range(1, 6):
                message = Message(
                    message_id=message_id, date=datetime.now(timezone.utc),
                    chat=Chat(id=-100123, type="supergroup"),
                    is_automatic_forward=True, media_group_id="album-1",
                    photo=[PhotoSize(file_id=f"photo-{message_id}",
                                     file_unique_id=f"unique-{message_id}", width=100, height=100)],
                )
                await dispatcher.feed_update(bot, Update(update_id=message_id, message=message))
            reply.assert_awaited_once_with("Comment")

    async def test_concurrent_album_updates_do_not_duplicate_pending_reply(self):
        started, release = asyncio.Event(), asyncio.Event()
        first = self.message()

        async def delayed_reply(*args):
            started.set()
            await release.wait()

        first.reply.side_effect = delayed_reply
        task = asyncio.create_task(group_events.on_channel_post(first))
        try:
            await started.wait()
            rest = [self.message() for _ in range(4)]
            await asyncio.gather(*(group_events.on_channel_post(message) for message in rest))
            for message in rest:
                message.reply.assert_not_awaited()
        finally:
            release.set()
            await task
        first.reply.assert_awaited_once_with("Comment")

    async def test_separate_albums_and_chats_each_receive_comment(self):
        messages = [self.message(), self.message("album-2"), self.message(chat_id=-100456)]
        for message in messages:
            await group_events.on_channel_post(message)
            message.reply.assert_awaited_once_with("Comment")

    async def test_single_posts_each_receive_comment(self):
        for _ in range(3):
            message = self.message(album=None)
            await group_events.on_channel_post(message)
            message.reply.assert_awaited_once_with("Comment")

    async def test_failed_reply_allows_later_album_item_to_retry(self):
        first = self.message()
        first.reply.side_effect = TelegramBadRequest(
            method=SendMessage(chat_id=-100123, text="Comment"), message="message to reply not found",
        )
        with self.assertLogs(group_events.__name__, level="WARNING"):
            await group_events.on_channel_post(first)
        second, third = self.message(), self.message()
        await group_events.on_channel_post(second)
        await group_events.on_channel_post(third)
        second.reply.assert_awaited_once_with("Comment")
        third.reply.assert_not_awaited()

    async def test_cancelled_reply_does_not_block_remaining_album_items(self):
        started = asyncio.Event()
        first = self.message()

        async def cancelled_reply(*args):
            started.set()
            await asyncio.Future()

        first.reply.side_effect = cancelled_reply
        task = asyncio.create_task(group_events.on_channel_post(first))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        second, third = self.message(), self.message()
        await group_events.on_channel_post(second)
        await group_events.on_channel_post(third)
        second.reply.assert_awaited_once_with("Comment")
        third.reply.assert_not_awaited()
