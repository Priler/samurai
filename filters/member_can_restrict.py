from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery


class MemberCanRestrictFilter(BaseFilter):
    """
    Filter that checks if the member can restrict other members.
    """

    def __init__(self, member_can_restrict: bool = True) -> None:
        self.member_can_restrict = member_can_restrict

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        if event.from_user is None:
            return False

        if isinstance(event, CallbackQuery):
            if event.message is None:
                return False
            chat_id = event.message.chat.id
            bot = event.bot
        else:
            chat_id = event.chat.id
            bot = event.bot

        member = await bot.get_chat_member(chat_id, event.from_user.id)

        # Creator can always restrict
        if member.status == "creator":
            can_restrict = True
        elif member.status == "administrator":
            can_restrict = getattr(member, "can_restrict_members", False)
        else:
            can_restrict = False

        if self.member_can_restrict:
            return can_restrict
        return not can_restrict
