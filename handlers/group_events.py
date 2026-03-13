"""
Group event handlers - message processing, profanity/spam detection, reputation system.

IMPORTANT: Handler order matters in aiogram 3.x!
- Command handlers must come BEFORE catch-all message handlers
- The on_user_message handler should be LAST as it catches all text messages
"""
import asyncio
import io
import logging
import random
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, ContentType, InlineKeyboardMarkup, InlineKeyboardButton,
    ChatMemberAdministrator, ChatMemberOwner
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command

from PIL import Image
import numpy as np

from config import config
from filters import IsOwnerFilter, InMainGroups, ThrottleFilter
from db.models import Member, Spam
from services import (
    retrieve_or_create_member, retrieve_tgmember, detect_gender,
    check_for_profanity_all, check_name_for_violations, Gender
)
from services.spam import predict as ruspam_predict
from services.nsfw import classify_explicit_content as nsfw_predict
from services.cache import (
    queue_member_update, 
    invalidate_member_cache,
    is_trusted_user,
    get_cached_nsfw_result,
    cache_nsfw_result,
    is_nsfw_profile_on_cooldown,
    mark_nsfw_profile_checked,
    get_member_orm,
    MemberData
)
from services.announcements import track_message
from utils import (
    get_string, _random, user_mention, write_log, 
    generate_log_message, remove_prefix, get_message_text,
    MemberStatus
)

router = Router(name="group_events")


MEDIA_CONTENT_TYPES = {
    ContentType.PHOTO, ContentType.VIDEO, ContentType.AUDIO,
    ContentType.DOCUMENT, ContentType.VOICE, ContentType.VIDEO_NOTE,
    ContentType.ANIMATION
}

# media types only handled by on_user_media (not covered by on_user_message)
# VOICE is handled by on_user_voice separately
MEDIA_ONLY_CONTENT_TYPES = {
    ContentType.AUDIO, ContentType.VIDEO_NOTE, ContentType.ANIMATION
}


### COMMAND HANDLERS (must be before catch-all) ###

# fun command
@router.message(InMainGroups(), Command("бу", prefix="!/"))
async def on_bu(message: Message) -> None:
    """Fun command - bot gets 'scared'."""
    await message.reply(_random("bu-responses"))


# rules (throttled per group)
@router.message(
    InMainGroups(), 
    Command("rules", "правила", prefix="!/"),
    ThrottleFilter(interval=60, per_group=True)
)
async def on_rules(message: Message) -> None:
    """Show chat rules (throttled per group - once per minute)."""
    await message.answer(get_string("rules-message"))


