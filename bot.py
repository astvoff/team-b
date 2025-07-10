import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Logging
logging.basicConfig(level=logging.INFO)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs = gspread.authorize(creds)
SHEET_NAME = 'Tasks'
sheet = gs.open(SHEET_NAME).sheet1

# Init bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Store user session data
user_sessions = {}

# --- Helper Functions --- #

def get_today():
    return datetime.now().strftime('%Y-%m-%d')

def get_blocks_count():
    # повертає максимальне значення блока за сьогодні
    records = sheet.get_all_records()
    today = get_today()
    blocks = {str(rec["Блок"]) for rec in records if str(rec["Дата"]) == today}
    return sorted(list(blocks))

def get_block_tasks(block, user_id):
    records = sheet.get_all_records()
    today = get_today()
    tasks = []
    for rec in records:
        if str(rec["Дата"]) == today and str(rec["Блок"]) == str(block):
            tasks.append({
                "row": records.index(rec)+2,  # +2 бо get_all_records не враховує заголовки
                "time": rec["Час"],
                "task": rec["Завдання"],
                "desc": rec["Опис"],
                "done": rec["Виконано"],
            })
    return tasks

def assign_user_to_block(block, user_id):
    # Записує Telegram ID у всі завдання блоку на сьогодні
    records = sheet.get_all_records()
    today = get_today()
    for i, rec in enumerate(records):
        if str(rec["Дата"]) == today and str(rec["Блок"]) == str(block):
            sheet.update_cell(i+2, 3, str(user_id)) # колонка 3 - Telegram ID

def mark_task_done(row):
    # Позначає завдання як виконане (TRUE) по row
    sheet.update_cell(row, 7, "TRUE") # колонка 7 - Виконано

def get_block_for_user(user_id):
    records = sheet.get_all_records()
    today = get_today()
    for rec in records:
        if str(rec["Дата"]) == today and str(rec["Telegram ID"]) == str(user_id):
            return rec["Блок"]
    return None

# --- Bot Handlers --- #

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton('Розпочати день'))
    await message.answer("Вітаю! Натисніть «Розпочати день» щоб вибрати свій блок.", reply_markup=kb)

@dp.message(lambda msg: msg.text == 'Розпочати день')
async def choose_blocks(message: types.Message):
    blocks = get_blocks_count()
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for b in blocks:
        kb.add(KeyboardButton(f"{b} блок"))
    await message.answer(f"Скільки блоків сьогодні працює? Обери свій блок:", reply_markup=kb)

@dp.message(lambda msg: msg.text and msg.text.endswith('блок'))
async def select_block(message: types.Message):
    block_num = message.text.split()[0]
    user_id = message.from_user.id

    # Перевірка, чи блок вже зайнятий
    records = sheet.get_all_records()
    today = get_today()
    for rec in records:
        if str(rec["Дата"]) == today and str(rec["Блок"]) == block_num and rec["Telegram ID"]:
            if str(rec["Telegram ID"]) == str(user_id):
                await message.answer("Цей блок вже закріплений за вами.")
                return
            else:
                await message.answer("Цей блок вже зайнятий іншим працівником.")
                return

    assign_user_to_block(block_num, user_id)
    user_sessions[user_id] = block_num
    await message.answer(f"Супер! Твої задачі на сьогодні в блоці {block_num} 👇", reply_markup=ReplyKeyboardRemove())

    tasks = get_block_tasks(block_num, user_id)
    tasks_text = "\n".join([f"— {t['time']}: {t['task']} ({t['desc']})" for t in tasks])
    await message.answer(f"Я буду нагадувати тобі про кожне завдання у потрібний час. Ось твій список:\n\n{tasks_text}")

    # Запускаємо нагадування для цього юзера
    schedule_reminders_for_user(user_id, block_num, tasks)

def schedule_reminders_for_user(user_id, block_num, tasks):
    for task in tasks:
        remind_time = datetime.strptime(f"{get_today()} {task['time']}", '%Y-%m-%d %H:%M')
        if remind_time < datetime.now():
            continue  # не надсилати, якщо час вже минув
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=remind_time,
            args=[user_id, task["task"], task["desc"], task["row"]],
            id=f"{user_id}-{task['row']}",
            replace_existing=True
        )

async def send_reminder(user_id, task, desc, row):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton('✅ Виконано'))
    await bot.send_message(
        user_id,
        f"Нагадування: {task}\n\n{desc}\n\nПісля виконання натисни «✅ Виконано».",
        reply_markup=kb
    )
    # Зберігаємо row для відмітки виконання
    user_sessions[user_id] = row

@dp.message(lambda msg: msg.text == '✅ Виконано')
async def mark_done(message: types.Message):
    user_id = message.from_user.id
    row = user_sessions.get(user_id)
    if not row:
        await message.answer("Помилка: завдання не знайдено.")
        return
    mark_task_done(row)
    await message.answer("Відмічено як виконане ✅", reply_markup=ReplyKeyboardRemove())
    user_sessions[user_id] = None

# --- Main --- #
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())