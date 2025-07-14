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
dp = Dispatcher()
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
            day_sheet.update_cell(i+2, 9, name)          # Імʼя
    user_sessions[user_id] = block_num

def mark_task_done(row):
    day_sheet.update_cell(row, 10, "TRUE")

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
    print(f"[DEBUG][repeat_reminder_if_needed] {user_id=}, {row=}, {task=}")
    value = day_sheet.cell(row, 10).value
    print(f"[DEBUG][repeat_reminder_if_needed] value={value}")
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
    print(f"[DEBUG][notify_admin_if_needed] {user_id=}, {row=}, {task=}")
    value = day_sheet.cell(row, 10).value
    print(f"[DEBUG][notify_admin_if_needed] value={value}")
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
                args=[user_id, t["task"], t["reminder"], t["row"], i+1],  # додати i+1
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

def schedule_all_block_tasks_for_today():
    today = get_today()
    records = day_sheet.get_all_records()
    # Словник: user_id -> список задач
    user_tasks = {}
    for idx, row in enumerate(records):
        if str(row.get("Дата")) != today:
            continue
        user_id = row.get("Telegram ID")
        if user_id:
            try:
                user_id = int(user_id)
            except Exception:
                continue
            # Додаємо задачу користувачу
            task = {
                "row": idx + 2,
                "task": row.get("Завдання"),
                "reminder": row.get("Нагадування"),
                "time": row.get("Час"),
                "done": row.get("Виконано", ""),
                "block": row.get("Блок")
            }
            if user_id not in user_tasks:
                user_tasks[user_id] = []
            user_tasks[user_id].append(task)
    # Для кожного user_id ставимо нагадування
    for user_id, tasks in user_tasks.items():
        schedule_reminders_for_user(user_id, tasks)

def refresh_block_tasks():
    print("[REFRESH] Оновлення завдань з Google Sheet")
    schedule_all_block_tasks_for_today()

scheduler.add_job(
    refresh_block_tasks,
    'interval',
    minutes=10,  # або minutes=30 якщо треба частіше
    id="refresh-block-tasks"
)

# --- Загальні нагадування (розсилка) ---
def get_all_staff_user_ids():
    ids = []
    try:
        all_records = staff_sheet.get_all_records()
        for r in all_records:
            try:
                user_id = int(str(r.get("Telegram ID", "")).strip())
                if user_id:
                    ids.append(user_id)
            except:
                pass
    except Exception as e:
        print(f"[ERROR][get_all_staff_user_ids] {e}")
    return ids

def get_today_users():
    today = get_today()
    user_ids = set()
    try:
        rows = day_sheet.get_all_records()
        for row in rows:
            if str(row.get("Дата")) == today and row.get("Telegram ID"):
                try:
                    user_ids.add(int(row["Telegram ID"]))
                except:
                    pass
    except Exception as e:
        print(f"[ERROR][get_today_users] {e}")
    return list(user_ids)

def get_staff_user_ids_by_username(username):
    username = str(username).strip().lstrip('@').lower()
    ids = []
    try:
        all_records = staff_sheet.get_all_records()
        for r in all_records:
            uname = str(r.get("Username", "")).strip().lstrip('@').lower()
            if uname == username and r.get("Telegram ID"):
                try:
                    ids.append(int(r["Telegram ID"]))
                except:
                    pass
    except Exception as e:
        print(f"[ERROR][get_staff_user_ids_by_username] {e}")
    return ids

async def send_general_reminder(text, ids):
    for user_id in ids:
        try:
            await bot.send_message(user_id, f"🔔 <b>Загальне нагадування</b>:\n{text}", parse_mode="HTML")
        except Exception as e:
            print(f"[ERROR][send_general_reminder] Cannot send to user {user_id}: {e}")

