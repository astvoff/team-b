import os
import logging
import asyncio
import time  # ДОДАНО!
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

class ReminderFSM(StatesGroup):
    wait_text = State()
    wait_time = State()

class PollState(StatesGroup):
    waiting_question = State()
    waiting_options = State()
    waiting_type = State()
    waiting_target = State()
    waiting_username = State()
    waiting_datetime = State()
    confirm = State()

class ReportFSM(StatesGroup):
    waiting_date = State()
    
# --- Константи ---
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SHEET_KEY = os.getenv('SHEET_KEY')
UA_TZ = timezone(timedelta(hours=3))  # Київ
REMINDER_REPEAT_MINUTES = 20
ADMIN_NOTIFY_MINUTES = 30
ADMIN_IDS = [438830182]
logging.basicConfig(level=logging.INFO)

# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs = gspread.authorize(creds)
TEMPLATE_SHEET = 'Шаблони блоків'
DAY_SHEET = 'Завдання на день'
INFORMATION_BASE_SHEET = 'Інформаційна база'
STAFF_SHEET = "Штат"
GENERAL_REMINDERS_SHEET = 'Загальні нагадування'
POLL_SHEET = 'Опитування'
template_sheet = gs.open_by_key(SHEET_KEY).worksheet(TEMPLATE_SHEET)
day_sheet = gs.open_by_key(SHEET_KEY).worksheet(DAY_SHEET)
information_base_sheet = gs.open_by_key(SHEET_KEY).worksheet(INFORMATION_BASE_SHEET)
staff_sheet = gs.open_by_key(SHEET_KEY).worksheet(STAFF_SHEET)
general_reminders_sheet = gs.open_by_key(SHEET_KEY).worksheet(GENERAL_REMINDERS_SHEET)
poll_sheet = gs.open_by_key(SHEET_KEY).worksheet(POLL_SHEET)

# --- Telegram bot ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=UA_TZ)
user_sessions = {}

def now_ua():
    return datetime.now(timezone.utc).astimezone(UA_TZ)

def get_today():
    return now_ua().strftime('%Y-%m-%d')

def is_true(val):
    if isinstance(val, bool):
        return val is True
    if isinstance(val, str):
        return val.strip().lower() in ('true', 'yes', '1', 'y', 'так')
    return False

def copy_template_blocks_to_today(blocks_count):
    records = template_sheet.get_all_records()
    today = get_today()
    existing = day_sheet.get_all_records()
    # Перевіряємо, чи вже є завдання на сьогодні з цим blocks_count
    for row in existing:
        if str(row["Дата"]) == today and str(row["Кількість блоків"]) == str(blocks_count):
            return  # вже є — не додаємо
    # Додаємо нові рядки тільки для сьогоднішньої дати
    new_rows = []
    for row in records:
        if str(row["Кількість блоків"]) == str(blocks_count):
            new_rows.append([
                today, row["Кількість блоків"], row["Блок"], row["Завдання"],
                row["Нагадування"], row["Час"], row.get("Опис", ""),
                "", "", ""  # Telegram ID, Імʼя, Виконано
            ])
    if new_rows:
        prepend_rows_to_sheet(day_sheet, new_rows)

def get_blocks_for_today():
    today = get_today()
    records = day_sheet.get_all_records()
    # Додаємо фільтр, щоб порожні блоки не попадали у вибір
    return sorted(list(set(str(row["Блок"]) for row in records if str(row["Дата"]) == today and str(row["Блок"]).strip())))

def get_tasks_for_block(block_num, user_id=None):
    today = get_today()
    records = day_sheet.get_all_records()
    tasks = [
        {
            "row": idx + 2,
            "task": row["Завдання"],
            "reminder": row["Нагадування"],
            "desc": row.get("Опис", ""),
            "time": row["Час"],
            "done": row.get("Виконано", ""),
            "block": row["Блок"]
        }
        for idx, row in enumerate(records)
        if str(row.get("Дата")) == today and str(row.get("Блок")) == str(block_num)
           and (user_id is None or str(row.get("Telegram ID")) == str(user_id))
    ]
    return tasks

async def assign_user_to_block(block_num, user_id):
    today = get_today()
    records = day_sheet.get_all_records()
    user = await bot.get_chat(user_id)
    name = user.username or user.full_name or str(user_id)
    for i, row in enumerate(records):
        if str(row["Дата"]) == today and str(row["Блок"]) == str(block_num) and not row["Telegram ID"]:
            day_sheet.update_cell(i+2, 8, str(user_id))  # Telegram ID
            time.sleep(0.5)
            day_sheet.update_cell(i+2, 9, name)          # Імʼя
            time.sleep(0.5)
    user_sessions[user_id] = block_num

