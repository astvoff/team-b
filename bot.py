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

# === Константи та ініціалізація ===
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SHEET_KEY = os.getenv('SHEET_KEY')
UA_TZ = timezone(timedelta(hours=3))  # Київ

logging.basicConfig(level=logging.INFO)

# Авторизація Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs = gspread.authorize(creds)

TEMPLATE_SHEET = 'Шаблони блоків'
DAY_SHEET = 'Завдання на день'
template_sheet = gs.open_by_key(SHEET_KEY).worksheet(TEMPLATE_SHEET)
day_sheet = gs.open_by_key(SHEET_KEY).worksheet(DAY_SHEET)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
user_sessions = {}  # user_id: block_num

def now_ua():
    return datetime.now(timezone.utc).astimezone(UA_TZ)

def get_today():
    return now_ua().strftime('%Y-%m-%d')

# === Копіювання шаблонів у "Завдання на день" ===
def copy_template_blocks_to_today(blocks_count):
    records = template_sheet.get_all_records()
    today = get_today()
    # Перевіряємо: якщо вже є рядки на сьогодні і цю кількість блоків — не копіюємо вдруге
    existing = day_sheet.get_all_records()
    for row in existing:
        if str(row["Дата"]) == today and str(row["Кількість блоків"]) == str(blocks_count):
            return  # Уже є, не копіюємо
    # Копіюємо
    new_rows = []
    for row in records:
        if str(row["Кількість блоків"]) == str(blocks_count):
            new_rows.append([
                today,  # Дата
                row["Кількість блоків"],
                row["Блок"],
                row["Завдання"],
                row["Нагадування"],
                row["Час"],
                row.get("Опис", ""),  # опціонально
                "",  # Telegram ID
                "",  # Виконано
            ])
    if new_rows:
        day_sheet.append_rows(new_rows, value_input_option='USER_ENTERED')

# === Отримати список блоків на сьогодні ===
def get_blocks_for_today():
    today = get_today()
    records = day_sheet.get_all_records()
    return sorted(list(set(str(row["Блок"]) for row in records if str(row["Дата"]) == today)))

# === Отримати всі завдання для блоку (для цього юзера на сьогодні) ===
def get_tasks_for_block(block_num):
    today = get_today()
    records = day_sheet.get_all_records()
    return [
        {
            "row": idx + 2,  # для update_cell (1-based)
            "task": row["Завдання"],
            "reminder": row["Нагадування"],
            "time": row["Час"],
            "done": row["Виконано"],
        }
        for idx, row in enumerate(records)
        if str(row["Дата"]) == today and str(row["Блок"]) == str(block_num)
    ]

# === Прив'язати користувача до блоку ===
def assign_user_to_block(block_num, user_id):
    today = get_today()
    records = day_sheet.get_all_records()
    for i, row in enumerate(records):
        if str(row["Дата"]) == today and str(row["Блок"]) == str(block_num) and not row["Telegram ID"]:
            day_sheet.update_cell(i+2, 8, str(user_id))  # 8 — Telegram ID
    user_sessions[user_id] = block_num

# === Відмітити нагадування як виконане ===
def mark_task_done(row):
    day_sheet.update_cell(row, 9, "TRUE")  # 9 — Виконано

# === Нагадування користувачу ===
async def send_reminder(user_id, task, reminder, row):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text='✅ Виконано')]],
        resize_keyboard=True
    )
    await bot.send_message(
        user_id,
        f"Завдання: {task}\nНагадування: {reminder}\n\nПісля виконання натисни «✅ Виконано».",
        reply_markup=kb
    )
    user_sessions[user_id] = row

def schedule_reminders_for_user(user_id, tasks):
    for t in tasks:
        if not t["time"]:
            continue  # пропустити без часу
        remind_time = datetime.strptime(f"{get_today()} {t['time']}", '%Y-%m-%d %H:%M').replace(tzinfo=UA_TZ)
        now = now_ua()
        if remind_time <= now:
            continue  # Час минув
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=remind_time,
            args=[user_id, t["task"], t["reminder"], t["row"]],
            id=f"{user_id}-{t['row']}-{int(remind_time.timestamp())}",
            replace_existing=True
        )

# === aiogram обробники ===

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text='Розпочати день')]],
        resize_keyboard=True
    )
    await message.answer("Вітаю! Натисніть «Розпочати день» щоб вибрати кількість блоків.", reply_markup=kb)

@dp.message(lambda msg: msg.text and msg.text.strip().lower() == 'розпочати день')
async def choose_blocks_count(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text='6'), types.KeyboardButton(text='7')],
            [types.KeyboardButton(text='8'), types.KeyboardButton(text='9')]
        ],
        resize_keyboard=True
    )
    await message.answer("Оберіть кількість блоків на сьогодні:", reply_markup=kb)

@dp.message(F.text.in_(['6', '7', '8', '9']))
async def on_blocks_count_chosen(message: types.Message):
    blocks_count = message.text.strip()
    copy_template_blocks_to_today(blocks_count)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=f"{b} блок")] for b in get_blocks_for_today()],
        resize_keyboard=True
    )
    await message.answer(f"Оберіть свій блок:", reply_markup=kb)

@dp.message(F.text.regexp(r'^\d+ блок$'))
async def select_block(message: types.Message):
    block_num = message.text.split()[0]
    user_id = message.from_user.id
    # Перевірити чи блок вже зайнятий
    today = get_today()
    records = day_sheet.get_all_records()
    for rec in records:
        if str(rec["Дата"]) == today and str(rec["Блок"]) == str(block_num) and rec["Telegram ID"]:
            if str(rec["Telegram ID"]) == str(user_id):
                await message.answer("Цей блок вже закріплений за вами.")
                return
            else:
                await message.answer("Цей блок вже зайнятий іншим працівником.")
                return
    # Прив'язуємо
    assign_user_to_block(block_num, user_id)
    await message.answer(f"Супер! Твої нагадування на сьогодні в блоці {block_num} 👇", reply_markup=types.ReplyKeyboardRemove())

    tasks = get_tasks_for_block(block_num)
    if not tasks:
        await message.answer("Завдань не знайдено для цього блоку.")
        return
    tasks_text = "\n".join([f"— {t['time']}: {t['reminder']}" for t in tasks if t["time"]])
    await message.answer(f"Я буду нагадувати тобі про кожне завдання у потрібний час. Ось твій список нагадувань:\n\n{tasks_text}")

    schedule_reminders_for_user(user_id, tasks)

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
