"""
Callback query handlers for inline buttons.

Note: callback_data format for reports:
- rdel_{chat_id}_{msg_id}_{reporter_id}_{bot_reply_id}
- rdelban_{chat_id}_{msg_id}_{user_id}_{reporter_id}_{bot_reply_id}
- etc.
"""
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from functools import wraps

from aiogram import Router, F
from aiogram.types import CallbackQuery, ChatPermissions
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from config import config
from db.models import Member, Spam
from services.reports import claim_report_action, finish_report_action
from services.cache import queue_member_update, invalidate_nsfw_cache, mark_nsfw_profile_checked
from services.recent_messages import ban_and_cleanup
from services import bot_names
from utils import get_string, _random, MemberStatus
from handlers.personal_actions import pending_messages

router = Router(name="callbacks")
logger = logging.getLogger(__name__)


def safe_callback(func):
    """Catch malformed callback data so bad payloads don't crash handlers."""
    @wraps(func)
    async def wrapper(call: CallbackQuery) -> None:
        report_key = None
        try:
            report_prefixes = (
                "rdel_", "rdelban_", "rmute_", "rmute2_",
                "rdismiss_", "rdismiss2_", "rdismiss3_", "rdismiss4_",
            )
            if call.data and call.data.startswith(report_prefixes):
                parts = call.data.split("_")
                if not await claim_report_action(int(parts[1]), int(parts[2])):
                    await call.answer("Уже обработано", show_alert=True)
                    return
                report_key = (int(parts[1]), int(parts[2]))
            return await func(call)
        except (ValueError, IndexError) as e:
            logger.warning(f"Malformed callback data in {func.__name__}: {call.data!r} ({e})")
            await call.answer("❌ Ошибка данных", show_alert=True)
        finally:
            if report_key is not None:
                # Committed actions stay resolved
                await finish_report_action(*report_key, success=False)
    return wrapper


### MSG SEND CALLBACKS (owner broadcast) ###

@router.callback_query(F.data.startswith("msg_"))
@safe_callback
async def callback_msg_send(call: CallbackQuery) -> None:
    """Handle message send callbacks."""
    # verify owner
    if call.from_user.id != config.bot.owner:
        await call.answer("⛔ Только для владельца", show_alert=True)
        return
    
    parts = call.data.split("_")
    if len(parts) < 3:
        await call.answer("❌ Ошибка данных", show_alert=True)
        return
    
    msg_id = parts[1]
    target = "_".join(parts[2:])  # Handle negative chat IDs like -100123
    
    # get stored message
    if msg_id not in pending_messages:
        await call.message.edit_text("❌ Сообщение устарело. Отправьте команду заново.")
        await call.answer()
        return
    
    text, _ = pending_messages[msg_id]
    
    if target == "cancel":
        del pending_messages[msg_id]
        await call.message.edit_text("❌ Отменено.")
        await call.answer()
        return
    
    if target == "all":
        # send to all chats
        sent = 0
        failed = 0
        for chat_id in config.groups.main:
            try:
                await call.bot.send_message(chat_id, text)
                sent += 1
            except Exception:
                failed += 1
        
        del pending_messages[msg_id]
        await call.message.edit_text(
            f"✅ <b>Отправлено во все чаты</b>\n\n"
            f"Успешно: {sent}\n"
            f"Ошибок: {failed}"
        )
        await call.answer("Отправлено!")
    else:
        # send to specific chat
        try:
            chat_id = int(target)
            await call.bot.send_message(chat_id, text)
            
            # get chat name for confirmation
            try:
                chat = await call.bot.get_chat(chat_id)
                chat_name = chat.title or f"Chat {chat_id}"
            except Exception:
                chat_name = f"Chat {chat_id}"
            
            del pending_messages[msg_id]
            await call.message.edit_text(f"✅ <b>Отправлено в:</b> {chat_name}")
            await call.answer("Отправлено!")
        except ValueError:
            await call.answer("❌ Неверный ID чата", show_alert=True)
        except Exception as e:
            await call.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)


### REPORT CALLBACKS (new format with rewards) ###

async def _update_bot_reply(bot, chat_id: int, bot_reply_id: int) -> None:
    """Update bot's reply message in the original chat with completion message."""
    with suppress(TelegramBadRequest):
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_reply_id,
            text=_random("report-completed"),
            parse_mode="HTML"
        )


async def _reward_reporter(reporter_id: int, points: int) -> None:
    """Reward reporter with reputation points."""
    await queue_member_update(reporter_id, reputation_points=points)


