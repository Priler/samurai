"""
Localization module - re-exports from core.i18n.

This module provides backwards compatibility with the old
get_string() function while using the new Fluent-based i18n system.

For new code, prefer using:
    from core.i18n import _
    text = _("error-no-reply")

Or with the i18n middleware in handlers:
    async def handler(message: Message, i18n: Callable) -> None:
        text = i18n("error-no-reply")
"""
from core.i18n import get_string, _, _random, get_i18n

# Announcements are kept here as they're bot-specific content
# and don't need translation (they're only in Russian)
ANNOUNCEMENTS = (
    {
        "message": "❕ Не забывайте про команду <b>!report</b> благодаря которой Вы можете обратить внимание администрации на <u>нарушителя в чате</u>.\n\n<tg-spoiler><i>Спам данной командой карается вечным баном.</i></tg-spoiler>",
        "every": 10900 * 1.5
    },
    {
        "message": "<b>📁 Это чат канала @howdyho_official</b>\nОбщайтесь вежливо и не нарушайте правила!\n\n📈 В чате действует <u>система репутации</u>\n⛔️ Новичкам запрещено отправлять медиа\n🤬 Мат <u>удаляется автоматически</u>\n👹 Оффтоп/спам наказывается 🍌 бананами\n\n<b>Всем мира 🤞</b>",
        "every": 10800
    },
    {
        "message": "<b>🫰 Донат автору канала:</b>\n\n<i>Мой Boosty:</i> https://boosty.to/howdyho\n<i>Мой Patreon:</i> <a href='https://www.patreon.com/user?u=22843414'>https://www.patreon.com/howdyho</a>\n<i>Наш Discord:</i> <a href='https://discord.gg/6khaudi-kho-1123002520072097953'>https://discord.gg/howdyho</a>",
        "every": 7200 * 3
    },
    {
        "message": "<b>😈 У нас есть сайт, ты знал?</b>\n\nВотб он - https://howdyho.net\nМы там постим топовый софт, обои, игры, и кучу всего для ПК!\n\n<i>Заходи, тебе там всегда рады!</i>",
        "every": 9000 * 2
    },
    {
        "message": "<b>🫰 Хочешь чтобы твой мем/пост закинули в канал?</b>\nТыкай сюда - @hhsharebot",
        "every": 14500
    }
)

__all__ = ["get_string", "_", "_random", "get_i18n", "ANNOUNCEMENTS"]
