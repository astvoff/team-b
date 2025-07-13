import os
import logging
import asyncio
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
main_loop = None
from aiogram.fsm.state import State, StatesGroup


class AdminReminderFSM(StatesGroup):
    wait_type = State()
    wait_nick = State()
    wait_day = State()
    wait_time = State()
    wait_text = State()
    wait_repeat = State()
    wait_confirm = State()

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
template_sheet = gs.open_by_key(SHEET_KEY).worksheet(TEMPLATE_SHEET)
day_sheet = gs.open_by_key(SHEET_KEY).worksheet(DAY_SHEET)
information_base_sheet = gs.open_by_key(SHEET_KEY).worksheet(INFORMATION_BASE_SHEET)
staff_sheet = gs.open_by_key(SHEET_KEY).worksheet(STAFF_SHEET)
general_reminders_sheet = gs.open_by_key(SHEET_KEY).worksheet(GENERAL_REMINDERS_SHEET)


# --- Telegram бот ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=UA_TZ)
user_sessions = {}

# --- Reply клавіатури ---
user_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Розпочати день")],
        [types.KeyboardButton(text="Список моїх завдань"), types.KeyboardButton(text="Створити нагадування")],
        [types.KeyboardButton(text="Інформаційна база"), types.KeyboardButton(text="Завершити день")],
        [types.KeyboardButton(text="Відмінити дію")]
    ],
    resize_keyboard=True
)

admin_menu_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="📋 Завдання на день")],
        [types.KeyboardButton(text="➕ Додати нагадування")],
        [types.KeyboardButton(text="👁 Контроль виконання")],
        [types.KeyboardButton(text="🔄 Розблокувати блок")],
        [types.KeyboardButton(text="➕ Додати завдання у шаблон")],
        [types.KeyboardButton(text="✏️ Редагувати завдання")],
        [types.KeyboardButton(text="🛠 Інші налаштування")],
        [types.KeyboardButton(text="⬅️ Вихід до користувача")]
    ],
    resize_keyboard=True
)

# --- Сервісні функції ---
def now_ua():
    return datetime.now(timezone.utc).astimezone(UA_TZ)

def get_today():
    return now_ua().strftime('%Y-%m-%d')

def is_true(val):           # <-- Ось тут
    if isinstance(val, bool):
        return val is True
    if isinstance(val, str):
        return val.strip().lower() in ('true', 'yes', '1', 'y', 'так')
    return False

def copy_template_blocks_to_today(blocks_count):
    records = template_sheet.get_all_records()
    today = get_today()
    existing = day_sheet.get_all_records()
    for row in existing:
        if str(row["Дата"]) == today and str(row["Кількість блоків"]) == str(blocks_count):
            return
    new_rows = []
    for row in records:
        if str(row["Кількість блоків"]) == str(blocks_count):
            new_rows.append([
                today, row["Кількість блоків"], row["Блок"], row["Завдання"],
                row["Нагадування"], row["Час"], row.get("Опис", ""),
                "", "", ""  # Telegram ID, Імʼя, Виконано
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
    return [
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
    day_sheet.update_cell(row, 10, "TRUE")

# --- Inline-нагадування для задач ---
async def send_reminder(user_id, task, reminder, row):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text='✅ Виконано', callback_data=f'done_{row}')]
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

# --- Повторне нагадування і повідомлення адміну ---
async def repeat_reminder_if_needed(user_id, row, task, reminder, block):
    value = day_sheet.cell(row, 10).value
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

async def notify_admin_if_needed(user_id, row, task, reminder, block):
    value = day_sheet.cell(row, 10).value
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

DAYS = [
    "понеділок", "вівторок", "середа",
    "четвер", "пʼятниця", "субота", "неділя"
]

@dp.message(F.text == "➕ Додати нагадування")
async def admin_create_reminder(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Тільки для адміністратора")
        return
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Загальне"), types.KeyboardButton(text="Для зміни")],
            [types.KeyboardButton(text="Індивідуальне")],
            [types.KeyboardButton(text="Відміна")]
        ], resize_keyboard=True
    )
    await message.answer("Виберіть тип нагадування:", reply_markup=kb)
    await state.set_state(AdminReminderFSM.wait_type)

