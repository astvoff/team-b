import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Завантаження .env
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SHEET_KEY = os.getenv('SHEET_KEY')

logging.basicConfig(level=logging.INFO)

# Google Sheets авторизація
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs = gspread.authorize(creds)
sheet = gs.open_by_key(SHEET_KEY).worksheet('Tasks')  # Точно має бути Tasks, або заміни тут

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
user_sessions = {}

# === ЧАС УКРАЇНИ ===
def now_ua():
    # Повертає поточний час у Києві (UTC+3)
    return datetime.now(timezone.utc) + timedelta(hours=3)

def get_today():
    # Формат YYYY-MM-DD
    return now_ua().strftime('%Y-%m-%d')

def get_blocks_count():
    try:
        records = sheet.get_all_records()
        today = get_today()
        blocks = set()
        for rec in records:
            if str(rec["Дата"]) == today:
                blocks.add(str(rec["Блок"]))
        return sorted(list(blocks), key=lambda x: int(x)) if blocks else ["1", "2", "3"]
    except Exception as e:
        print("DEBUG get_blocks_count error:", e)
        return ["1", "2", "3"]

def get_block_tasks(block, user_id):
    records = sheet.get_all_records()
    today = get_today()
    tasks = []
    for rec in records:
        if str(rec["Дата"]) == today and str(rec["Блок"]) == str(block):
            tasks.append({
                "row": records.index(rec)+2,
                "time": rec["Час"],
                "task": rec["Завдання"],
                "desc": rec["Опис"],
                "done": rec["Виконано"],
            })
    return tasks

def assign_user_to_block(block, user_id):
    records = sheet.get_all_records()
    today = get_today()
    for i, rec in enumerate(records):
        if str(rec["Дата"]) == today and str(rec["Блок"]) == str(block):
            sheet.update_cell(i+2, 3, str(user_id))

def mark_task_done(row):
    sheet.update_cell(row, 7, "TRUE")

async def send_reminder(user_id, task, desc, row):
    print(f"DEBUG: Sending reminder for user_id={user_id}, task={task}")
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text='✅ Виконано')]],
        resize_keyboard=True
    )
    await bot.send_message(
        user_id,
        f"Нагадування: {task}\n\n{desc}\n\nПісля виконання натисни «✅ Виконано».",
        reply_markup=kb
    )
    user_sessions[user_id] = row

def schedule_reminders_for_user(user_id, block_num, tasks):
    for task in tasks:
        remind_time = datetime.strptime(f"{get_today()} {task['time']}", '%Y-%m-%d %H:%M')
        now = now_ua()
        print(f"DEBUG: Reminder set for {remind_time}, now: {now}")
        if remind_time <= now:
            print("DEBUG: Time has passed, skip.")
            continue
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=remind_time,
            args=[user_id, task["task"], task["desc"], task["row"]],
            id=f"{user_id}-{task['row']}-{int(remind_time.timestamp())}",
            replace_existing=True
        )

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text='Розпочати день')]],
        resize_keyboard=True
    )
    await message.answer("Вітаю! Натисніть «Розпочати день» щоб вибрати свій блок.", reply_markup=kb)

@dp.message(lambda msg: msg.text and msg.text.strip().lower() == 'розпочати день')
async def choose_blocks(message: types.Message):
    blocks = get_blocks_count()
    if not blocks:
        await message.answer("Немає доступних блоків на сьогодні.")
        return
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=f"{b} блок")] for b in blocks],
        resize_keyboard=True
    )
    await message.answer(f"Скільки блоків сьогодні працює? Обери свій блок:", reply_markup=kb)

@dp.message(F.text.regexp(r'^\d+ блок$'))
async def select_block(message: types.Message):
    block_num = message.text.split()[0]
    user_id = message.from_user.id
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
    await message.answer(f"Супер! Твої задачі на сьогодні в блоці {block_num} 👇", reply_markup=types.ReplyKeyboardRemove())

    tasks = get_block_tasks(block_num, user_id)
    if not tasks:
        await message.answer("Завдань не знайдено для цього блоку.")
        return
    tasks_text = "\n".join([f"— {t['time']}: {t['task']} ({t['desc']})" for t in tasks])
    await message.answer(f"Я буду нагадувати тобі про кожне завдання у потрібний час. Ось твій список:\n\n{tasks_text}")

    schedule_reminders_for_user(user_id, block_num, tasks)

@dp.message(F.text == '✅ Виконано')
async def mark_done(message: types.Message):
    user_id = message.from_user.id
    row = user_sessions.get(user_id)
    if not row:
        await message.answer("Помилка: завдання не знайдено.")
        return
    mark_task_done(row)
    await message.answer("Відмічено як виконане ✅", reply_markup=types.ReplyKeyboardRemove())
    user_sessions[user_id] = None

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