# user info
@router.message(
    InMainGroups(),
    Command("me", "я", "info", "инфо", "lvl", "лвл", "whoami", "neofetch", "fastfetch", prefix="!/"),
    ThrottleFilter(interval=60, per_member=True, per_group=True)
)
async def on_me(message: Message) -> None:
    """Show user info and reputation."""
    if message.reply_to_message and not message.reply_to_message.is_automatic_forward:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id

    member = await retrieve_or_create_member(user_id)
    tg_member = await retrieve_tgmember(message.bot, message.chat.id, user_id)

    # censor profanity in name
    full_name = tg_member.user.full_name.strip()
    is_profanity, bad_word = check_for_profanity_all(full_name)
    if is_profanity and bad_word:
        full_name = full_name.replace(bad_word, '#' * len(bad_word))

    member_gender = detect_gender(tg_member.user.first_name)

    # level and avatar
    is_creator = tg_member.status == MemberStatus.CREATOR
    is_admin = tg_member.status in MemberStatus.admin_statuses()

    if is_creator:
        member_level = get_string("level-king")
        member_rep = get_string("rep-creator")
        member_avatar = "✖️"
    elif is_admin:
        member_level = _random("admin-roles")
        member_rep = "🛡 "
        member_avatar = random.choice(['👮', '👮‍♂️', '👮‍♀️', '🚔', '⚖️', '🤖', '😼', '⚔️'])
    else:
        member_rep = ""

        if member.messages_count < 100:
            member_level = get_string("level-noname")
        elif 100 <= member.messages_count < 500:
            member_level = get_string("level-newbie")
        elif 500 <= member.messages_count < 1000:
            member_level = get_string("level-experienced")
        elif 1000 <= member.messages_count < 2000:
            member_level = get_string("level-professional")
        elif 2000 <= member.messages_count < 3000:
            member_level = get_string("level-veteran")
        elif 3000 <= member.messages_count < 5000:
            member_level = get_string("level-master")
        else:
            member_level = get_string("level-legend")

        if member_gender == Gender.FEMALE:
            member_avatar = random.choice(['👩‍🦰', '👩', '👱‍♀️', '👧', '👩‍🦱', '🤵‍♀️', '👩‍🦳'])
        elif member_gender == Gender.MALE:
            member_avatar = random.choice(['👨‍🦳', '🧔', '🧑', '👨', '🧔‍♂️', '🧑‍🦰', '🧑‍🦱', '👨‍🦰', '👦', '🤵‍♂️'])
        else:
            member_avatar = random.choice(['🤖', '😼', '👻', '😺'])

    # rep label
    member_rep_label = ""
    if not is_creator:
        if member.reputation_points < -2000:
            member_rep_label = get_string("rep-label-wanted")
        elif -2000 <= member.reputation_points < -1000:
            member_rep_label = get_string("rep-label-dangerous")
        elif -1000 <= member.reputation_points < -500:
            member_rep_label = get_string("rep-label-shady")
        elif -500 <= member.reputation_points < 0:
            member_rep_label = get_string("rep-label-violator")
        elif 0 <= member.reputation_points < 100:
            member_rep_label = get_string("rep-label-neutral")
        elif 100 <= member.reputation_points < 500:
            member_rep_label = get_string("rep-label-good")
        elif 500 <= member.reputation_points < 1000:
            member_rep_label = get_string("rep-label-very-good")
        else:
            member_rep_label = get_string("rep-label-generous")

    answer = f"{member_avatar} <b>{full_name}</b>"
    answer += f"\n<b>{get_string('rep-title')}: </b>{member_level} <i> 『{member_rep}{member_rep_label} (<tg-spoiler>{member.reputation_points}</tg-spoiler>)』</i>"

    try:
        await message.reply(answer)
    except TelegramBadRequest:
        pass  # original msg was deleted


### OWNER COMMANDS ###

@router.message(
    InMainGroups(),
    IsOwnerFilter(),
    Command("spam", prefix="!")
)
async def on_spam(message: Message) -> None:
    """Mark a message as spam (owner only)."""
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    member = await retrieve_or_create_member(message.reply_to_message.from_user.id)
    tg_member = await retrieve_tgmember(message.bot, message.chat.id, message.reply_to_message.from_user.id)

    # get msg text
    msg_text = None
    if message.reply_to_message.content_type == ContentType.TEXT:
        msg_text = message.reply_to_message.text
    elif message.reply_to_message.content_type in (ContentType.PHOTO, ContentType.DOCUMENT, ContentType.VIDEO):
        msg_text = message.reply_to_message.caption

    if msg_text is None:
        await message.reply("Нет текста - нет спама :3")
        return

    try:
        log_msg = msg_text
        log_msg += f"\n\n<i>Автор:</i> {user_mention(message.reply_to_message.from_user)}"

        # create DB record
        spam_rec = await Spam.objects.create(
            message=msg_text,
            is_spam=True,
            user_id=message.reply_to_message.from_user.id,
            chat_id=message.chat.id
        )

        spam_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Это спам + заблокировать пользователя",
                callback_data=f"spam_ban_{spam_rec.id}_{message.reply_to_message.from_user.id}"
            )],
            [InlineKeyboardButton(
                text="❎ Это НЕ спам",
                callback_data=f"spam_invert_{spam_rec.id}_{member.id}"
            )],
            [InlineKeyboardButton(
                text="Убрать из БД, это тест",
                callback_data=f"spam_test_{spam_rec.id}_{member.id}"
            )]
        ])

        await message.bot.send_message(
            config.groups.logs,
            generate_log_message(log_msg, "❌ АнтиСПАМ", message.chat.title),
            reply_markup=spam_keyboard
        )

        # remove msg if not admin
        if tg_member.status not in MemberStatus.admin_statuses():
            await message.reply_to_message.delete()

        await message.reply("🫡 Сообщение помечено как спам.")
    except Exception:
        await message.reply("O_o Мда")


