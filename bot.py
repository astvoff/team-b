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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
class PersonalReminderState(StatesGroup):
    wait_type = State()
    wait_text = State()
    wait_time = State()
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

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

# admin 

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# --- Адмін-меню / команда ---
@dp.message(lambda msg: msg.text and (msg.text.strip().lower() == '/admin' or msg.text == 'Адмін-меню'))
async def admin_menu(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ лише для адміністратора.")
        return

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

admin_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Завдання на день")],
        [KeyboardButton(text="👁 Контроль виконання")],
        [KeyboardButton(text="🔄 Розблокувати блок")],
        [KeyboardButton(text="➕ Додати завдання у шаблон")],
        [KeyboardButton(text="✏️ Редагувати завдання")],
        [KeyboardButton(text="🛠 Інші налаштування")],
    ],
    resize_keyboard=True
)

# --- Перегляд завдань на сьогодні ---
@dp.callback_query(lambda c: c.data == "admin_tasks_today")
async def admin_tasks_today(call: types.CallbackQuery):
    records = day_sheet.get_all_records()
    today = get_today()
    text = "<b>Завдання на сьогодні:</b>\n"
    for row in records:
        if str(row["Дата"]) == today:
            status = "✅" if row.get("Виконано") == "TRUE" else "❌"
            who = f'({row["Telegram ID"]})' if row["Telegram ID"] else ""
            text += f'— <b>Блок {row["Блок"]}:</b> {row["Нагадування"]} {who} {status}\n'
    await call.message.answer(text or "На сьогодні немає завдань.", parse_mode="HTML")
    await call.answer()

# --- Контроль виконання ---
@dp.callback_query(lambda c: c.data == "admin_control_done")
async def admin_control_done(call: types.CallbackQuery):
    records = day_sheet.get_all_records()
    today = get_today()
    done, undone = [], []
    for row in records:
        if str(row["Дата"]) == today:
            status = "✅" if row.get("Виконано") == "TRUE" else "❌"
            who = f'({row["Telegram ID"]})' if row["Telegram ID"] else ""
            line = f'Блок {row["Блок"]}: {row["Нагадування"]} {who} {status}'
            (done if status == "✅" else undone).append(line)
    text = "<b>Виконані:</b>\n" + ("\n".join(done) if done else "Немає") + "\n\n"
    text += "<b>Невиконані:</b>\n" + ("\n".join(undone) if undone else "Немає")
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# --- Розблокувати блок (видалити Telegram ID з усіх завдань блоку на сьогодні) ---
@dp.callback_query(lambda c: c.data == "admin_unblock")
async def admin_unblock(call: types.CallbackQuery):
    blocks = get_blocks_for_today()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"Блок {b}", callback_data=f"unblock_{b}")] for b in blocks]
    )
    await call.message.answer("Оберіть блок для розблокування:", reply_markup=kb)
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("unblock_"))
async def do_unblock(call: types.CallbackQuery):
    block_num = call.data.replace("unblock_", "")
    today = get_today()
    records = day_sheet.get_all_records()
    for i, row in enumerate(records):
        if str(row["Дата"]) == today and str(row["Блок"]) == str(block_num):
            day_sheet.update_cell(i+2, 8, "")  # Telegram ID
    await call.message.answer(f"Блок {block_num} розблоковано.")
    await call.answer()

# --- Додати завдання у шаблон ---
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class AddTemplateState(StatesGroup):
    wait_blocks = State()
    wait_block_num = State()
    wait_task = State()
    wait_reminder = State()
    wait_time = State()

@dp.callback_query(lambda c: c.data == "admin_add_template")
async def admin_add_template_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Вкажіть кількість блоків (6/7/8/9):")
    await state.set_state(AddTemplateState.wait_blocks)
    await call.answer()

@dp.message(AddTemplateState.wait_blocks)
async def admin_add_template_blocknum(message: types.Message, state: FSMContext):
    blocks = message.text.strip()
    if blocks not in ["6", "7", "8", "9"]:
        await message.answer("Введіть 6, 7, 8 або 9.")
        return
    await state.update_data(blocks=blocks)
    await message.answer("Вкажіть номер блоку (1, 2, ...):")
    await state.set_state(AddTemplateState.wait_block_num)

@dp.message(AddTemplateState.wait_block_num)
async def admin_add_template_task(message: types.Message, state: FSMContext):
    block_num = message.text.strip()
    await state.update_data(block_num=block_num)
    await message.answer("Введіть назву завдання:")
    await state.set_state(AddTemplateState.wait_task)

@dp.message(AddTemplateState.wait_task)
async def admin_add_template_reminder(message: types.Message, state: FSMContext):
    task = message.text.strip()
    await state.update_data(task=task)
    await message.answer("Введіть текст нагадування:")
    await state.set_state(AddTemplateState.wait_reminder)

@dp.message(AddTemplateState.wait_reminder)
async def admin_add_template_time(message: types.Message, state: FSMContext):
    reminder = message.text.strip()
    await state.update_data(reminder=reminder)
    await message.answer("Введіть час нагадування у форматі HH:MM (наприклад, 10:00):")
    await state.set_state(AddTemplateState.wait_time)

