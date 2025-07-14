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

class PollCreateState(StatesGroup):
    question = State()
    options = State()
    audience = State()
    poll_type = State()
    waiting = State()
    
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

# --- Меню ---
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
        [types.KeyboardButton(text="📋 Створити опитування")],
        [types.KeyboardButton(text="⬅️ Вихід до користувача")]
    ],
    resize_keyboard=True
)
@dp.message(F.text.lower() == "створити опитування")
async def handle_poll_button(message: types.Message, state: FSMContext):
    await start_poll_create(message, state)

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
    tasks = get_tasks_for_block(block_num, user_id)
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

# --- Опитування --- #
@dp.message(Command("створити_опитування"))
async def start_poll_create(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Лише для адміністратора.")
        return
    await message.answer("Введіть питання опитування:")
    await state.set_state(PollCreateState.question)

@dp.message(PollCreateState.question)
async def poll_get_question(message: types.Message, state: FSMContext):
    await state.update_data(question=message.text)
    await message.answer("Введіть варіанти відповідей через кому (напр. Так, Ні, Не знаю):")
    await state.set_state(PollCreateState.options)

@dp.message(PollCreateState.options)
async def poll_get_options(message: types.Message, state: FSMContext):
    options = [opt.strip() for opt in message.text.split(",") if opt.strip()]
    if not (2 <= len(options) <= 10):
        await message.answer("Потрібно від 2 до 10 варіантів.")
        return
    await state.update_data(options=options)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Всім зі штату")],
            [types.KeyboardButton(text="Тим хто на зміні")],
            [types.KeyboardButton(text="Конкретному юзеру")]
        ], resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Кому надіслати опитування?", reply_markup=kb)
    await state.set_state(PollCreateState.audience)

@dp.message(PollCreateState.audience)
async def poll_get_audience(message: types.Message, state: FSMContext):
    audience = message.text.lower()
    if audience == "конкретному юзеру":
        await message.answer("Введіть username (без @):", reply_markup=types.ReplyKeyboardRemove())
    else:
        await state.update_data(audience=audience)
        kb = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="Одна відповідь")],
                [types.KeyboardButton(text="Кілька відповідей")]
            ], resize_keyboard=True, one_time_keyboard=True
        )
        await message.answer("Оберіть тип опитування:", reply_markup=kb)
        await state.set_state(PollCreateState.poll_type)
        return
    await state.update_data(audience=audience)
    await state.set_state(PollCreateState.waiting)

@dp.message(PollCreateState.waiting)
async def poll_get_username(message: types.Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    await state.update_data(username=username)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Одна відповідь")],
            [types.KeyboardButton(text="Кілька відповідей")]
        ], resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Оберіть тип опитування:", reply_markup=kb)
    await state.set_state(PollCreateState.poll_type)

@dp.message(PollCreateState.poll_type)
async def poll_send_poll(message: types.Message, state: FSMContext):
    data = await state.get_data()
    question = data["question"]
    options = data["options"]
    audience = data.get("audience")
    username = data.get("username")
    poll_type = message.text.lower()
    allow_multiple = poll_type == "кілька відповідей"

    # --- Обираємо, кому надсилати ---
    user_ids = []
    if audience == "всім зі штату":
        user_ids = get_all_staff_user_ids()  # повинна бути твоя функція
    elif audience == "тим хто на зміні":
        user_ids = get_today_users()
    elif audience == "конкретному юзеру" and username:
        user_ids = get_staff_user_ids_by_username(username)

    if not user_ids:
        await message.answer("Не знайдено жодного користувача для опитування.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        return

    polls_sheet = gs.open_by_key(SHEET_KEY).worksheet('Опитування')
    # --- Відправляємо Poll і зберігаємо poll_id ---
    for uid in user_ids:
        sent = await bot.send_poll(
            uid,
            question=question,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=allow_multiple
        )
        polls_sheet.append_row([
            question, ", ".join(options), audience, poll_type, sent.poll.id, '', '', ''
        ])
    await message.answer("Опитування надіслано!", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()

# --- Приймаємо відповіді poll ---
@dp.poll_answer()
async def save_poll_answer(poll_answer: types.PollAnswer):
    user_id = poll_answer.user.id
    username = poll_answer.user.username or str(user_id)
    selected = poll_answer.option_ids  # список індексів обраних варіантів
    poll_id = poll_answer.poll_id

    # --- Зберігаємо у таблицю (знайти рядок за poll_id) ---
    polls_sheet = gs.open_by_key(SHEET_KEY).worksheet('Опитування')
    all_rows = polls_sheet.get_all_records()
    for idx, row in enumerate(all_rows):
        if str(row.get("poll_id", "")) == str(poll_id):
            options = [opt.strip() for opt in row["варіанти"].split(",")]
            answers = ", ".join([options[i] for i in selected if i < len(options)])
            time = datetime.now().strftime("%Y-%m-%d %H:%M")
            polls_sheet.update(f"F{idx+2}", username)     # F: username
            polls_sheet.update(f"G{idx+2}", answers)      # G: відповідь
            polls_sheet.update(f"H{idx+2}", time)         # H: час
            break

# --- Кнопка для адміна: Показати результати ---
@dp.message(Command("показати_результати"))
async def show_poll_results(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Лише для адміністратора.")
        return
    polls_sheet = gs.open_by_key(SHEET_KEY).worksheet('Опитування')
    all_rows = polls_sheet.get_all_records()
    text = "Останні результати опитувань:\n\n"
    for row in all_rows[-5:]:
        q = row["питання"]
        ans = row.get("відповідь", "")
        name = row.get("username", "")
        t = row.get("час", "")
        text += f"<b>{q}</b>\n{name or '-'}: {ans or '-'} ({t})\n\n"
    await message.answer(text, parse_mode="HTML")



# --- Запуск ---
async def main():
    loop = asyncio.get_running_loop()
    schedule_general_reminders(loop)
    scheduler.start()
    schedule_all_block_tasks_for_today()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
