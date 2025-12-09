# Samurai Bot v0.7 (aiogram 3.x)

A Telegram group moderation bot with anti-spam, anti-profanity, NSFW detection, and reputation system.

## Features

- **Anti-Profanity**: Automatically detects and removes messages containing profanity (Russian/English)
- **Anti-Spam**: ML-based spam detection for new users
- **NSFW Detection**: Profile photo analysis for suspicious accounts
- **Reputation System**: Users gain reputation through positive participation
- **Report System**: Users can report messages to admins
- **Scheduled Announcements**: Periodic automated messages

## Migration from aiogram 2.x

This bot has been migrated from aiogram 2.x to aiogram 3.x. Key changes:

- `Dispatcher(bot)` → `Dispatcher()` (bot passed to `start_polling`)
- `@dp.message_handler()` → `@router.message()`
- `BoundFilter` → `BaseFilter`
- `kick_chat_member` → `ban_chat_member`
- `types.ChatPermissions(True)` → `ChatPermissions(can_send_messages=True, ...)`
- `executor.start_polling()` → `dp.start_polling(bot)`

## Project Structure

```
samurai_v3/
├── bot.py                 # Main entry point
├── config/
│   ├── __init__.py
│   ├── settings.py        # Pydantic configuration
│   └── config.toml        # Configuration file
├── core/
│   ├── __init__.py
│   └── i18n.py            # Fluent internationalization
├── db/
│   ├── __init__.py
│   ├── database.py        # Database setup
│   └── models/
│       ├── member.py      # Member model
│       └── spam.py        # Spam record model
├── filters/
│   ├── is_owner.py
│   ├── is_admin.py
│   └── member_can_restrict.py
├── handlers/
│   ├── admin_actions.py   # Ban/unban commands
│   ├── callbacks.py       # Inline button handlers
│   ├── exceptions.py      # Error handler
│   ├── group_events.py    # Main message processing
│   ├── personal_actions.py# Ping, profanity check
│   └── user_actions.py    # Report command
├── locales/
│   ├── en/
│   │   └── strings.ftl    # English translations
│   └── ru/
│       └── strings.ftl    # Russian translations
├── middlewares/
│   ├── __init__.py
│   └── i18n.py            # I18n middleware
├── services/
│   ├── announcements.py   # Scheduled announcements
│   ├── cache.py           # LRU caching
│   ├── gender.py          # Gender detection
│   ├── nsfw.py            # NSFW detection
│   ├── profanity.py       # Profanity detection
│   └── spam.py            # Spam detection
├── utils/
│   ├── helpers.py         # Utility functions
│   └── localization.py    # Localization exports
├── libs/                  # External libraries (censure, gender_extractor)
├── ruspam_model/          # ML model for spam detection
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Internationalization (i18n)

The bot uses [Project Fluent](https://projectfluent.org/) for translations.

### Usage in handlers

```python
# Method 1: Import _ function directly
from core.i18n import _

async def handler(message: Message) -> None:
    text = _("error-no-reply")
    await message.reply(text)

# Method 2: Use i18n from middleware (user's locale)
async def handler(message: Message, i18n: Callable) -> None:
    text = i18n("error-no-reply")
    await message.reply(text)

# With variables
text = _("report-message", date="2024-01-01", chat_id="123", msg_id="456")
```

### Adding translations

1. Create/edit `.ftl` files in `locales/{lang}/`
2. Use hyphenated keys: `error-no-reply`
3. Variables use `{ $var }` syntax

Example `locales/ru/strings.ftl`:
```fluent
error-no-reply = Эта команда должна быть ответом на сообщение!
report-message = 👆 Отправлено { $date }
    <a href="https://t.me/c/{ $chat_id }/{ $msg_id }">Перейти</a>
```

## Installation

### Prerequisites

- Python 3.11+
- Bot token from [@BotFather](https://t.me/BotFather)

### Setup

1. Clone the repository

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

4. Configure `config.toml` with your group IDs

5. Run the bot:
   ```bash
   python bot.py
   ```

### Docker

```bash
docker build -t samurai-bot .
docker run -d --name samurai-bot -v $(pwd)/config.toml:/app/config.toml samurai-bot
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token |
| `BOT_OWNER` | Owner's Telegram user ID |
| `GROUPS_MAIN` | Main group chat ID |
| `GROUPS_REPORTS` | Reports group chat ID |
| `GROUPS_LOGS` | Logs group chat ID |
| `LINKED_CHANNEL` | Linked channel ID |
| `DB_URL` | Database URL |

### config.toml

```toml
[bot]
owner = 123456789
token = "your_bot_token"
language = "ru"
version = "0.7"
version_codename = "Eternal Ronin"

[groups]
main = -1001234567890
reports = -1001234567891
logs = -1001234567892
linked_channel = -1001234567893

[spam]
member_messages_threshold = 10
member_reputation_threshold = 10
allow_media_threshold = 20

[nsfw]
enabled = true

[db]
url = "sqlite+aiosqlite:///db.sqlite"
```

## Commands

### User Commands

| Command | Description |
|---------|-------------|
| `!report` / `/report` | Report a message (reply) |
| `!me` / `!info` | Show user info |
| `!бу` | Fun command |
| `@admin` | Call admin attention |

### Admin Commands

| Command | Description |
|---------|-------------|
| `!ban` | Ban user (reply) |
| `!unban` | Unban user (reply) |
| `!ping` | Check bot status |
| `!prof <text>` | Check text for profanity |

### Owner Commands

| Command | Description |
|---------|-------------|
| `!spam` | Mark message as spam (reply) |
| `!reward <points>` | Add reputation points |
| `!punish <points>` | Remove reputation points |
| `!setlvl <level>` | Set user level |
| `!rreset` | Reset user reputation |
| `!msg <text>` | Send message from bot |
| `!log <text>` | Write test log |

## External Libraries

The bot uses two external libraries that should be in the `libs/` folder:

- **censure**: Russian/English profanity detection
- **gender_extractor**: Gender detection from names

## ML Models

- **ruspam_model/**: BERT-based spam classifier
- **NSFW model**: SigLIP-based image classifier (downloaded from HuggingFace)

## License

MIT License