@router.message(InMainGroups(), IsOwnerFilter(), Command("setlvl", prefix="!"))
async def on_setlvl(message: Message) -> None:
    """Set user level (owner only)."""
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    try:
        value = abs(int(remove_prefix(message.text, "!setlvl")))
        if value > 100000:
            await message.reply("Что куришь, другалёк? :3")
        else:
            member = await get_member_orm(message.reply_to_message.from_user.id)
            member.messages_count = value
            member.reputation_points += value
            await member.update()
            invalidate_member_cache(message.reply_to_message.from_user.id)
            await message.reply("Ладно :3")
    except ValueError:
        await message.reply("O_o Мда")


@router.message(InMainGroups(), IsOwnerFilter(), Command("reward", prefix="!"))
async def on_reward(message: Message) -> None:
    """Reward reputation points (owner only)."""
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    try:
        points = abs(int(remove_prefix(message.text, "!reward")))
    except ValueError:
        await message.reply("O_o Мда")
        return

    if points > 100_000:
        await message.reply("Нетб :3")
    else:
        await queue_member_update(message.reply_to_message.from_user.id, reputation_points=points)
        await message.reply(f"➕ Участник чата получает <i><b>{points}</b> очков репутации.</i>")


@router.message(InMainGroups(), IsOwnerFilter(), Command("rreset", prefix="!"))
async def on_rep_reset(message: Message) -> None:
    """Reset user reputation (owner only)."""
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    try:
        member = await get_member_orm(message.reply_to_message.from_user.id)
        member.reputation_points = member.messages_count
        await member.update()
        invalidate_member_cache(message.reply_to_message.from_user.id)
        await message.reply("☯ Уровень репутации участника <i><b>сброшен</b>.</i>")
    except Exception:
        await message.reply("O_o Мда")


@router.message(InMainGroups(), IsOwnerFilter(), Command("punish", prefix="!"))
async def on_punish(message: Message) -> None:
    """Punish user - remove reputation (owner only)."""
    if not message.reply_to_message:
        await message.reply("Чего ты от меня хочешь :3")
        return

    try:
        points = abs(int(remove_prefix(message.text, "!punish")))
    except ValueError:
        await message.reply("O_o Мда")
        return

    if points > 100_000:
        await message.reply("Нетб :3")
    else:
        await queue_member_update(message.reply_to_message.from_user.id, reputation_points=-points)
        await message.reply(f"➖ Участник чата теряет <i><b>{points}</b> очков репутации.</i>")


### SERVICE MESSAGE HANDLERS ###

# user join
@router.message(InMainGroups(), F.content_type == ContentType.NEW_CHAT_MEMBERS)
async def on_user_join(message: Message) -> None:
    """Remove 'user joined' service message."""
    await message.delete()
    await write_log(
        message.bot,
        f"Присоединился пользователь {user_mention(message.from_user)}",
        "➕ Новый участник",
        message.chat.title
    )


# voice messages (discourage)
@router.message(InMainGroups(), F.content_type == ContentType.VOICE)
async def on_user_voice(message: Message) -> None:
    """React to voice messages (discourage them)."""
    if random.random() < 0.75:  # 75% chance
        await message.reply(_random("voice-responses"))
        await queue_member_update(message.from_user.id, reputation_points=-10)


# contacts
@router.message(InMainGroups(), F.content_type == ContentType.CONTACT)
async def on_user_contact(message: Message) -> None:
    """Delete contact messages from non-admins."""
    tg_member = await retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    if tg_member.status not in MemberStatus.admin_statuses():
        await message.delete()


# cross-chat reply restriction ("Reply in Another Chat")
@router.message(InMainGroups(), F.external_reply, ~F.is_automatic_forward)
async def on_external_reply(message: Message) -> None:
    """
    Delete cross-chat replies from low-rep users.

    Messages sent via "Reply in Another Chat" have external_reply set.
    This covers both plain text replies and forwards containing an external reply.
    """
    if message.from_user is None:
        return

    tg_member = await retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    if tg_member.status in MemberStatus.admin_statuses():
        return

    member = await retrieve_or_create_member(message.from_user.id)

    if member.reputation_points < config.spam.external_reply_rep_threshold:
        await message.delete()

        await queue_member_update(
            message.from_user.id,
            violations_count_spam=1,
            reputation_points=-10
        )

        msg_text = get_message_text(message) or "[медиа без текста]"
        await write_log(
            message.bot,
            f"{msg_text}\n\n<i>Автор:</i> {user_mention(message.from_user)}",
            "↩️ Антиспам (кросс-чат)",
            message.chat.title
        )
        await _maybe_autoban(message, member, 10, "кросс-чат")


