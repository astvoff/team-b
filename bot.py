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
from collections import defaultdict
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- FSM ---
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
REMINDER_REPEAT_MINUTES = 30
ADMIN_NOTIFY_MINUTES = 40
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

def prepend_rows_to_sheet(sheet, rows):
    for i, row in enumerate(rows):
        sheet.insert_row(row, index=2 + i, value_input_option='USER_ENTERED')

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
        prepend_rows_to_sheet(day_sheet, new_rows)

def get_blocks_for_today():
    today = get_today()
    records = day_sheet.get_all_records()
    return sorted(list(set(str(row["Блок"]) for row in records if str(row["Дата"]) == today)))

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
        name = get_full_name_by_id(user_id)
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"❗️ <b>Завдання НЕ виконано!</b>\n"
                    f"Користувач: {name}\n"
                    f"Блок: {block}\n"
                    f"Завдання: {task}\n"
                    f"Нагадування: {reminder}",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"[ADMIN_NOTIFY] Failed to send to {admin_id}: {e}")

@dp.callback_query(F.data.startswith('done_'))
async def done_callback(call: types.CallbackQuery):
    parts = call.data.split('_')
    row = int(parts[1])
    idx = int(parts[2])
    col = 10 + (idx - 1)
    day_sheet.update_cell(row, col, "TRUE")
    await call.message.edit_text(
        call.message.text.replace("нагадування надійшло", "Успішне"),
        reply_markup=None,
        parse_mode="HTML"
    )
    await call.answer("Відмічено як виконане ✅")

def aggregate_tasks(records, today, block_num, user_id=None):
    agg = defaultdict(lambda: {
        'desc': '',
        'reminders': [],
        'row_idxs': [],
        'done_cols': [],
    })
    for idx, row in enumerate(records):
        if str(row.get("Дата")) != today: continue
        if str(row.get("Блок")) != str(block_num): continue
        if user_id and str(row.get("Telegram ID")) != str(user_id): continue
        task = (row.get("Завдання") or "").strip()
        desc = (row.get("Опис") or "").strip()
        reminder = (row.get("Нагадування") or "").strip()
        times = [t.strip() for t in (row.get("Час") or "").split(",") if t.strip()]
        key = (task, desc, block_num)
        agg[key]['desc'] = desc
        agg[key]['row_idxs'].append(idx + 2)
        if times and reminder:
            for i, tm in enumerate(times):
                agg[key]['reminders'].append((tm, reminder, idx+2, i))
                col = "Виконано" if i == 0 else f"Виконано ({i+1})"
                done = (row.get(col, "").strip().upper() == "TRUE")
                agg[key]['done_cols'].append(done)
        else:
            val = (row.get("Виконано") or "").strip().upper()
            agg[key]['done_cols'].append(val == "TRUE")
    return agg

def schedule_reminders_for_user(user_id, agg):
    for (task, desc, block), data in agg.items():
        for i, (tm, reminder, row, idx) in enumerate(data['reminders']):
            try:
                remind_time = datetime.strptime(f"{get_today()} {tm}", '%Y-%m-%d %H:%M').replace(tzinfo=UA_TZ)
            except Exception:
                continue
            now = now_ua()
            if remind_time <= now:
                continue
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time,
                args=[user_id, task, reminder, row, idx+1],
                id=f"{user_id}-{row}-{idx+1}-{int(remind_time.timestamp())}-{tm.replace(':','')}",
                replace_existing=True
            )
            scheduler.add_job(
                repeat_reminder_if_needed,
                'date',
                run_date=remind_time + timedelta(minutes=REMINDER_REPEAT_MINUTES),
                args=[user_id, row, task, reminder, block],
                id=f"repeat-{user_id}-{row}-{int(remind_time.timestamp())}-{tm.replace(':','')}",
                replace_existing=True
            )
            scheduler.add_job(
                notify_admin_if_needed,
                'date',
                run_date=remind_time + timedelta(minutes=ADMIN_NOTIFY_MINUTES),
                args=[user_id, row, task, reminder, block],
                id=f"admin-{user_id}-{row}-{int(remind_time.timestamp())}-{tm.replace(':','')}",
                replace_existing=True
            )

