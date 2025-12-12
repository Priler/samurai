from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from config import config


class IsOwnerFilter(BaseFilter):
    """
    Filter that checks if the user is the bot owner.
    """

    def __init__(self, is_owner: bool = True) -> None:
        self.is_owner = is_owner

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        if event.from_user is None:
            return False

        user_is_owner = event.from_user.id == config.bot.owner

        if self.is_owner:
            return user_is_owner
        return not user_is_owner