async def _delete_report_message(bot, chat_id: int, message_id: int) -> None:
    """An already deleted message is harmless; other failures must be retried."""
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as exc:
        if "message to delete not found" not in str(exc).lower():
            raise


async def _is_chat_moderator(call: CallbackQuery, chat_id: int) -> bool:
    if call.from_user.id == config.bot.owner:
        return True
    try:
        role = await call.bot.get_chat_member(chat_id, call.from_user.id)
        return role.status in MemberStatus.admin_statuses()
    except TelegramAPIError:
        logger.exception("Failed to check moderator permissions in chat %s", chat_id)
        return False


@router.callback_query(F.data.startswith("rdel_"))
@safe_callback
async def callback_report_delete(call: CallbackQuery) -> None:
    """Delete reported message only. Reward rep."""
    # format: rdel_chatId_msgId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    reporter_id = int(parts[3])
    bot_reply_id = int(parts[4])

    await _delete_report_message(call.bot, chat_id, message_id)
    
    # reward reporter (+10 for delete)
    await _reward_reporter(reporter_id, 10)
    await finish_report_action(chat_id, message_id, success=True)
    
    # update bot's reply in original chat
    await _update_bot_reply(call.bot, chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("rdelban_"))
@safe_callback
async def callback_report_delete_and_ban(call: CallbackQuery) -> None:
    """Delete message and ban user. Reward more rep."""
    # format: rdelban_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])
    reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    if not await _is_chat_moderator(call, chat_id):
        await call.answer("⛔ Только для администратора чата", show_alert=True)
        return
    reported_name = None
    try:
        reported_name = await bot_names.store.report_name(chat_id, message_id, user_id)
        if reported_name is None:  # Reports posted before name snapshots existed
            target = await call.bot.get_chat_member(chat_id, user_id)
            name = target.user.full_name
            if isinstance(name, str):
                reported_name = name
    except (TelegramAPIError, OSError, ValueError):
        logger.exception("Could not retrieve the reported user's display name")

    await _delete_report_message(call.bot, chat_id, message_id)

    await call.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)

    name_saved = reported_name is not None
    if reported_name is not None:
        try:
            await bot_names.store.learn(reported_name)
        except (OSError, ValueError):
            name_saved = False
            logger.exception("Report ban succeeded but learning its name failed")

    # reward reporter (+20 for ban)
    await _reward_reporter(reporter_id, 20)
    await finish_report_action(chat_id, message_id, success=True)
    
    # update bot's reply in original chat
    await _update_bot_reply(call.bot, chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted_banned")
        + ("\n⚠️ Имя не удалось сохранить." if not name_saved else "")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("notbot_"))
@safe_callback
async def callback_not_a_bot(call: CallbackQuery) -> None:
    """Permanently exempt this Telegram user from learned-name checks."""
    parts = call.data.split("_")
    chat_id, user_id = int(parts[1]), int(parts[2])
    if not await _is_chat_moderator(call, chat_id):
        await call.answer("⛔ Только для администратора чата", show_alert=True)
        return
    try:
        await bot_names.store.exempt(user_id)
    except (OSError, ValueError):
        logger.exception("Failed to save learned-name exemption for user %s", user_id)
        await call.answer("❌ Не удалось сохранить исключение. Повторите.", show_alert=True)
        return
    await call.message.edit_text(call.message.html_text + "\n\n✅ Пользователь исключён из проверки имён.")
    await call.answer("Исключение сохранено")