def schedule_all_block_tasks_for_today():
    today = get_today()
    records = day_sheet.get_all_records()
    by_user_and_block = defaultdict(lambda: defaultdict(list))
    for row in records:
        if str(row.get("Дата")) != today:
            continue
        user_id = row.get("Telegram ID")
        block_num = row.get("Блок")
        if user_id and block_num:
            try:
                user_id_int = int(user_id)
                by_user_and_block[user_id_int][block_num].append(row)
            except Exception:
                continue
    for user_id, blocks in by_user_and_block.items():
        for block_num, tasks_rows in blocks.items():
            agg = aggregate_tasks(tasks_rows, today, block_num, user_id=user_id)
            schedule_reminders_for_user(user_id, agg)

# --- Меню користувача ---
user_menu = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Розпочати день")],
        [types.KeyboardButton(text="Список моїх завдань"), types.KeyboardButton(text="Мої нагадування")],
        [types.KeyboardButton(text="Створити нагадування"), types.KeyboardButton(text="Інформаційна база")],
        [types.KeyboardButton(text="Завершити день")],
        [types.KeyboardButton(text="Відмінити дію")]
    ],
    resize_keyboard=True
)

# --- Меню адміністратора ---
admin_menu_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="📋 Створити опитування")],
        [types.KeyboardButton(text="📊 Звіт виконання")],
        [types.KeyboardButton(text="⬅️ Вихід до користувача")]
    ],
    resize_keyboard=True
)

def get_full_name_by_id(user_id):
    try:
        for r in staff_sheet.get_all_records():
            if str(r.get("Telegram ID", "")).strip() == str(user_id):
                return r.get(list(r.keys())[0], "")  # перший стовпець — ім'я
    except Exception as e:
        print(f"[ERROR][get_full_name_by_id]: {e}")
    return "?"

# --- Адмін-звіт по виконанню ---
@dp.message(F.text == "📊 Звіт виконання")
async def admin_report_choose_date(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ лише адміністратору.")
        return
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
        seen_tasks = set()
        for r in items:
            task = r.get("Завдання") or ""
            reminder = r.get("Нагадування") or ""
            task_key = task.strip().lower()
            if task_key in seen_tasks:
                continue
            seen_tasks.add(task_key)
            times = [tm.strip() for tm in (r.get("Час") or "").split(",") if tm.strip()]
            status_marks = []
            for idx, tm in enumerate(times):
                col = "Виконано" if idx == 0 else f"Виконано ({idx+1})"
                val = (r.get(col) or "").strip().upper()
                status_marks.append("✅" if val == "TRUE" else "❌")
            if not times:
                val = (r.get("Виконано") or "").strip().upper()
                status_marks.append("✅" if val == "TRUE" else "❌")
            result += f"• <b>{task}</b> | {reminder} {' '.join(status_marks)}\n"
        result += "\n"
    await message.answer(result, parse_mode="HTML", reply_markup=admin_menu_kb)

# --- Кнопки виходу ---
@dp.message(F.text == "⬅️ Вихід до користувача")
async def exit_admin(message: types.Message):
    await message.answer("Повернулись у меню користувача", reply_markup=user_menu)

# --- Створення нагадування ---
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

# --- Start та меню ---
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

@dp.message(F.text == "Список моїх завдань")
async def my_tasks(message: types.Message):
    user_id = message.from_user.id
    today = get_today()
    records = day_sheet.get_all_records()
    my_tasks = [
        (idx+2, row)
        for idx, row in enumerate(records)
        if str(row.get("Дата")) == today and str(row.get("Telegram ID")) == str(user_id)
    ]
    if not my_tasks:
        await message.answer("У вас немає завдань на сьогодні.", reply_markup=user_menu)
        return

    seen_tasks = set()
    for row_idx, row in my_tasks:
        task = (row.get("Завдання") or "").strip().lower()
        if task in seen_tasks:
            continue
        seen_tasks.add(task)
        desc = row.get("Опис") or ""
        done = (row.get("Виконано", "").strip().upper() == "TRUE")
        status = "✅" if done else "❌ Не виконано"
        text = f"<b>Завдання:</b> <b>{row.get('Завдання') or ''}</b>\n"
        if desc:
            text += f"<u>Зона відповідальності:</u>\n{desc}\n"
        text += f"<b>Статус:</b> <b>{status}</b>"
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Виконано", callback_data=f"task_done_{row_idx}")]
            ]
        )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("task_done_"))