# forwards restriction
@router.message(InMainGroups(), F.forward_origin)
async def on_user_forward(message: Message) -> None:
    """
    Delete forwards from low-rep users (anti-spam).
    
    Allowed: auto-forwards, linked channels, group members
    Blocked: external channels, non-members
    """
    # skip auto-forwards
    if message.is_automatic_forward:
        return
    
    # allow forwards from linked channels
    if message.forward_from_chat:
        if config.groups.is_linked_channel(message.forward_from_chat.id):
            return
    
    # allow forwards from group members
    if message.forward_from:
        try:
            forwarded_member = await message.bot.get_chat_member(
                message.chat.id, 
                message.forward_from.id
            )
            if forwarded_member.status not in ("left", "kicked"):
                return
        except Exception:
            pass  # user not found or privacy settings
    
    # external forward - check rep
    member = await retrieve_or_create_member(message.from_user.id)
    tg_member = await retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    # skip admins
    if tg_member.status in MemberStatus.admin_statuses():
        return

    if member.reputation_points < config.spam.allow_forwards_threshold:
        await message.delete()
        
        await queue_member_update(
            message.from_user.id,
            reputation_points=-config.spam.forward_violation_penalty,
            violations_count_spam=1
        )
        
        # log
        forward_from = "Unknown"
        if message.forward_from:
            forward_from = f"👤 {message.forward_from.full_name}"
        elif message.forward_from_chat:
            forward_from = f"📢 {message.forward_from_chat.title or message.forward_from_chat.id}"
        elif message.forward_sender_name:
            forward_from = f"👤 {message.forward_sender_name}"
        
        await write_log(
            message.bot,
            f"Удалён форвард от: {forward_from}\n\n"
            f"<i>Автор:</i> {user_mention(message.from_user)}\n"
            f"<i>Репутация:</i> {member.reputation_points}",
            "📨 Антиспам",
            message.chat.title
        )


# media restriction
@router.message(
    InMainGroups(), 
    F.content_type.in_(MEDIA_ONLY_CONTENT_TYPES),
    ~F.is_automatic_forward
)
async def on_user_media(message: Message) -> None:
    """Delete media from low-rep users."""
    member = await retrieve_or_create_member(message.from_user.id)
    tg_member = await retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    if (tg_member.status not in MemberStatus.admin_statuses() and
        member.reputation_points < config.spam.allow_media_threshold):
        await message.delete()


### CHANNEL AUTO-FORWARD (bot comments on posts) ###

@router.message(InMainGroups(), F.is_automatic_forward)
async def on_channel_post(message: Message) -> None:
    """Reply to auto-forwarded channel posts with a random comment."""
    try:
        await message.reply(_random("bot-comments"))
    except TelegramBadRequest as e:
        logging.getLogger(__name__).warning(f"Failed to reply to channel post: {e}")


### CATCH-ALL MESSAGE HANDLER (must be last!) ###

