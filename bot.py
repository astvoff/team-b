import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.environ.get("TOKEN")
user_state = {}

TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
    },
}

REMINDERS = {
    "Черговий (-a)": [
        {"delay_sec": 10, "text": "Тестове нагадування для Чергового!"},
    ],
    "Замовлення сайту": [
        {"delay_sec": 10, "text": "Тестове нагадування для Замовлення сайту!"},
    ],
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {}
    kb = [[KeyboardButton("▶️ Початок робочого дня")]]
    await update.message.reply_text("Натисніть «Початок робочого дня», щоб розпочати.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(str(i))] for i in TASKS.keys()]
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

async def block_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.startswith("✅ Так, блок "):
        block = user_state[user_id]["block"]
        workers = user_state[user_id]["workers"]
        tasks = TASKS[workers][block]
        kb = [[KeyboardButton(t)] for t in tasks]
        await update.message.reply_text("Оберіть завдання:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def task_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    block = user_state[user_id]["block"]
    workers = user_state[user_id]["workers"]
    tasks = TASKS[workers][block]
    if text in tasks:
        await update.message.reply_text(f"Інструкція для завдання «{text}»")
        # Ось тут СТАРТУЄМО нагадування (через 10 сек)
        if text in REMINDERS:
            for r in REMINDERS[text]:
                context.application.job_queue.run_once(
                    send_reminder,
                    when=r["delay_sec"],
                    chat_id=user_id,
                    data={"text": r["text"]}
                )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = context.job.data
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Готово", callback_data="reminder_done")]
    ])
    await context.bot.send_message(chat_id=chat_id, text=data["text"], reply_markup=kb)

async def reminder_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("✅ Виконано! Дякую!")

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
    app.add_handler(CallbackQueryHandler(reminder_done_callback, pattern=r"reminder_done"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, task_instruction))
    app.run_polling()

if __name__ == "__main__":
    main()