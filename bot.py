import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import datetime
import pytz

TOKEN = os.environ.get("TOKEN")
user_state = {}

TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", "Запити \"Нова Техніка\"", "Запити \"Акси\""]
    },
    7: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса", "Запити \"Акси\""],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"]
    },
    8: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Запити Сайту"],
        "3": ["Замовлення наші", "Прийомка товару"],
        "4": ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса"],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"],
        "8": ["Перевірка переміщень", "Стіна аксесуарів", "Запити \"Акси\""]
    },
    9: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Запити Сайту"],
        "3": ["Замовлення наші", "Прийомка товару"],
        "4": ["OLХ", "Прийомка товару"],
        "5": ["Цінники", "Прийомка товару"],
        "6": ["Каса"],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"],
        "8": ["Перевірка переміщень", "Стіна аксесуарів", "Запити \"Акси\""],
        "9": ["Стани техніка і тел.", "Зарядка телефонів"]
    }
}

INSTRUCTIONS = {
    "Черговий (-a)": "1) Відкрити зміну...\n2) Звести касу на ранок...",
    "Замовлення сайту": "1) Перевірити актуальність...",
    "Цінники": "1) Перевірити всю б/у техніку...",
    # та інші інструкції
}

REMINDER_TIMES = [
    ("Саме час перевірити телефони на включення Looper та їх чистоту", ["10:10", "10:15", "10:20"]),
    ("Перевір, щоб на одному обліковому запису було не більше 10 пристроїв", ["10:30"]),
    ("Не забудь перевірити групу сайту", ["10:40"])
]

KYIV_TZ = pytz.timezone('Europe/Kyiv')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "waiting_start"}
    kb = [[KeyboardButton("▶️ Початок робочого дня")]]
    await update.message.reply_text(
        "Натисніть «Початок робочого дня», щоб розпочати.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=context.job.data
    )

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
            return await start(update, context)
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
            return await update.message.reply_text(
                "Оберіть кількість працівників на зміні:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
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
            return await update.message.reply_text(
                "Оберіть свій блок:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
        if text.startswith("✅ Так, блок"):
            user_state[user_id]["step"] = "tasks"
            user_state[user_id]["done"] = []
            workers = user_state[user_id]["workers"]
            block = user_state[user_id]["block"]
            tasks = TASKS[workers][block]
            # --- Додаємо нагадування ---
            if "Черговий (-a)" in tasks:
                now = datetime.datetime.now(KYIV_TZ)
                for msg, times in REMINDER_TIMES:
                    for t in times:
                        h, m = map(int, t.split(":"))
                        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if target < now:
                            # Якщо вже минуло, відправляємо одразу!
                            context.application.create_task(
                                context.bot.send_message(chat_id=user_id, text=msg)
                            )
                        else:
                            delay = (target - now).total_seconds()
                            context.application.job_queue.run_once(
                                send_reminder, delay, chat_id=user_id, data=msg
                            )
            # --- Меню завдань ---
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
    app.run_polling()