def mark_task_done(row):
    day_sheet.update_cell(row, 10, "TRUE")
    time.sleep(0.5)

async def send_reminder(user_id, task, reminder, row, idx=1):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text='✅ Виконано', callback_data=f'done_{row}_{idx}')]
        ]
    )
    await bot.send_message(
        user_id,
        f"Завдання: {task}\nНагадування: {reminder}\n\nСтатус виконання: <b>нагадування надійшло</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    user_sessions[user_id] = row

async def repeat_reminder_if_needed(user_id, row, task, reminder, block):
    value = day_sheet.cell(row, 10).value
    if value != "TRUE":
        await bot.send_message(
            user_id,
            f"⏰ Завдання досі не виконано:\n\n"
            f"Блок {block}\n"
            f"Завдання: {task}\n"
            f"Нагадування: {reminder}\n\n"
            f"Не забудь натиснути «✅ Виконано»!"
        )

async def notify_admin_if_needed(user_id, row, task, reminder, block):
    value = day_sheet.cell(row, 10).value
    if value != "TRUE":
        name = get_staff_name_by_id(user_id)
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                f"❗️ <b>Завдання НЕ виконано!</b>\n"
                f"Користувач: {name}\n"
                f"Блок: {block}\n"
                f"Завдання: {task}\n"
                f"Нагадування: {reminder}",
                parse_mode="HTML"
            )

@dp.callback_query(F.data.startswith('done_'))
async def done_callback(call: types.CallbackQuery):
    parts = call.data.split('_')
    row = int(parts[1])
    idx = int(parts[2])  # індекс нагадування
    # Визначаємо номер стовпця: 10 - 'Виконано', 11 - 'Виконано (2)', 12 - 'Виконано (3)' ...
    col = 10 + (idx - 1)
    day_sheet.update_cell(row, col, "TRUE")
    time.sleep(0.5)
    await call.message.edit_text(
        call.message.text.replace("нагадування надійшло", "Успішне"),
        reply_markup=None,
        parse_mode="HTML"
    )
    await call.answer("Відмічено як виконане ✅")

def schedule_reminders_for_user(user_id, tasks):
    for t in tasks:
        if not t["time"]:
            continue
        times = [tm.strip() for tm in t["time"].split(",") if tm.strip()]
        for i, time_str in enumerate(times):
            try:
                remind_time = datetime.strptime(f"{get_today()} {time_str}", '%Y-%m-%d %H:%M').replace(tzinfo=UA_TZ)
            except Exception:
                continue
            now = now_ua()
            if remind_time <= now:
                continue
            block = t.get("block") or t.get("Блок") or "?"
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time,
                args=[user_id, t["task"], t["reminder"], t["row"], i+1],
                id=f"{user_id}-{t['row']}-{i+1}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
                replace_existing=True
            )
            scheduler.add_job(
                repeat_reminder_if_needed,
                'date',
                run_date=remind_time + timedelta(minutes=REMINDER_REPEAT_MINUTES),
                args=[user_id, t["row"], t["task"], t["reminder"], block],
                id=f"repeat-{user_id}-{t['row']}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
                replace_existing=True
            )
            scheduler.add_job(
                notify_admin_if_needed,
                'date',
                run_date=remind_time + timedelta(minutes=ADMIN_NOTIFY_MINUTES),
                args=[user_id, t["row"], t["task"], t["reminder"], block],
                id=f"admin-{user_id}-{t['row']}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
                replace_existing=True
            )

def prepend_rows_to_sheet(sheet, rows):
    sheet.append_rows(rows, value_input_option='USER_ENTERED')
    time.sleep(0.5)

# --------
# (Тут решта коду не змінюється, затримку треба лише туди, де є .update_cell чи .append_rows чи .append_row)
# Якщо в тебе є свої кастомні функції для роботи з Google Sheets — став time.sleep(0.5) після кожного запису!
# --------

# --- Запуск ---
async def main():
    loop = asyncio.get_running_loop()
    schedule_general_reminders(loop)
    scheduler.start()
    schedule_all_block_tasks_for_today()
    schedule_polls()
    scheduler.add_job(
        refresh_block_tasks,
        'interval',
        hours=1,
        id="refresh-block-tasks",
        replace_existing=True
    )
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
