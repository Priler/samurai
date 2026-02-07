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
    F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT, ContentType.VIDEO})
)
async def on_user_message(message: Message) -> None:
    """
    Process every user message - profanity, spam, reputation.
    
    NOTE: This handler MUST be last in this file!
    """
    # track for announcement rate limiting
    track_message(message.chat.id, is_announcement=False)
    
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

    if msg_text is None:
        return

    user_id = message.from_user.id

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
    else:
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
            
            # auto-ban check
            if config.spam.autoban_enabled:
                new_violations = member.violations_count_spam + 1
                new_rep = member.reputation_points - 5
                if (new_violations >= config.spam.autoban_threshold and 
                    new_rep < config.spam.autoban_rep_threshold):
                    try:
                        await message.bot.ban_chat_member(
                            chat_id=message.chat.id,
                            user_id=user_id
                        )
                        await write_log(
                            message.bot,
                            f"Автобан за спам: {new_violations} нарушений\n"
                            f"<i>Репутация:</i> {new_rep}\n\n"
                            f"<i>Пользователь:</i> {user_mention(message.from_user)}",
                            "🚫 Автобан",
                            message.chat.title
                        )
                    except Exception:
                        pass  # user left or already banned
        else:
            # check for unwanted content (nsfw etc)
            handled = await check_for_unwanted(message, msg_text, member, tg_member)

            if not handled:
                # clean msg - increase rep
                await queue_member_update(
                    user_id,
                    messages_count=1,
                    reputation_points=1
                )


### HELPER FUNCTIONS ###

async def check_for_unwanted(message: Message, msg_text: str, member: MemberData, tg_member) -> bool:
    """Check for unwanted content (first comments, NSFW profiles)."""
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

    # nsfw check (female profiles only)
    member_gender = detect_gender(tg_member.user.first_name)

    if member_gender == Gender.FEMALE and config.nsfw.enabled:
        # skip high-rep
        if member.reputation_points > config.spam.allow_comments_rep_threshold__woman:
            return False

        name_valid = check_name_for_violations(message.from_user.full_name)

        nsfw_prediction = None
        cached_result = None
        if name_valid:
            profile_photos = await message.bot.get_user_profile_photos(user_id=message.from_user.id)

            if not profile_photos.photos:
                return False

            photo = profile_photos.photos[0][-1]
            file_unique_id = photo.file_unique_id
            
            # check cache first
            cached_result = get_cached_nsfw_result(message.from_user.id, file_unique_id)
            if cached_result is not None:
                if not cached_result:
                    return False
            else:
                # not cached - do nsfw check
                file_id = photo.file_id
                img_file = await message.bot.get_file(file_id)
                file_bytes = await message.bot.download_file(img_file.file_path)

                image = Image.open(io.BytesIO(file_bytes.getvalue())).convert("RGB")
                nsfw_prediction = await asyncio.to_thread(nsfw_predict, np.asarray(image))
                
                is_nsfw = is_nsfw_detected(nsfw_prediction) if nsfw_prediction else False
                cache_nsfw_result(message.from_user.id, file_unique_id, is_nsfw)
                
                if not is_nsfw:
                    return False

        # check thresholds
        if (not name_valid or (nsfw_prediction and is_nsfw_detected(nsfw_prediction)) or
            (cached_result is True)):
            log_msg = msg_text
            log_msg += f"\n\n<i>Автор:</i> {user_mention(message.from_user)}"

            nsfw_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Это NSFW + заблокировать пользователя",
                    callback_data=f"nsfw_ban_{message.from_user.id}_{message.chat.id}"
                )],
                [InlineKeyboardButton(
                    text="❎ Это НЕ NSFW",
                    callback_data=f"nsfw_safe_{member.id}"
                )]
            ])

            await message.bot.send_message(
                config.groups.logs,
                generate_log_message(log_msg, "🔞 NSFW", message.chat.title),
                reply_markup=nsfw_keyboard
            )

            await message.delete()
            return True

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
    """Check if NSFW is detected based on thresholds."""
    # safe checks
    is_safe = (
        (float(prediction["Normal"]) > config.nsfw.normal_prediction_threshold or
         float(prediction["Anime Picture"]) > config.nsfw.anime_prediction_threshold)
        and
        (float(prediction["Enticing or Sensual"]) < config.nsfw.normal_comb_sensual_prediction_threshold
         and float(prediction["Pornography"]) < config.nsfw.normal_comb_pornography_prediction_threshold)
    )

    # unsafe checks
    is_unsafe = (
        (float(prediction["Enticing or Sensual"]) > config.nsfw.comb_sensual_prediction_threshold
         and float(prediction["Pornography"]) > config.nsfw.comb_pornography_prediction_threshold)
        or float(prediction["Enticing or Sensual"]) > config.nsfw.sensual_prediction_threshold
        or float(prediction["Pornography"]) > config.nsfw.pornography_prediction_threshold
        or float(prediction["Hentai"]) > config.nsfw.hentai_prediction_threshold
    )

    return not is_safe and is_unsafe
