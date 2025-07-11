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

REMINDER_REPEAT_MINUTES = 20   # через 20 хвилин повторити нагадування
ADMIN_NOTIFY_MINUTES = 30      # через 30 хвилин адміну
ADMIN_IDS = [438830182]        # <-- свій Telegram ID

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

# --- Reply меню користувача ---
user_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Розпочати день")],
        [types.KeyboardButton(text="Створити нагадування")],
        [types.KeyboardButton(text="Список моїх завдань")],
        [types.KeyboardButton(text="Назад")],
        [types.KeyboardButton(text="Завершити день")]
    ],
    resize_keyboard=True
)

# ==== Дата та сьогодні ====
def now_ua():
    return datetime.now(timezone.utc).astimezone(UA_TZ)

def get_today():
    return now_ua().strftime('%Y-%m-%d')

# === Копіювання шаблонів у "Завдання на день" ===
def copy_template_blocks_to_today(blocks_count):
    records = template_sheet.get_all_records()
    today = get_today()
    # Якщо вже є рядки на сьогодні і цю кількість блоків — не копіюємо
    existing = day_sheet.get_all_records()
    for row in existing:
        if str(row["Дата"]) == today and str(row["Кількість блоків"]) == str(blocks_count):
            return
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
                row.get("Опис", ""),
                "",  # Telegram ID
                "",  # Імʼя
                "",  # Виконано
            ])
    if new_rows:
        day_sheet.append_rows(new_rows, value_input_option='USER_ENTERED')

def get_blocks_for_today():
    today = get_today()
    records = day_sheet.get_all_records()
    return sorted(list(set(str(row["Блок"]) for row in records if str(row["Дата"]) == today)))

def get_tasks_for_block(block_num, user_id=None):
    today = get_today()
    records = day_sheet.get_all_records()
    tasks = [
        {
            "row": idx + 2,
            "task": row["Завдання"],
            "reminder": row["Нагадування"],
            "time": row["Час"],
            "done": row.get("Виконано", ""),
            "block": row["Блок"]
        }
        for idx, row in enumerate(records)
        if str(row["Дата"]) == today and str(row["Блок"]) == str(block_num)
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
            day_sheet.update_cell(i+2, 9, name)          # Імʼя
    user_sessions[user_id] = block_num

def mark_task_done(row):
    day_sheet.update_cell(row, 10, "TRUE")  # 10 — Виконано

# ==== Inline-нагадування ====
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def send_reminder(user_id, task, reminder, row):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Виконано', callback_data=f'done_{row}')]
        ]
    )
    await bot.send_message(
        user_id,
        f"Завдання: {task}\nНагадування: {reminder}\n\nСтатус виконання: <b>нагадування надійшло</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    user_sessions[user_id] = row

@dp.callback_query(F.data.startswith('done_'))
async def done_callback(call: types.CallbackQuery):
    row = int(call.data.split('_')[1])
    mark_task_done(row)
    await call.message.edit_text(
        call.message.text.replace("нагадування надійшло", "Успішне"),
        reply_markup=None,
        parse_mode="HTML"
    )
    await call.answer("Відмічено як виконане ✅")

# ==== Повторне нагадування через 20 хвилин ====
async def repeat_reminder_if_needed(user_id, row, task, reminder, block):
    value = day_sheet.cell(row, 10).value  # "Виконано"
    if value != "TRUE":
        await bot.send_message(
            user_id,
            f"⏰ Завдання досі не виконано:\n\n"
            f"Блок {block}\n"
            f"Завдання: {task}\n"
            f"Нагадування: {reminder}\n\n"
            f"Не забудь натиснути «✅ Виконано»!",
            reply_markup=user_menu
        )

# ==== Повідомлення адміну через 30 хвилин ====
async def notify_admin_if_needed(user_id, row, task, reminder, block):
    value = day_sheet.cell(row, 10).value  # "Виконано"
    if value != "TRUE":
        try:
            user = await bot.get_chat(user_id)
            username = user.username or user.full_name or str(user_id)
        except Exception:
            username = str(user_id)
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                f"❗️ <b>Завдання НЕ виконано!</b>\n"
                f"Користувач: @{username} (ID: {user_id})\n"
                f"Блок: {block}\n"
                f"Завдання: {task}\n"
                f"Нагадування: {reminder}",
                parse_mode="HTML"
            )

