import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
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
    "Замовлення сайту": "1) Перевірити актуальність, уточнити у менеджера сайта\n2) Всі замовлення мають стікер з № замовлення\n3) Зарядити вживані телефони\n4) Вживані телефони в фірмових коробках\n5) Все відкладено на поличці замовлень\n6) Перевірити закази на складі",
    "Замовлення наші": "1) Звірити товар факт/база\n2) Проінформувати клієнта про наявність (за потреби)\n3) Поновити резерви (за потреби)\n4) Техніка підписана відповідальним\n5) Зарядити б/у телефони\n6) Неактуальні закази закрити",
    "OLХ": "1) Відповідати на повідомлення\n2) Перевірити кількість оголошень (більше 45)\n3) Запустити рекламу (7-9 оголошень)\n4) Звірити актуальність цін",
    "Стани техніка і тел.": "1) На всю б/у техніку та телефони мають стояти актуальні стани\n2) Контролювати проставлення станів після прийняття в Trade-in",
    "Цінники": "1) Перевірити всю б/у техніку на якість наклеєних цінників\n2) Перевірити якість поклейки цінників на всій техніці (в тому числі і шоурум)\n3) Перевірити наявні переоцінки, та проконтролювати переклейку",
    "Звіт-витрати": "1) Всі витрати мають бути проведені по базі\n2) Перевірити правильність проведення (правильні статті)\n3) Зробити та скинути файл exel в групу \"Звіти\" з усіма чеками",
    "Перевірка переміщень": "1) Перевірити переміщення яким більше двох днів (ГО, Склади, містами)\n2) Переглянути переміщення по Одесі між магазинами за минулі дні\n3) Знайти всі переміщення фізично або розібратись чому воно не доїхало на магазин."
    # Додавай інші за потреби
}

REMINDER_TIMES = [
    ("Саме час перевірити телефони на включення Looper та їх чистоту", ["10:46", "10:47", "10:20"]),
    ("Перевір, щоб на одному обліковому запису було не більше 10 пристроїв", ["10:47"]),
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
    chat_id = context.job.chat_id
    text = context.job.data
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Готово", callback_data=f"done:{text}")]])
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=kb
    )

async def reminder_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reminder_text = query.data.replace("done:", "")
    await query.edit_message_text(f"✅ Виконано: {reminder_text}")

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
            workers = user_state[user_id]["workers"]
            block = user_state[user_id]["block"]
            tasks = TASKS[workers][block]
            # --- Нагадування: асинхронно ---
            if "Черговий (-a)" in tasks:
                now = datetime.datetime.now(KYIV_TZ)
                for msg, times in REMINDER_TIMES:
                    for t in times:
                        h, m = map(int, t.split(":"))
                        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if target < now:
                            # Надсилаємо без await!
                            context.application.create_task(
                                context.bot.send_message(
                                    chat_id=user_id,
                                    text=msg,
                                    reply_markup=InlineKeyboardMarkup(
                                        [[InlineKeyboardButton("Готово", callback_data=f"done:{msg}")]]
                                    )
                                )
                            )
                        else:
                            delay = (target - now).total_seconds()
                            context.application.job_queue.run_once(
                                send_reminder, delay, chat_id=user_id, data=msg
                            )
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
    app.add_handler(CallbackQueryHandler(reminder_done, pattern="^done:"))
    app.run_polling()