def schedule_general_reminders(main_loop):
    try:
        rows = general_reminders_sheet.get_all_records()
    except Exception as e:
        print(f"[ERROR][schedule_general_reminders] Exception при get_all_records: {e}")
        rows = []
    days_map = {
        "понеділок": 0, "вівторок": 1, "середа": 2,
        "четвер": 3, "пʼятниця": 4, "п’ятниця": 4, "пятниця": 4,
        "субота": 5, "неділя": 6
    }

    def run_async_job(text, ids_func):
        try:
            ids = ids_func()
            asyncio.run_coroutine_threadsafe(send_general_reminder(text, ids), main_loop)
        except Exception as e:
            print(f"[ERROR][run_async_job] Exception: {e}")

    for row in rows:
        day = str(row.get('День', '')).strip().lower()
        time_str = str(row.get('Час', '')).strip()
        text = str(row.get('Текст', '')).strip()
        send_all = is_true(row.get('Загальна', ''))
        send_shift = is_true(row.get('Розсилка, хто на зміні', ''))
        send_individual = is_true(row.get('Індивідуальна розсилка', ''))
        username = str(row.get('Username', '')).strip()
        if not day or not time_str or not text or not (send_all or send_shift or send_individual):
            continue
        weekday_num = days_map.get(day)
        if weekday_num is None:
            continue
        try:
            hour, minute = map(int, time_str.split(":"))
        except Exception as e:
            continue
        if send_all:
            ids_func = get_all_staff_user_ids
        elif send_shift:
            ids_func = get_today_users
        elif send_individual and username:
            _username = username
            ids_func = lambda _username=_username: get_staff_user_ids_by_username(_username)
        else:
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
        except Exception as e:
            print(f"[ERROR][schedule_general_reminders] Exception при add_job: {e}")

scheduler.add_job(
    lambda: schedule_general_reminders(asyncio.get_event_loop()),
    'interval',
    minutes=10,
    id="refresh-general-reminders"
)

# --- Меню ---
user_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Розпочати день")],
        [types.KeyboardButton(text="Список моїх завдань"), types.KeyboardButton(text="Мої нагадування")],
        [types.KeyboardButton(text="Створити нагадування")],
        [types.KeyboardButton(text="Інформаційна база"), types.KeyboardButton(text="Завершити день")],
        [types.KeyboardButton(text="Відмінити дію")]
    ],
    resize_keyboard=True
)
# --- Адмін меню --- #

admin_menu_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="📋 Створити опитування")],
        [types.KeyboardButton(text="📊 Звіт виконання")],
        [types.KeyboardButton(text="⬅️ Вихід до користувача")]
    ],
    resize_keyboard=True
)

# --- Адмін звіт по виконанню --- #

from datetime import datetime, timedelta

class ReportFSM(StatesGroup):
    waiting_date = State()

def get_full_name_by_id(user_id):
    try:
        for r in staff_sheet.get_all_records():
            if str(r.get("Telegram ID", "")).strip() == str(user_id):
                return r.get(list(r.keys())[0], "")  # перший стовпець — ім'я
    except Exception as e:
        print(f"[ERROR][get_full_name_by_id]: {e}")
    return "?"

@dp.message(F.text == "📊 Звіт виконання")
async def admin_report_choose_date(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ лише адміністратору.")
        return
    # генеруємо останні 10 днів, сьогодні - окремо
    today = datetime.now(UA_TZ).date()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(10)]
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=d)] for d in dates] + [[types.KeyboardButton(text="Відмінити дію")]],
        resize_keyboard=True
    )
    await state.set_state(ReportFSM.waiting_date)
    await message.answer("Оберіть дату для звіту:", reply_markup=kb)