@router.callback_query(F.data.startswith("rmute_"))
@safe_callback
async def callback_report_delete_and_mute_24h(call: CallbackQuery) -> None:
    """Delete message and mute user for 24 hours. Reward rep."""
    # format: rmute_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])
    reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    await _delete_report_message(call.bot, chat_id, message_id)

    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(hours=24)
    )

    # reward reporter (+10 for mute)
    await _reward_reporter(reporter_id, 10)
    await finish_report_action(chat_id, message_id, success=True)
    
    # update bot's reply in original chat
    await _update_bot_reply(call.bot, chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted_readonly")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("rmute2_"))
@safe_callback
async def callback_report_delete_and_mute_7d(call: CallbackQuery) -> None:
    """Delete message and mute user for 7 days. Reward some more rep."""
    # format: rmute2_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])
    reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    await _delete_report_message(call.bot, chat_id, message_id)

    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(days=7)
    )

    # reward reporter (+15 for 7d mute)
    await _reward_reporter(reporter_id, 15)
    await finish_report_action(chat_id, message_id, success=True)
    
    # update bot's reply in original chat
    await _update_bot_reply(call.bot, chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted_readonly2")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("rdismiss_"))
@safe_callback
async def callback_report_dismiss(call: CallbackQuery) -> None:
    """Dismiss report (false alarm). No rep reward."""
    # format: rdismiss_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    # user_id = int(parts[3])  # reported user - not used here
    # reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    await finish_report_action(chat_id, message_id, success=True)
    
    # delete bot's reply in original chat (false alarm, no need to show completion)
    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_dismissed")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("rdismiss2_"))
@safe_callback
async def callback_report_dismiss_mute_reporter_1d(call: CallbackQuery) -> None:
    """Dismiss and mute reporter for 1 day."""
    # format: rdismiss2_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    # user_id = int(parts[3])  # reported user
    reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    # mute reporter
    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=reporter_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(days=1)
    )
    
    # punish reporter
    await queue_member_update(reporter_id, reputation_points=-10)
    await finish_report_action(chat_id, message_id, success=True)
    
    # delete bot's reply
    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted_dismissed2")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("rdismiss3_"))
@safe_callback
async def callback_report_dismiss_mute_reporter_7d(call: CallbackQuery) -> None:
    """Dismiss and mute reporter for 7 days."""
    # format: rdismiss3_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    # user_id = int(parts[3])
    reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    # mute reporter
    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=reporter_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(days=7)
    )
    
    # punish reporter
    await queue_member_update(reporter_id, reputation_points=-20)
    await finish_report_action(chat_id, message_id, success=True)
    
    # delete bot's reply
    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted_dismissed3")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("rdismiss4_"))
@safe_callback
async def callback_report_dismiss_ban_reporter(call: CallbackQuery) -> None:
    """Dismiss and ban reporter."""
    # format: rdismiss4_chatId_msgId_userId_reporterId_botReplyId
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    # user_id = int(parts[3])
    reporter_id = int(parts[4])
    bot_reply_id = int(parts[5])

    # ban reporter
    await call.bot.ban_chat_member(chat_id=chat_id, user_id=reporter_id)
    await finish_report_action(chat_id, message_id, success=True)
    
    # delete bot's reply
    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, bot_reply_id)

    await call.message.edit_text(
        call.message.html_text + "\n\n" + get_string("action_deleted_dismissed4")
    )
    await call.answer(text="Done")


### LEGACY REPORT CALLBACKS (backwards compat) ###

@router.callback_query(F.data.startswith("del_"))
@safe_callback
async def callback_delete(call: CallbackQuery) -> None:
    """Delete reported message only (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("delban_"))
@safe_callback
async def callback_delete_and_ban(call: CallbackQuery) -> None:
    """Delete message and ban user (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted_banned")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("mute_"))
@safe_callback
async def callback_delete_and_mute_24h(call: CallbackQuery) -> None:
    """Delete message and mute user for 24 hours (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(hours=24)
    )

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted_readonly")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("mute2_"))
@safe_callback
async def callback_delete_and_mute_7d(call: CallbackQuery) -> None:
    """Delete message and mute user for 7 days (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(days=7)
    )

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted_readonly2")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("dismiss_"))
@safe_callback
async def callback_dismiss(call: CallbackQuery) -> None:
    """Dismiss report (false alarm) (legacy)."""
    await call.message.edit_text(
        call.message.html_text + get_string("action_dismissed")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("dismiss2_"))
@safe_callback
async def callback_dismiss_mute_reporter_1d(call: CallbackQuery) -> None:
    """Dismiss and mute reporter for 1 day (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(days=1)
    )

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted_dismissed2")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("dismiss3_"))
@safe_callback
async def callback_dismiss_mute_reporter_7d(call: CallbackQuery) -> None:
    """Dismiss and mute reporter for 7 days (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=datetime.now(timezone.utc) + timedelta(days=7)
    )

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted_dismissed3")
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("dismiss4_"))
@safe_callback
async def callback_dismiss_ban_reporter(call: CallbackQuery) -> None:
    """Dismiss and ban reporter (legacy)."""
    parts = call.data.split("_")
    chat_id = int(parts[1])
    message_id = int(parts[2])
    user_id = int(parts[3])

    with suppress(TelegramBadRequest):
        await call.bot.delete_message(chat_id, message_id)

    await call.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)

    await call.message.edit_text(
        call.message.html_text + get_string("action_deleted_dismissed4")
    )
    await call.answer(text="Done")