@dp.message(AdminReminderFSM.wait_type)
async def reminder_type_chosen(message: types.Message, state: FSMContext):
    if message.text == "Відміна":
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_menu_kb)
        return
    data = {"type": message.text}
    await state.update_data(**data)
    if message.text == "Індивідуальне":
        await message.answer("Введіть нікнейм користувача (без @):", reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(AdminReminderFSM.wait_nick)
    else:
        await ask_day(message, state)

@dp.message(AdminReminderFSM.wait_nick)
async def reminder_nick_chosen(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await ask_day(message, state)

async def ask_day(message, state):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=day.title())] for day in DAYS] + [[types.KeyboardButton(text="Відміна")]],
        resize_keyboard=True
    )
    await message.answer("Виберіть день:", reply_markup=kb)
    await state.set_state(AdminReminderFSM.wait_day)

@dp.message(AdminReminderFSM.wait_day)
async def reminder_day_chosen(message: types.Message, state: FSMContext):
    if message.text == "Відміна":
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_menu_kb)
        return
    if message.text.lower() not in DAYS:
        await message.answer("Будь ласка, оберіть день із клавіатури.")
        return
    await state.update_data(day=message.text.lower())
    await message.answer("Введіть час у форматі ГГ:ХХ (наприклад, 13:30):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AdminReminderFSM.wait_time)

@dp.message(AdminReminderFSM.wait_time)
async def reminder_time_chosen(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    try:
        _ = datetime.strptime(time_str, "%H:%M")
    except Exception:
        await message.answer("Невірний формат часу. Введіть у форматі ГГ:ХХ (наприклад, 09:25):")
        return
    await state.update_data(time=time_str)
    await message.answer("Введіть текст нагадування:")
    await state.set_state(AdminReminderFSM.wait_text)

@dp.message(AdminReminderFSM.wait_text)
async def reminder_text_chosen(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Щотижня"), types.KeyboardButton(text="Одноразове")],
            [types.KeyboardButton(text="Відміна")]
        ], resize_keyboard=True
    )
    await message.answer("Оберіть повторюваність:", reply_markup=kb)
    await state.set_state(AdminReminderFSM.wait_repeat)

@dp.message(AdminReminderFSM.wait_repeat)
async def reminder_repeat_chosen(message: types.Message, state: FSMContext):
    if message.text == "Відміна":
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_menu_kb)
        return
    if message.text not in ["Щотижня", "Одноразове"]:
        await message.answer("Оберіть варіант із клавіатури.")
        return
    await state.update_data(repeat=message.text)
    data = await state.get_data()
    confirm_text = (
        f"<b>Підтвердіть створення нагадування:</b>\n"
        f"Тип: <b>{data.get('type')}</b>\n"
        f"{'Нік: @' + data['username'] if data.get('username') else ''}\n"
        f"День: <b>{data['day'].title()}</b>\n"
        f"Час: <b>{data['time']}</b>\n"
        f"Текст: <b>{data['text']}</b>\n"
        f"Повтор: <b>{data['repeat']}</b>\n\n"
        "Підтвердити створення?"
    )
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Підтвердити"), types.KeyboardButton(text="Відміна")]
        ], resize_keyboard=True
    )
    await message.answer(confirm_text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(AdminReminderFSM.wait_confirm)

@dp.message(AdminReminderFSM.wait_confirm)
async def reminder_confirmed(message: types.Message, state: FSMContext):
    if message.text == "Відміна":
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_menu_kb)
        return
    data = await state.get_data()
    row = [
        data.get('day', ''),
        data.get('time', ''),
        data.get('text', ''),
        "TRUE" if data['type'] == "Загальне" else "",
        "TRUE" if data['type'] == "Для зміни" else "",
        "TRUE" if data['type'] == "Індивідуальне" else "",
        data.get('username', ''),
        data.get('repeat', ''),
    ]
    print(f"[DEBUG][append_row] row={row}")
    print(f"[DEBUG][sheet name] {general_reminders_sheet.title}")
    try:
        general_reminders_sheet.append_row(row, value_input_option='USER_ENTERED')
        print("[DEBUG][append_row] Успішно додано")
        await message.answer("✅ Нагадування успішно створено!", reply_markup=admin_menu_kb)
    except Exception as e:
        print(f"[ERROR][append_row] {e}")
        await message.answer(f"❌ Помилка при додаванні у таблицю: {e}", reply_markup=admin_menu_kb)
    await state.clear()