@dp.message(ReportFSM.waiting_date)
async def admin_report_generate(message: types.Message, state: FSMContext):
    date = message.text.strip()
    await state.clear()
    # Якщо це сьогодні, беремо з "Завдання на день"
    if date == datetime.now(UA_TZ).strftime('%Y-%m-%d'):
        sheet = day_sheet
    else:
        try:
            archive_sheet = date
            sheet = gs.open_by_key(SHEET_KEY).worksheet(archive_sheet)
        except Exception:
            await message.answer(f"Не знайдено архівний лист для {date}.")
            return

    rows = sheet.get_all_records()
    if not rows:
        await message.answer("Немає даних за цю дату.")
        return

    # групуємо по блоках
    blocks = {}
    for row in rows:
        block = str(row.get("Блок") or "")
        if not block:
            continue
        if block not in blocks:
            blocks[block] = []
        blocks[block].append(row)

    result = f"<b>Звіт за {date}:</b>\n\n"
    for block, items in sorted(blocks.items(), key=lambda x: int(x[0])):
        # шукаємо Telegram ID і визначаємо імʼя
        responsible_id = None
        for r in items:
            if r.get("Telegram ID"):
                responsible_id = r["Telegram ID"]
                break
        if responsible_id:
            name = get_full_name_by_id(responsible_id)
        else:
            name = "—"
        result += f"<b>Блок {block}:</b>\n"
        result += f"Відповідальний: <b>{name}</b>\n"
        # для кожного завдання — беремо список часів (або один)
        for r in items:
            task = r.get("Завдання") or ""
            reminder = r.get("Нагадування") or ""
            times = [tm.strip() for tm in (r.get("Час") or "").split(",") if tm.strip()]
            # знаходимо всі колонки "Виконано", "Виконано (2)", ...
            status_marks = []
            for idx, tm in enumerate(times):
                col = "Виконано" if idx == 0 else f"Виконано ({idx+1})"
                val = (r.get(col) or "").strip().upper()
                status_marks.append("✅" if val == "TRUE" else "❌")
            if not times:
                # без часу — перевіряємо просто "Виконано"
                val = (r.get("Виконано") or "").strip().upper()
                status_marks.append("✅" if val == "TRUE" else "❌")
            result += f"• <b>{task}</b> | {reminder} {' '.join(status_marks)}\n"
        result += "\n"
    await message.answer(result, parse_mode="HTML", reply_markup=admin_menu_kb)
    

@dp.message(F.text == "Створити нагадування")
async def start_reminder(message: types.Message, state: FSMContext):
    await state.set_state(ReminderFSM.wait_text)
    await message.answer("Введіть текст нагадування:")

@dp.message(ReminderFSM.wait_text)
async def get_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(ReminderFSM.wait_time)
    await message.answer("Введіть час (ГГ:ХХ):")

@dp.message(ReminderFSM.wait_time)
async def get_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    try:
        remind_time = datetime.strptime(f"{datetime.now().date()} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=UA_TZ)
        if remind_time < datetime.now(UA_TZ):
            await message.answer("Цей час вже минув.")
            return
    except Exception:
        await message.answer("Некоректний формат. Введіть у форматі ГГ:ХХ (наприклад, 09:25):")
        return
    data = await state.get_data()
    text = data.get("text")
    user_id = message.from_user.id

    async def send_personal_reminder():
        await bot.send_message(user_id, f"🔔 <b>Ваше нагадування</b>:\n{text}", parse_mode="HTML")

    scheduler.add_job(
        send_personal_reminder,
        trigger="date",
        run_date=remind_time,
        id=f"personal-{user_id}-{int(remind_time.timestamp())}",
        replace_existing=False
    )
    await message.answer(f"Нагадування створено на {time_str}!\nТекст: {text}")
    await state.clear()


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

    for row in my_tasks:
        task = row.get("Завдання") or ""
        desc = row.get("Опис") or ""
        done = (row.get("Виконано", "").strip().upper() == "TRUE")
        status = "✅" if done else "❌ Не виконано"
        text = f"<b>Завдання:</b> {task}\n"
        if desc:
            text += f"<b>Опис:</b> {desc}\n"
        text += f"<b>Статус:</b> {status}"
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Виконано", callback_data=f"task_done_{row['_row']}")]
            ]
        )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def send_task_to_user(user_id, row, task, desc, status, row_idx):
    status_text = "✅ Виконано" if status else "❌ Не виконано"
    kb = None
    if not status:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Виконано", callback_data=f"done_task_{row_idx}")]
        ])
    msg = f"<b>Завдання:</b> {task}\n"
    if desc:
        msg += f"<b>Опис:</b> {desc}\n"
    msg += f"<b>Статус:</b> {status_text}"
    await bot.send_message(user_id, msg, parse_mode="HTML", reply_markup=kb)

    text = "<b>Ваші завдання на сьогодні:</b>\n"
    for row in my_tasks:
        task = row.get("Завдання") or ""
        status = "✅" if (row.get("Виконано", "").strip().upper() == "TRUE") else "❌"
        text += f"— {task} {status}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=user_menu)