async def mark_task_done_callback(call: types.CallbackQuery):
    row_idx = int(call.data.replace("task_done_", ""))
    day_sheet.update_cell(row_idx, 10, "TRUE")
    await call.message.edit_text(call.message.text.replace("❌", "✅").replace("Не виконано", "Виконано"), parse_mode="HTML")
    await call.answer("Відмічено як виконане ✅")

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

    def parse_time(row):
        times = (row.get("Час") or "").split(",")
        times = [t.strip() for t in times if t.strip()]
        if not times:
            return "23:59"
        try:
            return times[0]
        except:
            return "23:59"

    my_reminders_sorted = sorted(my_reminders, key=parse_time)
    text = "<b>Ваші нагадування на сьогодні:</b>\n"
    for row in my_reminders_sorted:
        reminder = row.get("Нагадування") or ""
        time = row.get("Час") or ""
        status = "✅" if (row.get("Виконано", "").strip().upper() == "TRUE") else "❌"
        text += f"— {time}: {reminder} {status}\n"
    await message.answer(text, parse_mode="HTML", reply_markup=user_menu)

# --- Інформаційна база ---
@dp.message(lambda msg: msg.text and msg.text.lower() == "інформаційна база")
async def show_information_categories(message: types.Message):
    records = information_base_sheet.get_all_records()
    categories = sorted(set(row["Категорія"] for row in records if row.get("Категорія")))
    if not categories:
        await message.answer("База порожня.")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=cat, callback_data=f"info_cat_{cat}")] for cat in categories]
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

# --- Відміна дії ---
@dp.message(StateFilter('*'), F.text == "Відмінити дію")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅️ Повернулись до головного меню.", reply_markup=user_menu)

# --- Вибір блоків на день ---
@dp.message(lambda msg: msg.text and msg.text.strip().lower() == 'розпочати день')
async def choose_blocks_count(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text='6'), types.KeyboardButton(text='7')],
            [types.KeyboardButton(text='8'), types.KeyboardButton(text='9')],
            [types.KeyboardButton(text="Відмінити дію")]
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
    await assign_user_to_block(block_num, user_id)
    agg = aggregate_tasks(records, today, block_num, user_id)
    if not agg:
        await message.answer("Завдань не знайдено для цього блоку.", reply_markup=user_menu)
        return
    for (task, desc, block), data in agg.items():
        status_marks = " ".join(["✅" if d else "❌" for d in data['done_cols']])
        text = (
            f"<b>Завдання:</b> <b>{task}</b>\n"
            f"<u>Зона відповідальності:</u>\n{desc}\n"
            f"<b>Статус:</b> <b>{status_marks}</b>"
        )
        kb = None
        if not all(data['done_cols']):
            kb = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="✅ Виконано", callback_data=f"task_done_{data['row_idxs'][0]}")]
                ]
            )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    reminders = []
    for v in agg.values():
        reminders.extend([(tm, rem) for tm, rem, _, _ in v['reminders']])
    reminders = sorted(set(reminders), key=lambda x: x[0])
    if reminders:
        reminders_text = "<b>Нагадування для вашого блоку:</b>\n"
        for tm, rem in reminders:
            reminders_text += f"— {tm}: {rem}\n"
        await message.answer(reminders_text, parse_mode="HTML", reply_markup=user_menu)

# --- ПЛАНУВАЛЬНИК і ЗАПУСК ---
def refresh_block_tasks():
    print("[REFRESH] Оновлення завдань з Google Sheet")
    schedule_all_block_tasks_for_today()

async def main():
    loop = asyncio.get_running_loop()
    scheduler.start()
    schedule_all_block_tasks_for_today()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