@router.message(
    InMainGroups(),
    F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT, ContentType.VIDEO}),
    ~F.is_automatic_forward
)
@router.edited_message(
    InMainGroups(),
    F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT, ContentType.VIDEO}),
    ~F.is_automatic_forward
)
async def on_user_message(message: Message) -> None:
    """
    Process every user message - profanity, spam, reputation.
    
    NOTE: This handler MUST be last in this file!
    """
    # track for announcement rate limiting
    track_message(message.chat.id, is_announcement=False)

    # skip channel-originated messages (sender_chat set, from_user is None)
    if message.from_user is None:
        return

    member = await retrieve_or_create_member(message.from_user.id)
    tg_member = await retrieve_tgmember(message.bot, message.chat.id, message.from_user.id)

    # skip admins
    if tg_member.status in MemberStatus.admin_statuses():
        return

    # media restriction for low-rep users (photos, videos, documents)
    if message.content_type != ContentType.TEXT:
        if member.reputation_points < config.spam.allow_media_threshold:
            await message.delete()
            return

    msg_text = get_message_text(message)
    user_id = message.from_user.id

    if msg_text is not None:
        # chinese spam bots
        if _contains_chinese(msg_text):
            await message.delete()

            await queue_member_update(
                user_id,
                violations_count_spam=1,
                reputation_points=-5
            )

            log_msg = msg_text
            log_msg += f"\n\n<i>Автор:</i> {user_mention(message.from_user)}"
            await write_log(message.bot, log_msg, "🈲 Антиспам (CN)", message.chat.title)
            await _maybe_autoban(message, member, 5, "CN-спам")
            return

        # check profanity
        is_profanity, bad_word = check_for_profanity_all(msg_text)

        if is_profanity:
            await message.delete()

            await queue_member_update(
                user_id,
                violations_count_profanity=1,
                reputation_points=-20
            )

            log_msg = msg_text
            if bad_word:
                log_msg = log_msg.replace(bad_word, f'<u><b>{bad_word}</b></u>')
            log_msg += f"\n\n<i>Автор:</i> {user_mention(message.from_user)}"
            await write_log(message.bot, log_msg, "🤬 Антимат", message.chat.title)
            return

        # single-emoji spam (bots flooding with lone emojis)
        if (member.reputation_points < config.spam.single_emoji_rep_threshold and
                _is_single_emoji(msg_text)):
            await message.delete()

            await queue_member_update(
                user_id,
                violations_count_spam=1,
                reputation_points=-5
            )

            await write_log(
                message.bot,
                f"{msg_text}\n\n<i>Автор:</i> {user_mention(message.from_user)}",
                "🤖 Антиспам (эмодзи)",
                message.chat.title
            )
            return

        # link spam (t.me invites, external URLs) from low-rep users
        if (member.reputation_points < config.spam.links_rep_threshold and
                _contains_link(message)):
            await message.delete()

            await queue_member_update(
                user_id,
                violations_count_spam=1,
                reputation_points=-10
            )

            await write_log(
                message.bot,
                f"{msg_text}\n\n<i>Автор:</i> {user_mention(message.from_user)}",
                "🔗 Антиспам (ссылка)",
                message.chat.title
            )
            await _maybe_autoban(message, member, 10, "ссылка")
            return

        # no profanity - check spam
        # skip expensive ML for trusted users
        should_check_spam = not is_trusted_user(member) and (
            member.messages_count < config.spam.member_messages_threshold or 
            member.reputation_points < config.spam.member_reputation_threshold
        )
        
        if should_check_spam and await asyncio.to_thread(ruspam_predict, msg_text):
            # spam detected
            await message.delete()

            await queue_member_update(
                user_id,
                violations_count_spam=1,
                reputation_points=-5
            )
            
            await _maybe_autoban(message, member, 5, "спам")
            return

    # check for unwanted content (nsfw, suspicious profiles)
    handled = await check_for_unwanted(message, msg_text, member)

    if not handled:
        # clean msg - increase rep
        await queue_member_update(
            user_id,
            messages_count=1,
            reputation_points=1
        )


### HELPER FUNCTIONS ###

