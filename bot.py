import os
import logging
import asyncio
import functools
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from functools import partial
main_loop = None


# --- Константи ---
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SHEET_KEY = os.getenv('SHEET_KEY')
UA_TZ = timezone(timedelta(hours=3))  # Київ
REMINDER_REPEAT_MINUTES = 20
ADMIN_NOTIFY_MINUTES = 30
ADMIN_IDS = [438830182]   # <-- твій Telegram ID
logging.basicConfig(level=logging.INFO)



# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gs = gspread.authorize(creds)
TEMPLATE_SHEET = 'Шаблони блоків'
DAY_SHEET = 'Завдання на день'
GENERAL_REMINDERS_SHEET = 'Загальні нагадування'
INFORMATION_BASE_SHEET = 'Інформаційна база'
STAFF_SHEET = "Штат"
template_sheet = gs.open_by_key(SHEET_KEY).worksheet(TEMPLATE_SHEET)
day_sheet = gs.open_by_key(SHEET_KEY).worksheet(DAY_SHEET)
information_base_sheet = gs.open_by_key(SHEET_KEY).worksheet(INFORMATION_BASE_SHEET)
general_reminders_sheet = gs.open_by_key(SHEET_KEY).worksheet(GENERAL_REMINDERS_SHEET)
staff_sheet = gs.open_by_key(SHEET_KEY).worksheet(STAFF_SHEET)



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

# --- Inline-нагадування ---
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

def schedule_reminders_for_user(user_id, tasks):
    for t in tasks:
        if not t["time"]:
            continue
        # Якщо кілька часів у комірці (через кому)
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
            # Основне нагадування
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time,
                args=[user_id, t["task"], t["reminder"], t["row"]],
                id=f"{user_id}-{t['row']}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
                replace_existing=True
            )
            # Повторне нагадування через 20 хв
            scheduler.add_job(
                repeat_reminder_if_needed,
                'date',
                run_date=remind_time + timedelta(minutes=REMINDER_REPEAT_MINUTES),
                args=[user_id, t["row"], t["task"], t["reminder"], block],
                id=f"repeat-{user_id}-{t['row']}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
                replace_existing=True
            )
            # Адміну через 30 хв
            scheduler.add_job(
                notify_admin_if_needed,
                'date',
                run_date=remind_time + timedelta(minutes=ADMIN_NOTIFY_MINUTES),
                args=[user_id, t["row"], t["task"], t["reminder"], block],
                id=f"admin-{user_id}-{t['row']}-{int(remind_time.timestamp())}-{time_str.replace(':','')}",
                replace_existing=True
            )

# --- Планувати щодня після запуску ---
async def daily_group_reminders():
    while True:
        schedule_group_reminders()
        await asyncio.sleep(60 * 60 * 6)  # Оновлювати кожні 6 годин (можна змінити)

# --- Запуск воркера в main() ---
async def main():
    scheduler.start()
    asyncio.create_task(daily_group_reminders())  # <--- Додаємо!
    await dp.start_polling(bot)

# === FSM для особистого нагадування ===
class PersonalReminderState(StatesGroup):
    wait_text = State()
    wait_time = State()

# --- Загальні нагадування ---

main_loop = None  # Глобальний event loop

def get_today_users():
    """Повертає список Telegram ID тих, хто обрав блок сьогодні (з аркуша 'Завдання на день')."""
    today = get_today()
    records = day_sheet.get_all_records()
    user_ids = set()
    for row in records:
        if str(row.get("Дата")) == today and row.get("Telegram ID"):
            try:
                user_ids.add(int(row["Telegram ID"]))
            except Exception:
                continue
    return list(user_ids)

def get_all_staff_user_ids():
    """Повертає список Telegram ID усіх співробітників з листа 'Штат'."""
    staff_records = staff_sheet.get_all_records()
    ids = []
    for r in staff_records:
        try:
            user_id = int(r.get("Telegram ID", 0))
            if user_id:
                ids.append(user_id)
        except Exception:
            continue
    return ids