@dp.message(F.text == "Мої нагадування")
async def my_reminders(message: types.Message):
    user_id = message.from_user.id
    today = get_today()
    records = day_sheet.get_all_records()
    my_reminders = [
        row for row in records
        if str(row.get("Дата")) == today and str(row.get("Telegram ID")) == str(user_id)
    ]
    if not my_reminders:
        await message.answer("У вас немає нагадувань на сьогодні.", reply_markup=user_menu)
        return

    text = "<b>Ваші нагадування на сьогодні:</b>\n"
    for row in my_reminders:
        reminder = row.get("Нагадування") or ""
        time = row.get("Час") or ""
        status = "✅" if (row.get("Виконано", "").strip().upper() == "TRUE") else "❌"
        text += f"— {time}: {reminder} {status}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=user_menu)

@dp.callback_query(lambda c: c.data.startswith("task_done_"))
async def task_done_callback(call: types.CallbackQuery):
    row = int(call.data.split("_")[-1])
    mark_task_done(row)
    await call.message.edit_text(call.message.text + "\n\n✅ Позначено як виконане.", reply_markup=None)
    await call.answer("Завдання виконано!")

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
    tasks = get_tasks_for_block(block_num, user_id)
    if not tasks:
        await message.answer("Завдань не знайдено для цього блоку.", reply_markup=user_menu)
        return
    for t in tasks:
        desc = t.get("Опис") or ""
        done = (t.get("done", "").strip().upper() == "TRUE")
        await send_task_with_status(user_id, t["task"], desc, done, t["row"])

@dp.callback_query(F.data.startswith('done_task_'))
async def done_task_callback(call: types.CallbackQuery):
    row_idx = int(call.data.split('_')[-1])
    # Оновлюємо стовпчик "Виконано" (10-та колонка, J)
    day_sheet.update_cell(row_idx, 10, "TRUE")
    await call.message.edit_text(call.message.text.replace("❌ Не виконано", "✅ Виконано"), parse_mode="HTML")
    await call.answer("Завдання відмічено як виконане ✅")

@dp.message(StateFilter('*'), F.text == "Відмінити дію")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Повернулись до головного меню.", reply_markup=user_menu)

async def send_task_with_status(user_id, task, desc, done, row):
    status = "✅" if done else "❌"
    text = f"<b>Завдання:</b> {task}\n"
    if desc:
        text += f"<b>Опис:</b> {desc}\n"
    text += f"<b>Статус:</b> {status}"
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Виконано", callback_data=f"task_done_{row}")]
        ]
    )
    await bot.send_message(user_id, text, reply_markup=kb, parse_mode="HTML")

# --- Опитування --- #
@dp.message(lambda m: m.text and m.text.strip().lower() == "створити опитування")
async def poll_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступно лише адміністратору.")
        return
    await message.answer("Введіть текст питання для опитування:")
    await state.set_state(PollState.waiting_question)

@dp.message(PollState.waiting_question)
async def poll_got_question(message: types.Message, state: FSMContext):
    await state.update_data(question=message.text.strip())
    await message.answer("Введіть варіанти відповіді через кому (наприклад: Так, Ні, Не знаю):")
    await state.set_state(PollState.waiting_options)

@dp.message(PollState.waiting_options)
async def poll_got_options(message: types.Message, state: FSMContext):
    options = [opt.strip() for opt in message.text.split(",") if opt.strip()]
    if len(options) < 2:
        await message.answer("Має бути мінімум 2 варіанти!")
        return
    await state.update_data(options=options)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Одна відповідь (radio)")],
            [types.KeyboardButton(text="Кілька відповідей (checkbox)")]
        ], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Який тип опитування?", reply_markup=kb)
    await state.set_state(PollState.waiting_type)

@dp.message(PollState.waiting_type)
async def poll_got_type(message: types.Message, state: FSMContext):
    if "одна" in message.text.lower():
        poll_type = "radio"
    elif "кілька" in message.text.lower():
        poll_type = "checkbox"
    else:
        await message.answer("Оберіть тип із кнопок.")
        return
    await state.update_data(poll_type=poll_type)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Всі зі штату")],
            [types.KeyboardButton(text="Ті, хто на зміні")],
            [types.KeyboardButton(text="Конкретний користувач")]
        ], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Кому надіслати опитування?", reply_markup=kb)
    await state.set_state(PollState.waiting_target)