@dp.message(AddTemplateState.wait_time)
async def admin_add_template_finish(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    data = await state.get_data()
    # Додаємо рядок у шаблон!
    template_sheet.append_row([
        data["blocks"], data["block_num"], data["task"], data["reminder"], time_str, ""
    ])
    await message.answer("✅ Завдання додано у шаблон!")
    await state.clear()

# --- Редагування завдання (простий приклад: тільки нагадування/час) ---
class EditTaskState(StatesGroup):
    wait_block = State()
    wait_reminder = State()
    wait_time = State()
    wait_row_idx = State()

@dp.callback_query(lambda c: c.data == "admin_edit_task")
async def admin_edit_task_start(call: types.CallbackQuery, state: FSMContext):
    blocks = get_blocks_for_today()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"Блок {b}", callback_data=f"editblock_{b}")] for b in blocks]
    )
    await call.message.answer("Оберіть блок для редагування:", reply_markup=kb)
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("editblock_"))
async def edit_task_choose_reminder(call: types.CallbackQuery, state: FSMContext):
    block_num = call.data.replace("editblock_", "")
    today = get_today()
    records = day_sheet.get_all_records()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row['Нагадування']} ({row['Час']})", callback_data=f"editrow_{i+2}")]
            for i, row in enumerate(records)
            if str(row["Дата"]) == today and str(row["Блок"]) == block_num
        ]
    )
    await call.message.answer("Оберіть нагадування для редагування:", reply_markup=kb)
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("editrow_"))
async def edit_task_input_reminder(call: types.CallbackQuery, state: FSMContext):
    row_idx = int(call.data.replace("editrow_", ""))
    await state.update_data(row_idx=row_idx)
    await call.message.answer("Введіть новий текст нагадування:")
    await state.set_state(EditTaskState.wait_reminder)
    await call.answer()

@dp.message(EditTaskState.wait_reminder)
async def edit_task_input_time(message: types.Message, state: FSMContext):
    reminder = message.text.strip()
    await state.update_data(reminder=reminder)
    await message.answer("Введіть новий час (HH:MM):")
    await state.set_state(EditTaskState.wait_time)

@dp.message(EditTaskState.wait_time)
async def edit_task_save(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    data = await state.get_data()
    day_sheet.update_cell(data["row_idx"], 5, data["reminder"])  # "Нагадування"
    day_sheet.update_cell(data["row_idx"], 6, time_str)  # "Час"
    await message.answer("✅ Нагадування та час оновлено!")
    await state.clear()

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ лише для адміністратора.")
        return
    await message.answer("🔧 <b>Адмін-меню</b>", reply_markup=admin_menu_kb, parse_mode="HTML")

# --- Інші налаштування ---
@dp.callback_query(lambda c: c.data == "admin_other_settings")
async def admin_other_settings(call: types.CallbackQuery):
    await call.message.answer("🔧 У майбутньому тут будуть додаткові налаштування.")
    await call.answer()

# --- Reply меню користувача ---
user_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Розпочати день")],
        [types.KeyboardButton(text="Створити нагадування")],
        [types.KeyboardButton(text="Список моїх завдань")],
        [types.KeyboardButton(text='База знань')],
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

@dp.message(lambda msg: msg.text == "Створити нагадування")
async def create_reminder_start(message: types.Message, state: FSMContext):
    await message.answer("Вкажіть вид завдання (наприклад, 'Особисте', 'Для магазину' тощо):")
    await state.set_state(PersonalReminderState.wait_type)

@dp.message(PersonalReminderState.wait_type)
async def create_reminder_type(message: types.Message, state: FSMContext):
    await state.update_data(reminder_type=message.text.strip())
    await message.answer("Введіть текст нагадування:")
    await state.set_state(PersonalReminderState.wait_text)

@dp.message(PersonalReminderState.wait_text)
async def create_reminder_text(message: types.Message, state: FSMContext):
    await state.update_data(reminder_text=message.text.strip())
    await message.answer("Вкажіть час нагадування у форматі HH:MM (наприклад, 14:30):")
    await state.set_state(PersonalReminderState.wait_time)

@dp.message(PersonalReminderState.wait_time)
async def create_reminder_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    reminder_time = message.text.strip()
    user_id = message.from_user.id
    today = get_today()
    # Додаємо у Google Таблицю
    day_sheet.append_row([
        today, "", "", data["reminder_type"], data["reminder_text"], reminder_time, "", user_id, ""
    ])
    await message.answer(f"✅ Особисте нагадування встановлено на {reminder_time}!\n"
                         "Вам прийде повідомлення у зазначений час.", reply_markup=user_menu)
    await state.clear()

@dp.message(lambda msg: msg.text and msg.text.lower() == "база знань")
async def knowledge_base_placeholder(message: types.Message):
    await message.answer(
        "🗂 Функція 'База знань' незабаром стане доступною!\n"
        "Тут можна буде знаходити важливі посилання, інструкції, документи та іншу інформацію для роботи."
    )


    # Плануємо нагадування
    remind_dt = datetime.strptime(f"{get_today} {reminder_time}", '%Y-%m-%d %H:%M').replace(tzinfo=UA_TZ)
    scheduler.add_job(
        send_personal_reminder,
        'date',
        run_date=remind_dt,
        args=[user_id, data["reminder_type"], data["reminder_text"], reminder_time]
    )

async def send_personal_reminder(user_id, reminder_type, reminder_text, reminder_time):
    await bot.send_message(
        user_id,
        f"<b>Особисте нагадування!</b>\n"
        f"Вид: {reminder_type}\n"
        f"Текст: {reminder_text}\n"
        f"Час: {reminder_time}",
        parse_mode="HTML"
    )

# --- Тут можуть бути інші адмін-меню/фічі ---

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