@dp.message(StateFilter('*'), F.text == "Відміна")
async def universal_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Дію скасовано.", reply_markup=admin_menu_kb)

def schedule_reminders_for_user(user_id, tasks):
    for t in tasks:
        if not t["time"]:
            continue
        times = [tm.strip() for tm in t["time"].split(",") if tm.strip()]
        for time_str in times:
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
                args=[user_id, t["task"], t["reminder"], t["row"]],
                id=f"{user_id}-{t['row']}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
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

# === FSM для створення особистого нагадування ===
class PersonalReminderState(StatesGroup):
    wait_text = State()
    wait_time = State()

@dp.message(F.text == "Створити нагадування")
async def create_reminder_start(message: types.Message, state: FSMContext):
    await message.answer("Введіть текст нагадування:")
    await state.set_state(PersonalReminderState.wait_text)

@dp.message(PersonalReminderState.wait_text)
async def reminder_got_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("Введіть час нагадування у форматі ГГ:ХХ (наприклад, 15:30):")
    await state.set_state(PersonalReminderState.wait_time)

@dp.message(PersonalReminderState.wait_time)
async def reminder_got_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    try:
        remind_time = datetime.strptime(f"{get_today()} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=UA_TZ)
        if remind_time < now_ua():
            await message.answer("Цей час вже минув. Введіть час у майбутньому.")
            return
    except Exception:
        await message.answer("Некоректний формат. Введіть ще раз у форматі ГГ:ХХ (наприклад, 09:25):")
        return
    data = await state.get_data()
    text = data.get("text")
    user_id = message.from_user.id

    async def send_personal_reminder():
        await bot.send_message(user_id, f"🔔 <b>Ваше особисте нагадування</b>:\n{text}", parse_mode="HTML")

    scheduler.add_job(
        send_personal_reminder,
        trigger="date",
        run_date=remind_time,
        id=f"personal-{user_id}-{int(remind_time.timestamp())}",
        replace_existing=False
    )
    await message.answer(f"Нагадування створено на {time_str}!\n\nТекст: {text}", reply_markup=user_menu)
    await state.clear()

import logging

def get_all_staff_user_ids():
    print("[DEBUG][get_all_staff_user_ids] старт")
    ids = []
    try:
        all_records = staff_sheet.get_all_records()
        print(f"[DEBUG][get_all_staff_user_ids] staff_sheet rows: {len(all_records)}")
        for r in all_records:
            print(f"[DEBUG][get_all_staff_user_ids] row: {r}")
            try:
                user_id = int(str(r.get("Telegram ID", "")).strip())
                if user_id:
                    ids.append(user_id)
            except Exception as e:
                print(f"[DEBUG][get_all_staff_user_ids] Exception: {e}")
    except Exception as e:
        print(f"[ERROR][get_all_staff_user_ids] Exception: {e}")
    print(f"[DEBUG][get_all_staff_user_ids] Result: {ids}")
    return ids

def get_today_users():
    print("[DEBUG][get_today_users] старт")
    today = get_today()
    user_ids = set()
    try:
        rows = day_sheet.get_all_records()
        print(f"[DEBUG][get_today_users] day_sheet rows: {len(rows)}")
        for row in rows:
            print(f"[DEBUG][general loop] row: {row}")
            print(f"[DEBUG][flags] Загальна: {is_true(row.get('Загальна', ''))}, Хто на зміні: {is_true(row.get('Розсилка, хто на зміні', ''))}, Індивід: {is_true(row.get('Індивідуальна розсилка', ''))}")
            if str(row.get("Дата")) == today and row.get("Telegram ID"):
                try:
                    user_ids.add(int(row["Telegram ID"]))
                except Exception as e:
                    print(f"[DEBUG][get_today_users] Exception: {e}")
    except Exception as e:
        print(f"[ERROR][get_today_users] Exception: {e}")
    print(f"[DEBUG][get_today_users] Result: {user_ids}")
    return list(user_ids)

def get_staff_user_ids_by_username(username):
    print(f"[DEBUG][get_staff_user_ids_by_username] старт з username='{username}'")
    username = str(username).strip().lstrip('@').lower()
    ids = []
    try:
        all_records = staff_sheet.get_all_records()
        print(f"[DEBUG][get_staff_user_ids_by_username] staff_sheet rows: {len(all_records)}")
        for r in all_records:
            uname = str(r.get("Username", "")).strip().lstrip('@').lower()
            print(f"[DEBUG][get_staff_user_ids_by_username] row uname: '{uname}'")
            if uname == username and r.get("Telegram ID"):
                try:
                    ids.append(int(r["Telegram ID"]))
                    print(f"[DEBUG][get_staff_user_ids_by_username] MATCH {uname} == {username} -> {r['Telegram ID']}")
                except Exception as e:
                    print(f"[DEBUG][get_staff_user_ids_by_username] Exception: {e}")
    except Exception as e:
        print(f"[ERROR][get_staff_user_ids_by_username] Exception: {e}")
    print(f"[DEBUG][get_staff_user_ids_by_username] Result: {ids}")
    return ids

async def send_general_reminder(text, ids):
    print(f"[DEBUG][send_general_reminder] IDs для розсилки: {ids}, text: {text}")
    if not ids:
        print("[WARNING][send_general_reminder] IDs порожні, розсилка не відправлена!")
    for user_id in ids:
        try:
            print(f"[DEBUG][send_general_reminder] Надсилаємо {user_id}")
            await bot.send_message(user_id, f"🔔 <b>Загальне нагадування</b>:\n{text}", parse_mode="HTML")
        except Exception as e:
            print(f"[ERROR][send_general_reminder] Cannot send to user {user_id}: {e}")

def schedule_general_reminders(main_loop):
    print("[DEBUG][schedule_general_reminders] старт")
    try:
        rows = general_reminders_sheet.get_all_records()
        print(f"[DEBUG][schedule_general_reminders] general_reminders_sheet rows: {len(rows)}")
    except Exception as e:
        print(f"[ERROR][schedule_general_reminders] Exception при get_all_records: {e}")
        rows = []
    days_map = {
        "понеділок": 0, "вівторок": 1, "середа": 2,
        "четвер": 3, "пʼятниця": 4, "п’ятниця": 4, "пятниця": 4,
        "субота": 5, "неділя": 6
    }

    def run_async_job(text, ids_func):
        print(f"[DEBUG][run_async_job] Викликається з text='{text}', ids_func={ids_func}")
        try:
            ids = ids_func()
            print(f"[DEBUG][run_async_job] IDs для надсилання: {ids}")
            asyncio.run_coroutine_threadsafe(send_general_reminder(text, ids), main_loop)
        except Exception as e:
            print(f"[ERROR][run_async_job] Exception: {e}")

    for row in rows:
        if not any(row.values()):
            continue  # Пропустити повністю порожній рядок
        print(f"[DEBUG][general loop] row: {row}")
        day = str(row.get('День', '')).strip().lower()
        time_str = str(row.get('Час', '')).strip()
        text = str(row.get('Текст', '')).strip()
        send_all = str(row.get('Загальна', '')).strip().upper() == "TRUE"
        send_shift = str(row.get('Розсилка, хто на зміні', '')).strip().upper() == "TRUE"
        send_individual = str(row.get('Індивідуальна розсилка', '')).strip().upper() == "TRUE"
        username = str(row.get('Username', '')).strip()

        print(f"[DEBUG][general loop] send_all={send_all}, send_shift={send_shift}, send_individual={send_individual}")

        if not day or not time_str or not text or not (send_all or send_shift or send_individual):
            print("[DEBUG][general loop] Пропущено через відсутність обовʼязкових даних")
            continue
        weekday_num = days_map.get(day)
        if weekday_num is None:
            print(f"[DEBUG][general loop] Пропущено — невірний день {day}")
            continue
        try:
            hour, minute = map(int, time_str.split(":"))
        except Exception as e:
            print(f"[ERROR][general loop] Exception при split time: {e}")
            continue

        if send_all:
            print("[DEBUG][general loop] ВІДПРАВКА ВСІМ!")
            ids_func = get_all_staff_user_ids
        elif send_shift:
            print("[DEBUG][general loop] ВІДПРАВКА тим, хто на зміні!")
            ids_func = get_today_users
        elif send_individual and username:
            print(f"[DEBUG][general loop] ВІДПРАВКА користувачу username={username}")
            _username = username
            ids_func = lambda _username=_username: get_staff_user_ids_by_username(_username)
        else:
            print("[DEBUG][general loop] Пропущено через невідповідність умовам розсилки")
            continue

        try:
            scheduler.add_job(
                run_async_job,
                'cron',
                day_of_week=weekday_num,
                hour=hour,
                minute=minute,
                args=[text, ids_func],
                id=f"general-{day}-{hour}-{minute}-{username or 'all'}",
                replace_existing=True
            )
            print(f"[DEBUG][schedule_general_reminders] Додано задачу: {day=} {time_str=} {text=} {ids_func=}")
        except Exception as e:
            print(f"[ERROR][schedule_general_reminders] Exception при add_job: {e}")
            
# --- Навігаційне меню користувача ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Вітаю! Натисніть «Розпочати день» щоб вибрати кількість блоків.",
        reply_markup=user_menu
    )

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ лише для адміністратора.")
        return
    await message.answer("🔧 <b>Адмін-меню</b>", reply_markup=admin_menu_kb, parse_mode="HTML")