def get_staff_user_ids_by_usernames(usernames):
    staff_records = staff_sheet.get_all_records()
    username_set = set([u.strip().lower() for u in usernames.split(",") if u.strip()])
    print("[DEBUG] username_set:", username_set)
    ids = []
    for r in staff_records:
        uname = str(r.get("Username", "")).strip().lower()
        print("[DEBUG] uname in sheet:", uname)
        if uname in username_set and r.get("Telegram ID"):
            try:
                ids.append(int(r["Telegram ID"]))
            except Exception as e:
                print("[ERROR] Cannot convert Telegram ID:", r["Telegram ID"], e)
                continue
    print("[DEBUG] Resulting ids:", ids)
    return ids

async def send_general_reminder(text, ids):
    print("send_general_reminder called:", text, ids)
    for user_id in ids:
        try:
            print(f"Sending to {user_id}")
            await bot.send_message(user_id, f"🔔 <b>Загальне нагадування</b>:\n{text}", parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Cannot send to user {user_id}: {e}")

def schedule_general_reminders():
    rows = general_reminders_sheet.get_all_records()
    days_map = {
        "понеділок": 0, "вівторок": 1, "середа": 2,
        "четвер": 3, "пʼятниця": 4, "субота": 5, "неділя": 6,
        "пятниця": 4, "п’ятниця": 4
    }
    for row in rows:
        day = row.get('День', '').strip().lower()
        time_str = row.get('Час', '').strip()
        text = row.get('Текст', '').strip()
        usernames = str(row.get('Usernames', '')).strip()
        send_to_all = str(row.get('Загальна розсилка', '')).strip().upper() == "TRUE"
        send_to_block = str(row.get('Загальна розсилка', '')).strip().upper() == "FALSE"
        if not day or not time_str or not text:
            continue
        weekday_num = days_map.get(day)
        if weekday_num is None:
            continue
        hour, minute = map(int, time_str.split(":"))
        
        # Логіка вибору функції отримання ID
        if send_to_all:
            ids_func = get_all_staff_user_ids
        elif usernames:
            ids_func = lambda: get_staff_user_ids_by_usernames(usernames)
        elif send_to_block:
            ids_func = get_today_users
        else:
            ids_func = get_today_users  # fallback, якщо все пусто

        async def job(text=text, ids_func=ids_func):
            ids = ids_func()
            print(f"== GENERAL REMINDER ==\nText: {text}\nIDs: {ids}")
            await send_general_reminder(text, ids)

        def run_async_job():
            global main_loop
            if main_loop and main_loop.is_running():
                main_loop.create_task(job())
            else:
                print("[ERROR] main_loop is not running!")

        scheduler.add_job(
            run_async_job,
            'cron',
            day_of_week=weekday_num,
            hour=hour,
            minute=minute,
            id=f"general-{day}-{hour}-{minute}",
            replace_existing=True
        )

async def send_general_reminder(text, ids):
    print("send_general_reminder called:", text, ids)
    for user_id in ids:
        try:
            print(f"Sending to {user_id}")
            await bot.send_message(user_id, f"🔔 <b>Загальне нагадування</b>:\n{text}", parse_mode="HTML")
        except Exception as e:
            print(f"Cannot send to user {user_id}: {e}")
            logging.warning(f"Cannot send to user {user_id}: {e}")

# --- Запуск loop в main ---
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    schedule_general_reminders()
    scheduler.start()
    await dp.start_polling(bot)
        
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

@dp.callback_query(lambda c: c.data.startswith("kb_cat_"))
async def show_knowledge_base_category(call: types.CallbackQuery):
    cat = call.data.replace("kb_cat_", "")
    records = knowledge_base_sheet.get_all_records()
    entries = [row for row in records if str(row.get("Категорія")) == cat]
    if not entries:
        await call.message.answer("Нічого не знайдено.")
        await call.answer()
        return

    msg = f"📚 <b>Інформаційна база — {cat}:</b>\n"
    for row in entries:
        name = row.get("Назва", "-")
        link = row.get("Посилання (або текст)", "-")
        desc = row.get("Опис (опціонально)", "")
        # Якщо це посилання — форматувати як гіперлінк
        if link.startswith("http"):
            link = f'<a href="{link}">{name}</a>'
        else:
            link = f"{name}: {link}"
        msg += f"— {link}"
        if desc:
            msg += f"\n   <i>{desc}</i>"
        msg += "\n"
    await call.message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)
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

@dp.message(StateFilter('*'), F.text == "Відмінити дію")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Повернулись до головного меню.", reply_markup=user_menu)

# --- Запуск ---
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    schedule_general_reminders()
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
