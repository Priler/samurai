from time import time
from aiogram import types, exceptions
from configurator import config
from dispatcher import dp
import localization
import utils
import psutil

import sys
sys.path.append("./censure")  # allow module import from git submodule

from censure import Censor


censor_ru = Censor.get(lang='ru')
censor_en = Censor.get(lang='en')


@dp.message_handler(commands='start')
async def on_start(message: types.Message):
	user = await message.bot.get_chat_member(
		config.groups.main, message.from_user.id
	)

	if user.is_chat_admin():
		return await message.reply(
			f'Привет, {message.from_user.first_name}!\n'
			'Я S么MUR么I создан для ХО чата.\n'
			'Вижу ты админ✅, в чате когото нужно забанить?\n!ban @somebody'
		)
	elif user.is_chat_creator():
		return await message.reply(
			'Здраствуйте, мой Господин...\n Вам что-то нужно?'
		)

	
@dp.message_handler(commands='ban', commands_prefix='!/')
async def ban_current_user(message: types.Message):
	user = await message.bot.get_chat_member(
		config.groups.main, 
		message.from_user.id
	)
	
	if user.is_chat_admin() or user.is_chat_creator():
		split_message = message.text.split()
		user_id = split_message[-1]

		if len(split_message) == 2 and user_id.isdigit():
			try:
				await message.bot.kick_chat_member(config.groups.main, int(user_id))

				return await message.reply(
					f'Пользователь с ID:{user_id} забанен!👊'
				)
			except exceptions.InvalidUserId:
				return await message.reply('User id не корректен!❌')
			except exceptions.ChatAdminRequired:
				return await message.reply('Жалко конечно, но нельзя забанить админа...❌')
		return await message.reply('Комманда не корректна.❌')

	
@dp.message_handler(commands='unban', commands_prefix='!/')
async def ban_current_user(message: types.Message):
	user = await message.bot.get_chat_member(
		config.groups.main, 
		message.from_user.id
	)
	
	if user.is_chat_admin() or user.is_chat_creator():
		split_message = message.text.split()
		user_id = split_message[-1]

		if len(split_message) == 2 and user_id.isdigit():
			try:
				await message.bot.unban_chat_member(config.groups.main, int(user_id))

				return await message.reply(
					f'Пользователь с ID:{user_id} разбанен!✅'
				)
			except exceptions.InvalidUserId:
				return await message.reply(f'User id не корректен!❌')
		return await message.reply('Комманда не корректна.❌')


@dp.message_handler(user_id = int(config.bot.owner), commands="msg", commands_prefix="!/")
async def cmd_message_from_bot(message: types.Message):
	await message.bot.send_message(config.groups.main, utils.remove_prefix(message.text, "!msg "))


@dp.message_handler(user_id = int(config.bot.owner), commands="log", commands_prefix="!/")
async def cmd_write_log_bot(message: types.Message):
	await utils.write_log(message.bot, utils.remove_prefix(message.text, "!log "), "test")


@dp.message_handler(commands="ping", commands_prefix="!")
async def cmd_ping_bot(message: types.Message):
	# Check if command is sent by group admin
	user = await message.bot.get_chat_member(config.groups.main, message.from_user.id)
	if user.is_chat_admin():

		ram = psutil.virtual_memory()

		reply = "<b>👊 Up & Running!</b>\n\n"
		reply += "<b>CPU:</b> <i>" + str(psutil.cpu_count()) + " cores (" + str(psutil.cpu_freq().max) + "MHz) with " + str(psutil.cpu_percent()) + "% current usage</i>\n"
		reply += "<b>RAM:</b> <i>" + str(ram.used >> 20) +"mb / "+ str(ram.total >> 20) + "mb</i>\n";

		reply += "\n<b>Bot version:</b> <i>" + str(config.bot.version) + " codename «<b>" + config.bot.version_codename + "</b>»</i> 🌚"

		await message.reply(reply)


@dp.message_handler(commands="prof", commands_prefix="!")
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

		# check RU
		if line_info_ru[1] or line_info_ru[2]:
			if line_info_ru[1]:
				_word = line_info_ru[3][0]
			else:
				_word = line_info_ru[4][0]

			_pat = line_info_ru[5][0]
			_del = True

		# check ENG
		if line_info_en[1] or line_info_en[2]:
			if line_info_en[1]:
				_word = line_info_en[3][0]
			else:
				_word = line_info_en[4][0]

			_pat = line_info_en[5][0]
			_del = True

		# process
		if _del:
			log_msg = message.text
			if _word:
				log_msg = "❌ Profanity detected.\n\n"
				log_msg += utils.remove_prefix(message.text, "!prof ").replace(_word, '<u><b>'+_word+'</b></u>')
				log_msg += "\nПаттерн: " + _pat

			await message.reply(log_msg)
		else:
			await message.reply("✅ No profanity detected.")