async def check_for_unwanted(message: Message, msg_text: str, member: MemberData) -> bool:
    """Check for unwanted content (first comments, NSFW images, suspicious profiles)."""
    # check if reply to channel post (comment)
    if (message.reply_to_message and 
        message.reply_to_message.forward_from_chat and 
        config.groups.is_linked_channel(message.reply_to_message.forward_from_chat.id)):
        
        # remove early comments from low-rep users
        threshold = config.spam.allow_comments_rep_threshold
        interval = config.spam.remove_first_comments_interval
        
        if (member.reputation_points < threshold and
            (message.date - message.reply_to_message.forward_date).seconds <= interval):
            try:
                await message.delete()
                await write_log(
                    message.bot,
                    f"Удалено сообщение: {message.text}\n\n<i>Автор:</i> {user_mention(message.from_user)}",
                    "🤖 Антибот",
                    message.chat.title
                )
                return True
            except TelegramBadRequest:
                pass

    if not config.nsfw.enabled:
        return False

    user_id = message.from_user.id
    is_low_rep = member.reputation_points < config.nsfw.check_rep_threshold

    # in-chat image nsfw check
    if message.content_type == ContentType.PHOTO and is_low_rep:
        photo = message.photo[-1]
        cached = get_cached_nsfw_result(user_id, photo.file_unique_id)

        if cached is None:
            img_file = await message.bot.get_file(photo.file_id)
            file_bytes = await message.bot.download_file(img_file.file_path)
            image = Image.open(io.BytesIO(file_bytes.getvalue())).convert("RGB")
            prediction = await asyncio.to_thread(nsfw_predict, np.asarray(image))
            is_nsfw = is_nsfw_detected(prediction)
            cache_nsfw_result(user_id, photo.file_unique_id, is_nsfw)
        else:
            is_nsfw = cached
            prediction = None

        if is_nsfw:
            extra = f"<i>Scores:</i> {_format_nsfw_scores(prediction)}" if prediction else None
            await _report_nsfw(message, msg_text, member, "🔞 NSFW (фото)", extra)
            return True

    # profile-based checks with per-user cooldown
    if is_low_rep and not is_nsfw_profile_on_cooldown(user_id):
        mark_nsfw_profile_checked(user_id)

        # name violation check (spam names like "посмотри мой профиль")
        if not check_name_for_violations(message.from_user.full_name):
            await _report_nsfw(
                message, msg_text, member, "🚫 Антиспам (имя)",
                f"<i>Имя:</i> {message.from_user.full_name}"
            )
            return True

        # profile photo nsfw check
        profile_photos = await message.bot.get_user_profile_photos(user_id=user_id)

        if profile_photos.photos:
            photo = profile_photos.photos[0][-1]
            cached = get_cached_nsfw_result(user_id, photo.file_unique_id)

            if cached is None:
                img_file = await message.bot.get_file(photo.file_id)
                file_bytes = await message.bot.download_file(img_file.file_path)
                image = Image.open(io.BytesIO(file_bytes.getvalue())).convert("RGB")
                prediction = await asyncio.to_thread(nsfw_predict, np.asarray(image))
                is_nsfw = is_nsfw_detected(prediction)
                cache_nsfw_result(user_id, photo.file_unique_id, is_nsfw)
            else:
                is_nsfw = cached
                prediction = None

            if is_nsfw:
                extra = f"<i>Scores:</i> {_format_nsfw_scores(prediction)}" if prediction else None
                await _report_nsfw(message, msg_text, member, "🔞 NSFW (профиль)", extra)
                return True

    return False


async def _maybe_autoban(
    message: Message, member: MemberData, penalty: int, reason: str
) -> None:
    """Ban user if violations + rep thresholds are exceeded."""
    if not config.spam.autoban_enabled:
        return
    new_violations = member.violations_count_spam + 1
    new_rep = member.reputation_points - penalty
    if (new_violations >= config.spam.autoban_threshold and
            new_rep < config.spam.autoban_rep_threshold):
        try:
            await message.bot.ban_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id
            )
            await write_log(
                message.bot,
                f"Автобан ({reason}): {new_violations} нарушений\n"
                f"<i>Репутация:</i> {new_rep}\n\n"
                f"<i>Пользователь:</i> {user_mention(message.from_user)}",
                "🚫 Автобан",
                message.chat.title
            )
        except Exception:
            pass  # user left or already banned


async def _report_nsfw(
    message: Message, msg_text: Optional[str], member: MemberData,
    log_label: str, extra_info: str = None
) -> None:
    """Delete message and report to log channel with action buttons."""
    log_msg = msg_text or "[медиа без текста]"
    if extra_info:
        log_msg += f"\n\n{extra_info}"
    log_msg += f"\n\n<i>Автор:</i> {user_mention(message.from_user)}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ NSFW + бан",
            callback_data=f"nsfw_ban_{message.from_user.id}_{message.chat.id}"
        )],
        [InlineKeyboardButton(
            text="❎ Это НЕ NSFW",
            callback_data=f"nsfw_safe_{member.id}"
        )]
    ])

    await message.bot.send_message(
        config.groups.logs,
        generate_log_message(log_msg, log_label, message.chat.title),
        reply_markup=keyboard
    )
    await message.delete()


def _format_nsfw_scores(prediction: dict) -> str:
    """Format NSFW prediction scores for log messages."""
    labels = {
        "Normal": "N", "Pornography": "P", "Enticing or Sensual": "S",
        "Hentai": "H", "Anime Picture": "A"
    }
    return " | ".join(f"{labels.get(k, k)}: {v}" for k, v in prediction.items())


def _contains_link(message: Message) -> bool:
    """Return True if message contains any URL or clickable link.

    Uses Telegram's own entity parsing - covers plain URLs (http/https/t.me)
    and inline hyperlinks (text_link entities).
    """
    entities = message.entities or message.caption_entities or []
    return any(e.type in ("url", "text_link") for e in entities)


