import random
from time import time
from aiogram import types
from configurator import config
from dispatcher import dp
import localization
import utils
import psutil

import sys
sys.path.append("./censure") # allow module import from git submodule

from censure import Censor

censor_ru = Censor.get(lang='ru')
censor_en = Censor.get(lang='en')


@dp.message_handler(user_id = int(config.bot.owner), commands="msg", commands_prefix="!/")
async def cmd_message_from_bot(message: types.Message):
	await message.bot.send_message(config.groups.main, utils.remove_prefix(message.text, "!msg "))


@dp.message_handler(user_id = int(config.bot.owner), commands="log", commands_prefix="!/")
async def cmd_write_log_bot(message: types.Message):
	await utils.write_log(message.bot, utils.remove_prefix(message.text, "!log "), "test")


@dp.message_handler(is_admin=True, commands="ping", commands_prefix="!")
async def cmd_ping_bot(message: types.Message):
	# Check if command is sent by group admin
	user = await message.bot.get_chat_member(config.groups.main, message.from_user.id)
	if user.is_chat_admin():

		ram = psutil.virtual_memory()

		reply = f"<b>{random.choice(['👊 Самурай на месте!', '🫰 Нужно больше золота', '🫡 Тута я, бож :3', '✊ Железо говн@, но я держусь!'])}</b>\n\n"
		reply += "<b>CPU:</b> <i>{} ядро ({} MHz) загружено на {}%</i>\n".format(
			psutil.cpu_count(),
			int(utils.get_cpu_freq_from_proc()),
			psutil.cpu_percent()
		)
		reply += "<b>RAM:</b> <i>{}ГБ / {}ГБ</i>\n".format(
			ram.used >> 20,
			ram.total >> 20
		)
		reply += "<b>GPU:</b> <i>N/A</i>\n"

		# Get disk info for root partition
		disk = psutil.disk_usage('/')
		# Convert bytes to GB
		disk_total_gb = disk.total // (2 ** 30)  # or (1024**3)
		disk_free_gb = disk.free // (2 ** 30)

		reply += "<b>SSD:</b> <i>{}гб / {}гб ({}% занято)</i>\n".format(
			disk_free_gb,
			disk_total_gb,
			int(disk.percent)
		)

		reply += "\n<b>Версия бота:</b> <i>" + str(config.bot.version) + " codename «<b>" + config.bot.version_codename + "</b>»</i>"

		await message.reply(reply)


# @dp.message_handler(lambda message: message.chat.type == 'private', commands=["prof", "мат"], commands_prefix="!")
@dp.message_handler(is_admin=True, commands=["prof", "мат"], commands_prefix="!")
@dp.message_handler(lambda message: message.chat.type == 'private', is_owner=True, commands=["prof", "мат"], commands_prefix="!")
async def cmd_profanity_check(message: types.Message):
	# Check if command is sent by group admin
	user = await message.bot.get_chat_member(config.groups.main, message.from_user.id)
	if user.is_chat_admin():
		_del = False
		_word = None
		_pat = None

		line_info_ru = censor_ru.clean_line(utils.remove_prefix(message.text, "!prof "))
		line_info_en = censor_en.clean_line(utils.remove_prefix(message.text, "!prof "))

		# line, bad_words_count, bad_phrases_count, detected_bad_words, detected_bad_phrases

		_det_lang = None

		# check RU
		if line_info_ru[1] or line_info_ru[2]:
			if line_info_ru[1]:
				_word = line_info_ru[3][0]
			else:
				_word = line_info_ru[4][0]

			_pat = line_info_ru[5][0]
			_del = True
			_det_lang = 'ru'

		# check ENG
		if line_info_en[1] or line_info_en[2]:
			if line_info_en[1]:
				_word = line_info_en[3][0]
			else:
				_word = line_info_en[4][0]

			_pat = line_info_en[5][0]
			_del = True
			_det_lang = 'en'

		# process
		if _del:
			log_msg = message.text
			if _word:
				log_msg = "❌ Profanity detected.\n\n"
				log_msg += utils.remove_prefix(message.text, "!prof ").replace(_word, '<u><b>'+_word+'</b></u>')
				log_msg += "\nПаттерн: " + _pat
				log_msg += "\nЯзык: " + _det_lang

			await message.reply(log_msg)
		else:
			await message.reply("✅ No profanity detected.")