@dp.message(F.text == "⬅️ Вихід до користувача")
async def exit_admin(message: types.Message):
    await message.answer("Повернулись у меню користувача", reply_markup=user_menu)

@dp.message(F.text == "Список моїх завдань")
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

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.message(lambda msg: msg.text and msg.text.lower() == "інформаційна база")
async def show_information_categories(message: types.Message):
    records = information_base_sheet.get_all_records()
    categories = sorted(set(row["Категорія"] for row in records if row.get("Категорія")))
    if not categories:
        await message.answer("База порожня.")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=cat, callback_data=f"info_cat_{cat}") ] for cat in categories]
    )
    await message.answer("Оберіть категорію:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("info_cat_"))
async def show_information_items(call: types.CallbackQuery):
    cat = call.data.replace("info_cat_", "")
    records = information_base_sheet.get_all_records()
    items = [row for row in records if row.get("Категорія") == cat]
    if not items:
        await call.message.answer("Нічого не знайдено.")
        return
    text = f"📚 <b>Інформаційна база — {cat}:</b>\n"
    for row in items:
        name = row.get("Назва", "")
        link = row.get("Посилання (або текст)", "")
        desc = row.get("Опис (опціонально)", "")
        line = f"— <b>{name}</b>:\n{link}"
        if desc:
            line += f"\n<i>{desc}</i>"
        text += line + "\n\n"
    await call.message.answer(text.strip(), parse_mode="HTML")
    await call.answer()

@dp.message(lambda msg: msg.text and msg.text.strip().lower() == 'розпочати день')
async def choose_blocks_count(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text='6'), types.KeyboardButton(text='7')],
            [types.KeyboardButton(text='8'), types.KeyboardButton(text='9')],
            [types.KeyboardButton(text='Відмінити дію')],
        ],
        resize_keyboard=True
    )
    await message.answer("Оберіть кількість блоків на сьогодні:", reply_markup=kb)

@dp.message(F.text.in_(['6', '7', '8', '9']))
async def on_blocks_count_chosen(message: types.Message):
    blocks_count = message.text.strip()
    copy_template_blocks_to_today(blocks_count)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=f"{b} блок")] for b in get_blocks_for_today()] +
                 [[types.KeyboardButton(text="Відмінити дію")]],
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

@dp.message(StateFilter('*'), F.text == "Відмінити дію")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Повернулись до головного меню.", reply_markup=user_menu)

# --- Запуск ---
async def main():
    loop = asyncio.get_running_loop()
    schedule_general_reminders(loop)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