def _is_single_emoji(text: str) -> bool:
    """Return True if text contains exactly one emoji and nothing else.

    Handles simple emoji, emoji + variation selector / skin-tone modifier,
    and two-regional-indicator flag sequences (e.g. 🇺🇸).
    ZWJ sequences (👨‍👩‍👧) are intentionally treated as multi-emoji so they
    are NOT flagged - only trivial single-character bot spam is caught.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Even the most exotic single emoji is < 10 UTF-16 code units
    if len(stripped) > 10:
        return False

    _SKIP = {0xFE0F, 0x200D, 0x20E3}  # variation selector, ZWJ, combining keycap

    base_count = 0
    all_regional = True

    for char in stripped:
        cp = ord(char)

        # Non-base combiners: skip without counting
        if cp in _SKIP or 0x1F3FB <= cp <= 0x1F3FF:
            continue

        is_emoji = (
            0x1F600 <= cp <= 0x1F64F or  # emoticons
            0x1F300 <= cp <= 0x1F5FF or  # misc symbols & pictographs
            0x1F680 <= cp <= 0x1F6FF or  # transport & map
            0x1F700 <= cp <= 0x1FA6F or  # alchemical → chess symbols
            0x1FA70 <= cp <= 0x1FAFF or  # symbols & pictographs extended-A
            0x2600  <= cp <= 0x27BF  or  # misc symbols + dingbats
            0x1F1E0 <= cp <= 0x1F1FF or  # regional indicators (flags)
            0x2300  <= cp <= 0x23FF  or  # misc technical (⌚ etc.)
            0x2B00  <= cp <= 0x2BFF  or  # misc symbols and arrows
            cp in (0x00A9, 0x00AE, 0x2122)  # ©®™
        )
        if not is_emoji:
            return False  # contains real text

        if not (0x1F1E0 <= cp <= 0x1F1FF):
            all_regional = False
        base_count += 1

    if base_count == 1:
        return True  # ordinary single emoji
    if base_count == 2 and all_regional:
        return True  # flag (two regional indicator chars)
    return False


def _contains_chinese(text: str) -> bool:
    """Check if text contains Chinese characters (CJK Unified Ideographs)."""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF or      # CJK Unified
            0x3400 <= cp <= 0x4DBF or      # CJK Extension A
            0x20000 <= cp <= 0x2A6DF or    # CJK Extension B
            0xF900 <= cp <= 0xFAFF):       # CJK Compatibility
            return True
    return False


def is_nsfw_detected(prediction: dict) -> bool:
    """Check if NSFW is detected based on thresholds.

    Detection requires *companion signals* - a single elevated category
    alone is not enough (the model produces too many false positives on
    clean anime art / attractive-but-safe photos).
    """
    normal = float(prediction["Normal"])
    anime = float(prediction["Anime Picture"])
    sensual = float(prediction["Enticing or Sensual"])
    porn = float(prediction["Pornography"])
    hentai = float(prediction["Hentai"])

    # safe: high Normal or Anime with low explicit signals
    # even if both sensual+porn are individually below limits, together they override
    is_safe = (
        (normal > config.nsfw.normal_prediction_threshold or
         anime > config.nsfw.anime_prediction_threshold)
        and
        (sensual < config.nsfw.normal_comb_sensual_prediction_threshold
         and porn < config.nsfw.normal_comb_pornography_prediction_threshold)
        and not (sensual > 0.25 and porn > 0.03)
    )

    # combined sensual + pornography - most reliable signal
    is_combined = (
        sensual > config.nsfw.comb_sensual_prediction_threshold
        and porn > config.nsfw.comb_pornography_prediction_threshold
    )

    # strong pornography alone
    is_porn = porn > config.nsfw.pornography_prediction_threshold

    # high sensual - needs some porn signal at moderate confidence,
    # but very high sensual (>0.95) is conclusive on its own
    is_sensual = (
        sensual > config.nsfw.sensual_prediction_threshold
        and (sensual > 0.95 or porn > 0.01)
    )

    # high hentai - only with explicit companion (avoids FP on clean anime art)
    is_hentai = (
        hentai > config.nsfw.hentai_prediction_threshold
        and (porn > 0.05 or sensual > 0.1)
    )

    return not is_safe and (is_combined or is_porn or is_sensual or is_hentai)