### SPAM CALLBACKS ###

@router.callback_query(F.data.startswith("spam_test_"))
@safe_callback
async def callback_spam_test(call: CallbackQuery) -> None:
    """Remove spam record (it was a test)."""
    parts = call.data.split("_")
    spam_id = int(parts[2])
    member_id = int(parts[3])

    # delete spam record
    try:
        await Spam.objects.delete(id=spam_id)
    except Exception:
        pass

    # increase member messages count
    try:
        member = await Member.objects.get(id=member_id)
        await queue_member_update(member.user_id, messages_count=1)
    except Exception:
        pass

    await call.message.edit_text(
        call.message.html_text + "\n\n<b>Удалено из базы, вероятно тест.</b>"
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("spam_ban_"))
@safe_callback
async def callback_spam_ban(call: CallbackQuery) -> None:
    """Ban user for spam."""
    parts = call.data.split("_")
    spam_id = int(parts[2])
    user_id = int(parts[3])
    # chat_id is stored in spam record
    
    # get spam record to find the chat_id
    try:
        spam_rec = await Spam.objects.get(id=spam_id)
        chat_id = spam_rec.chat_id
        
        if chat_id is None:
            await call.answer("❌ В записи спама отсутствует ID чата", show_alert=True)
            return
        await ban_and_cleanup(call.bot, chat_id, user_id)
            
        spam_rec.is_blocked = True
        await spam_rec.update()
    except Exception:
        logger.exception("Failed to ban spam user %s", user_id)
        await call.answer("❌ Не удалось выполнить действие. Проверьте права бота и повторите.", show_alert=True)
        return

    await call.message.edit_text(
        call.message.html_text + "\n\n❌ <b>Юзер забанен, сообщение помечено как спам</b>"
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("spam_invert_"))
@safe_callback
async def callback_spam_not_spam(call: CallbackQuery) -> None:
    """Mark message as not spam."""
    parts = call.data.split("_")
    spam_id = int(parts[2])
    member_id = int(parts[3]) if len(parts) > 3 else None

    # update spam record
    try:
        spam_rec = await Spam.objects.get(id=spam_id)
        spam_rec.is_spam = False
        await spam_rec.update()
    except Exception:
        pass

    # increase member reputation
    if member_id:
        try:
            member = await Member.objects.get(id=member_id)
            await queue_member_update(member.user_id, messages_count=1, reputation_points=10)
        except Exception:
            pass

    await call.message.edit_text(
        call.message.html_text + "\n\n❎ <b>Сообщение помечено как НЕ СПАМ</b>"
    )
    await call.answer(text="Done")


### NSFW CALLBACKS ###

@router.callback_query(F.data.startswith("nsfw_ban_"))
@safe_callback
async def callback_nsfw_ban(call: CallbackQuery) -> None:
    """Ban user for NSFW profile picture."""
    parts = call.data.split("_")
    user_id = int(parts[2])
    # chat_id is included in callback data
    chat_id = int(parts[3]) if len(parts) > 3 else None
    
    if chat_id is None:
        await call.answer("❌ В кнопке отсутствует ID чата", show_alert=True)
        return
    try:
        await ban_and_cleanup(call.bot, chat_id, user_id)
    except TelegramAPIError:
        logger.exception("Failed to ban NSFW user %s in chat %s", user_id, chat_id)
        await call.answer("❌ Не удалось забанить. Проверьте права бота и повторите.", show_alert=True)
        return

    await call.message.edit_text(
        call.message.html_text + "\n\n❌ <b>Юзер забанен за NSFW изображение профиля.</b>"
    )
    await call.answer(text="Done")


@router.callback_query(F.data.startswith("nsfw_safe_"))
@safe_callback
async def callback_nsfw_safe(call: CallbackQuery) -> None:
    """Mark as not NSFW."""
    member_id = int(call.data.split("_")[2])

    try:
        member = await Member.objects.get(id=member_id)
        await queue_member_update(member.user_id, messages_count=1, reputation_points=10)
        invalidate_nsfw_cache(member.user_id)
        mark_nsfw_profile_checked(member.user_id)
    except Exception:
        pass

    await call.message.edit_text(
        call.message.html_text + "\n\n❎ <b>Сообщение помечено как не содержащее NSFW.</b>"
    )
    await call.answer(text="Done")
