import os
import pytz
from datetime import datetime, time as dtime, timedelta
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = os.environ.get("TOKEN")
KYIV_TZ = pytz.timezone("Europe/Kyiv")

TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", "Запити \"Нова Техніка\"", "Запити \"Акси\""],
    },
    # Додаєш 7,8,9 по аналогії!
}

REMINDERS = {
    "Черговий (-a)": [
        {"time": dtime(10, 10), "text": "Саме час перевірити телефони на включення Looper та їх чистоту"},
        {"time": dtime(10, 30), "text": "Перевір, щоб на одному обліковому запису було не більше 10 пристроїв"},
        {"time": dtime(10, 40), "text": "Не забудь перевірити групу сайту"}
    ]
}

user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {}
    kb = [[KeyboardButton("▶️ Початок робочого дня")]]
    await update.message.reply_text("Натисніть «Початок робочого дня», щоб розпочати.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(str(i))] for i in (6,7,8,9)]
    await update.message.reply_text("Оберіть кількість працівників на зміні:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def select_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.isdigit() and int(text) in TASKS:
        user_state[user_id]["workers"] = int(text)
        blocks = TASKS[int(text)]
        kb = [[KeyboardButton(str(i))] for i in blocks.keys()]
        kb.append([KeyboardButton("⬅️ Назад")])
        await update.message.reply_text("Оберіть свій блок:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    elif text == "⬅️ Назад":
        await main_menu(update, context)

async def confirm_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    workers = user_state[user_id].get("workers")
    if text in TASKS[workers]:
        user_state[user_id]["block"] = text
        kb = [
            [KeyboardButton(f"✅ Так, блок {text}")],
            [KeyboardButton("⬅️ Назад")]
        ]
        await update.message.reply_text(
            f"Ви впевнені, що обрали блок {text}? Після підтвердження змінити не можна.",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
    elif text == "⬅️ Назад":
        await main_menu(update, context)

async def block_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.startswith("✅ Так, блок "):
        block = user_state[user_id]["block"]
        workers = user_state[user_id]["workers"]
        tasks = TASKS[workers][block]
        kb = [[KeyboardButton(t)] for t in tasks]
        kb.append([KeyboardButton("⬅️ Назад")])
        await update.message.reply_text("Оберіть завдання:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    elif text == "⬅️ Назад":
        await select_block(update, context)

async def task_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    block = user_state[user_id]["block"]
    workers = user_state[user_id]["workers"]
    tasks = TASKS[workers][block]
    if text in tasks:
        instr = f"Інструкція для завдання «{text}»: Інструкція до цього завдання відсутня."
        if text == "Черговий (-a)":
            instr = (
                "Інструкція для завдання «Черговий (-a)»:\n"
                "1) Відкрити зміну ТОВ...\n"
                "2) Звести касу на ранок...\n"
                "3) Перевірити пропущені Binotel...\n"
                "4) Прибирання і т.д."
            )
        await update.message.reply_text(instr)
        if text in REMINDERS:
            for r in REMINDERS[text]:
                reminder_id = f"{text}_{r['time']}".replace(" ", "_")[:50]
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Готово", callback_data=f"reminder_done:{reminder_id}")]
                ])
                now = datetime.now(KYIV_TZ)
                scheduled = datetime.combine(now.date(), r["time"]).replace(tzinfo=KYIV_TZ)
                if scheduled < now:
                    scheduled = now + timedelta(seconds=2)
                context.application.job_queue.run_once(
                    send_reminder,
                    when=(scheduled - now).total_seconds(),
                    chat_id=user_id,
                    data={"task": text, "text": r["text"], "time": r["time"].strftime("%H:%M")}
                )
        kb = [[KeyboardButton("⬅️ Назад")]]
        await update.message.reply_text("Після виконання натисни «Готово» у нагадуванні!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    elif text == "⬅️ Назад":
        await block_tasks(update, context)

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = context.job.data
    reminder_id = f"{data['task']}_{data['time']}".replace(" ", "_")[:50]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Готово", callback_data=f"reminder_done:{reminder_id}")]
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text=data["text"],
        reply_markup=kb
    )

async def reminder_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Виконано! Дякую!")

async def route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "/start":
        return await start(update, context)
    if text == "▶️ Початок робочого дня":
        return await main_menu(update, context)
    if user_id not in user_state or "workers" not in user_state[user_id]:
        return await select_block(update, context)
    if "block" not in user_state[user_id]:
        return await confirm_block(update, context)
    return await block_tasks(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(reminder_done_callback, pattern=r"^reminder_done:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route))
    app.run_polling()

if __name__ == "__main__":
    main()