@dp.message(PollState.waiting_target)
async def poll_got_target(message: types.Message, state: FSMContext):
    if "штат" in message.text.lower():
        await state.update_data(target="all")
        await state.set_state(PollState.waiting_datetime)
        await message.answer("Введіть дату і час у форматі YYYY-MM-DD HH:MM:")
    elif "зміні" in message.text.lower():
        await state.update_data(target="shift")
        await state.set_state(PollState.waiting_datetime)
        await message.answer("Введіть дату і час у форматі YYYY-MM-DD HH:MM:")
    elif "користувач" in message.text.lower():
        await state.update_data(target="user")
        await state.set_state(PollState.waiting_username)
        await message.answer("Введіть username користувача (без @):")
    else:
        await message.answer("Оберіть варіант із кнопок.")

@dp.message(PollState.waiting_username)
async def poll_got_username(message: types.Message, state: FSMContext):
    username = message.text.strip().lstrip('@')
    await state.update_data(username=username)
    await state.set_state(PollState.waiting_datetime)
    await message.answer("Введіть дату і час у форматі YYYY-MM-DD HH:MM:")

@dp.message(PollState.waiting_datetime)
async def poll_got_datetime(message: types.Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        await state.update_data(datetime=dt.strftime("%Y-%m-%d %H:%M"))
    except Exception:
        await message.answer("Некоректний формат. Приклад: 2025-07-14 16:00")
        return
    data = await state.get_data()
    preview = f"<b>ОПИТУВАННЯ</b>\nПитання: {data['question']}\nВаріанти: {', '.join(data['options'])}\nТип: {data['poll_type']}\nЧас: {data['datetime']}"
    if data["target"] == "user":
        preview += f"\nUser: @{data['username']}"
    await message.answer(preview, parse_mode="HTML")
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="✅ Підтвердити створення")],
                  [types.KeyboardButton(text="❌ Відмінити")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Підтвердити створення опитування?", reply_markup=kb)
    await state.set_state(PollState.confirm)

@dp.message(PollState.confirm)
async def poll_confirm(message: types.Message, state: FSMContext):
    if "підтвердити" in message.text.lower():
        data = await state.get_data()
        # Записати в Google Sheet
        row = [
            data.get("question"),
            ";".join(data.get("options", [])),
            data.get("poll_type"),
            data.get("target"),
            data.get("username", ""),
            data.get("datetime"),
            ""  # Тут буде записуватись вибраний варіант (результат)
        ]
        poll_sheet.append_row(row, value_input_option='USER_ENTERED')
        await message.answer("✅ Опитування створене та заплановане!", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        await message.answer("❌ Відмінено.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()

# --- Логіка надсилання опитування ---
days_map = {
    "понеділок": 0, "вівторок": 1, "середа": 2,
    "четвер": 3, "пʼятниця": 4, "п’ятниця": 4, "пятниця": 4,
    "субота": 5, "неділя": 6
}

async def send_poll_to_users(title, options, poll_type, user_ids, poll_row_idx):
    if poll_type == "radio":
        kb = types.InlineKeyboardMarkup()
        for opt in options:
            kb.add(types.InlineKeyboardButton(text=opt, callback_data=f"poll_{poll_row_idx}_{opt}"))
        for uid in user_ids:
            await bot.send_message(uid, f"🗳 <b>{title}</b>", reply_markup=kb, parse_mode="HTML")
    else:  # checkbox
        kb = types.InlineKeyboardMarkup()
        for opt in options:
            kb.add(types.InlineKeyboardButton(text=opt, callback_data=f"pollcb_{poll_row_idx}_{opt}"))
        kb.add(types.InlineKeyboardButton(text="✅ Завершити", callback_data=f"pollcb_{poll_row_idx}_done"))
        for uid in user_ids:
            await bot.send_message(uid, f"🗳 <b>{title}</b>\n(Можна обрати кілька варіантів, після вибору натисніть 'Завершити')", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("poll_"))
async def on_poll_vote(call: types.CallbackQuery):
    _, row_idx, option = call.data.split("_", 2)
    user = call.from_user.username or call.from_user.id
    poll_sheet.append_row([
        poll_sheet.cell(int(row_idx)+1, 1).value,  # назва
        poll_sheet.cell(int(row_idx)+1, 2).value,  # варіанти
        option,                                    # вибраний варіант
        datetime.now(UA_TZ).strftime("%Y-%m-%d %H:%M"),
        user,                                      # username
        poll_sheet.cell(int(row_idx)+1, 6).value,  # день
        poll_sheet.cell(int(row_idx)+1, 7).value,  # тип
        poll_sheet.cell(int(row_idx)+1, 8).value,  # recipients
        poll_sheet.cell(int(row_idx)+1, 9).value   # username if individual
    ])
    await call.answer("Ваш вибір прийнято!", show_alert=True)
    await call.message.edit_reply_markup(reply_markup=None)

# Для чекбоксів — тимчасове зберігання
user_checkbox_selections = {}

@dp.callback_query(lambda c: c.data.startswith("pollcb_"))
async def on_pollcb_vote(call: types.CallbackQuery):
    parts = call.data.split("_")
    row_idx = parts[1]
    option = "_".join(parts[2:])
    user = call.from_user.username or call.from_user.id
    key = f"{row_idx}:{user}"
    if option == "done":
        selected = user_checkbox_selections.get(key, [])
        if not selected:
            await call.answer("Оберіть хоча б одну відповідь.", show_alert=True)
            return
        for opt in selected:
            poll_sheet.append_row([
                poll_sheet.cell(int(row_idx)+1, 1).value,  # назва
                poll_sheet.cell(int(row_idx)+1, 2).value,  # варіанти
                opt,                                       # вибраний варіант
                datetime.now(UA_TZ).strftime("%Y-%m-%d %H:%M"),
                user,                                      # username
                poll_sheet.cell(int(row_idx)+1, 6).value,  # день
                poll_sheet.cell(int(row_idx)+1, 7).value,  # тип
                poll_sheet.cell(int(row_idx)+1, 8).value,  # recipients
                poll_sheet.cell(int(row_idx)+1, 9).value   # username if individual
            ])
        await call.answer("Ваш вибір прийнято!", show_alert=True)
        await call.message.edit_reply_markup(reply_markup=None)
        user_checkbox_selections.pop(key, None)
        return
    # Додаємо до вибраного
    if key not in user_checkbox_selections:
        user_checkbox_selections[key] = []
    if option not in user_checkbox_selections[key]:
        user_checkbox_selections[key].append(option)
    await call.answer(f"Вибрано: {', '.join(user_checkbox_selections[key])}")

# --- Планувальник для опитувань ---
def schedule_polls():
    rows = poll_sheet.get_all_records()
    for idx, row in enumerate(rows):
        title = row.get("назва", "")
        options = row.get("варіанти вибору", "").split(";")
        poll_type = row.get("тип", "radio")
        day = row.get("день", "")
        time_str = row.get("час", "")
        recipients = row.get("recipients", "")
        username = row.get("username", "")
        if not title or not options or not day or not time_str:
            continue
        weekday_num = days_map.get(day)
        if weekday_num is None:
            continue
        try:
            hour, minute = map(int, time_str.split(":"))
        except:
            continue
        if "штату" in recipients:
            user_ids = get_all_staff_user_ids
        elif "зміні" in recipients:
            user_ids = get_today_users
        elif "індивідуально" in recipients and username:
            user_ids = lambda username=username: get_staff_user_ids_by_username(username)
        else:
            continue

        def run_poll_async(idx=idx, title=title, options=options, poll_type=poll_type, user_ids=user_ids):
            ids = user_ids() if callable(user_ids) else user_ids
            asyncio.run_coroutine_threadsafe(
                send_poll_to_users(title, options, poll_type, ids, idx),
                asyncio.get_event_loop()
            )

        scheduler.add_job(
            run_poll_async,
            'cron',
            day_of_week=weekday_num,
            hour=hour,
            minute=minute,
            id=f"poll-{idx}",
            replace_existing=True
        )


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