def schedule_reminders_for_user(user_id, tasks):
    for t in tasks:
        if not t["time"]:
            continue
        remind_time = datetime.strptime(f"{get_today()} {t['time']}", '%Y-%m-%d %H:%M').replace(tzinfo=UA_TZ)
        now = now_ua()
        if remind_time <= now:
            continue
        block = t.get("block") or t.get("Блок") or "?"
        # Основне нагадування
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=remind_time,
            args=[user_id, t["task"], t["reminder"], t["row"]],
            id=f"{user_id}-{t['row']}-{int(remind_time.timestamp())}",
            replace_existing=True
        )
        # Повторне нагадування через 20 хв
        scheduler.add_job(
            repeat_reminder_if_needed,
            'date',
            run_date=remind_time + timedelta(minutes=REMINDER_REPEAT_MINUTES),
            args=[user_id, t["row"], t["task"], t["reminder"], block],
            id=f"repeat-{user_id}-{t['row']}-{int(remind_time.timestamp())}",
            replace_existing=True
        )
        # Адміну через 30 хв
        scheduler.add_job(
            notify_admin_if_needed,
            'date',
            run_date=remind_time + timedelta(minutes=ADMIN_NOTIFY_MINUTES),
            args=[user_id, t["row"], t["task"], t["reminder"], block],
            id=f"admin-{user_id}-{t['row']}-{int(remind_time.timestamp())}",
            replace_existing=True
        )

# === Обробники aiogram ===

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Вітаю! Натисніть «Розпочати день» щоб вибрати кількість блоків.",
        reply_markup=user_menu
    )

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
    today = get_today()
    records = day_sheet.get_all_records()
    for rec in records:
        if str(rec["Дата"]) == today and str(rec["Блок"]) == str(block_num) and rec["Telegram ID"]:
            if str(rec["Telegram ID"]) == str(user_id):
                await message.answer("Цей блок вже закріплений за вами.", reply_markup=user_menu)
                return
            else:
                await message.answer("Цей блок вже зайнятий іншим працівником.", reply_markup=user_menu)
                return
    await assign_user_to_block(block_num, user_id)
    await message.answer(f"Супер! Твої нагадування на сьогодні в блоці {block_num} 👇", reply_markup=user_menu)
    tasks = get_tasks_for_block(block_num)
    if not tasks:
        await message.answer("Завдань не знайдено для цього блоку.", reply_markup=user_menu)
        return
    tasks_text = "\n".join([f"— {t['time']}: {t['reminder']}" for t in tasks if t["time"]])
    await message.answer(
        f"Я буду нагадувати тобі про кожне завдання у потрібний час. Ось твій список нагадувань:\n\n{tasks_text}",
        reply_markup=user_menu
    )
    schedule_reminders_for_user(user_id, tasks)

# --- Навігаційне меню користувача ---
@dp.message(lambda msg: msg.text == "Список моїх завдань")
async def my_tasks(message: types.Message):
    user_id = message.from_user.id
    today = get_today()
    records = day_sheet.get_all_records()
    my_tasks = [
        row for row in records
        if str(row.get("Дата")) == today and str(row.get("Telegram ID")) == str(user_id)
    ]
    if not my_tasks:
        await message.answer("У вас немає завдань на сьогодні.", reply_markup=user_menu)
        return

    text = "<b>Ваші завдання на сьогодні:</b>\n"
    for row in my_tasks:
        status = "✅" if row.get("Виконано") == "TRUE" else "❌"
        time = row.get("Час") or ""
        task = row.get("Завдання") or ""
        reminder = row.get("Нагадування") or ""
        text += f"— {time}: {task} | {reminder} {status}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=user_menu)

@dp.message(F.text == "Створити нагадування")
async def create_custom_reminder(message: types.Message):
    await message.answer("🛠 Функція створення власного нагадування незабаром буде доступна!", reply_markup=user_menu)

@dp.message(F.text == "Назад")
async def go_back(message: types.Message):
    await message.answer("⬅️ Повернулись до меню.", reply_markup=user_menu)

@dp.message(lambda msg: msg.text == "Завершити день")
async def finish_day(message: types.Message):
    user_id = message.from_user.id
    today = get_today()
    records = day_sheet.get_all_records()
    updated = 0
    for idx, row in enumerate(records):
        if str(row.get("Дата")) == today and str(row.get("Telegram ID")) == str(user_id):
            if not row.get("Виконано") or row.get("Виконано") not in ["TRUE", "✅"]:
                # Встановлюємо статус як FALSE для невиконаних
                day_sheet.update_cell(idx + 2, 10, "FALSE")
                updated += 1
    await message.answer("Робочий день завершено! Виконання або невиконання завдання зафіксовано.", reply_markup=user_menu)

# --- Тут можуть бути інші адмін-меню/фічі ---

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
