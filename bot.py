import os
import datetime
import pytz
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.environ.get("TOKEN")
user_state = {}

KYIV_TZ = pytz.timezone('Europe/Kyiv')

# === Словник завдань ===
TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", "Запити \"Нова Техніка\"", "Запити \"Акси\""]
    }
    # Додай аналогічно для 7, 8, 9 працівників!
}

# === Інструкції для завдань ===
INSTRUCTIONS = {
    "Черговий (-a)": "1) Відкрити зміну...\n2) Звести касу на ранок...",
    "Цінники": "1) Перевірити всю б/у техніку на якість наклеєних цінників...",
    "Замовлення сайту": "1) Перевірити актуальність, уточнити у менеджера сайта...",
    # Додавай інші інструкції
}

# === Індивідуальні нагадування ===
REMINDERS = {
    "Черговий (-a)": [
        {"time": "10:10", "text": "Перевірити телефони Looper!"},
        {"time": "10:30", "text": "Оновити статуси в чаті!"},
    ],
    "Цінники": [
        {"time": "12:00", "text": "Зроби перевірку цінників!"},
    ],
    "Замовлення сайту": [
        {"time": "14:00", "text": "Перевір актуальність замовлень сайту."}
    ]
    # Додавай ще
}

# === Start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "waiting_start"}
    kb = [[KeyboardButton("▶️ Початок робочого дня")]]
    await update.message.reply_text(
        "Натисніть «Початок робочого дня», щоб розпочати.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

# === Надсилання нагадування з кнопкою ===
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = context.job.data
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Готово", callback_data=f"reminder_done:{data['task']}:{data['text']}")
    ]])
    await context.bot.send_message(
        chat_id=chat_id,
        text=data["text"],
        reply_markup=kb
    )

# === Кнопка Готово ===
async def reminder_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, task, reminder_text = query.data.split(":", 2)
    user_id = query.from_user.id
    if "done_reminders" not in user_state.get(user_id, {}):
        user_state[user_id]["done_reminders"] = []
    user_state[user_id]["done_reminders"].append((task, reminder_text))
    await query.edit_message_text(f"✅ Виконано: {reminder_text}")

# === Головний хендлер ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = user_state.get(user_id, {"step": "waiting_start"})

    if state["step"] == "waiting_start":
        if text == "▶️ Початок робочого дня":
            user_state[user_id] = {"step": "workers"}
            kb = [[KeyboardButton(str(i))] for i in range(6, 10)]
            kb.append([KeyboardButton("⬅️ Назад")])
            await update.message.reply_text(
                "Оберіть кількість працівників на зміні:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
        return

    if state["step"] == "workers":
        if text == "⬅️ Назад":
            await start(update, context)
            return
        if text.isdigit() and int(text) in TASKS:
            user_state[user_id] = {"step": "block", "workers": int(text)}
            kb = [[KeyboardButton(str(i))] for i in TASKS[int(text)]]
            kb.append([KeyboardButton("⬅️ Назад")])
            await update.message.reply_text(
                "Оберіть свій блок:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
        return

    if state["step"] == "block":
        if text == "⬅️ Назад":
            user_state[user_id] = {"step": "workers"}
            kb = [[KeyboardButton(str(i))] for i in range(6, 10)]
            kb.append([KeyboardButton("⬅️ Назад")])
            await update.message.reply_text(
                "Оберіть кількість працівників на зміні:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
            return
        workers = state["workers"]
        if text in TASKS[workers]:
            user_state[user_id].update({"step": "confirm_block", "block": text})
            kb = [
                [KeyboardButton(f"✅ Так, блок {text}")],
                [KeyboardButton("⬅️ Назад")]
            ]
            await update.message.reply_text(
                f"Ви впевнені, що обрали блок {text}? Після підтвердження змінити не можна.",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
        return

    if state["step"] == "confirm_block":
        if text == "⬅️ Назад":
            user_state[user_id]["step"] = "block"
            workers = user_state[user_id]["workers"]
            kb = [[KeyboardButton(str(i))] for i in TASKS[workers]]
            kb.append([KeyboardButton("⬅️ Назад")])
            await update.message.reply_text(
                "Оберіть свій блок:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
            return
        if text.startswith("✅ Так, блок"):
            user_state[user_id]["step"] = "tasks"
            user_state[user_id]["done"] = []
            user_state[user_id]["done_reminders"] = []
            workers = user_state[user_id]["workers"]
            block = user_state[user_id]["block"]
            tasks = TASKS[workers][block]
            # --- Індивідуальні нагадування для кожного завдання ---
            now = datetime.datetime.now(KYIV_TZ)
            for task in tasks:
                if task in REMINDERS:
                    for r in REMINDERS[task]:
                        h, m = map(int, r["time"].split(":"))
                        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if target < now:
                            # Надіслати одразу
                            context.application.create_task(
                                context.bot.send_message(
                                    chat_id=user_id,
                                    text=r["text"],
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("Готово", callback_data=f"reminder_done:{task}:{r['text']}")]
                                    ])
                                )
                            )
                        else:
                            delay = (target - now).total_seconds()
                            job = context.application.job_queue.run_once(
                                send_reminder, delay, chat_id=user_id, data={"task": task, "text": r["text"]}
                            )
                            if "jobs" not in user_state[user_id]:
                                user_state[user_id]["jobs"] = []
                            user_state[user_id]["jobs"].append(job)
            kb = [[KeyboardButton(task)] for task in tasks]
            kb.append([KeyboardButton("⬅️ Назад")])
            kb.append([KeyboardButton("⏹ Завершити робочий день")])
            await update.message.reply_text(
                f"Ваші завдання на сьогодні (блок {block}):",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
            return

    if state["step"] == "tasks":
        if text == "⬅️ Назад":
            await update.message.reply_text("Повернення назад неможливе після підтвердження блоку!")
            return
        if text == "⏹ Завершити робочий день":
            # Видалити jobs, очистити стейт
            if "jobs" in user_state[user_id]:
                for job in user_state[user_id]["jobs"]:
                    job.schedule_removal()
            user_state[user_id] = {"step": "waiting_start"}
            kb = [[KeyboardButton("▶️ Початок робочого дня")]]
            await update.message.reply_text(
                "День завершено! Дякуємо за роботу.",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
            return
        workers = state["workers"]
        block = state["block"]
        if text in TASKS[workers][block]:
            instruction = INSTRUCTIONS.get(text, "Інструкція до цього завдання відсутня.")
            user_state[user_id]["done"].append(text)
            await update.message.reply_text(f"Інструкція для завдання «{text}»:\n{instruction}")
        return

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(reminder_done, pattern="^reminder_done:"))
    app.run_polling()