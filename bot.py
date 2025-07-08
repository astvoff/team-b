import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get('TOKEN')

# Прикладова структура завдань по блоках
TASKS = {
    6: {
        1: ["Завдання 1.1", "Завдання 1.2"],
        2: ["Завдання 2.1", "Завдання 2.2"],
        3: ["Завдання 3.1", "Завдання 3.2"],
        4: ["Завдання 4.1", "Завдання 4.2"],
        5: ["Завдання 5.1", "Завдання 5.2"],
        6: ["Завдання 6.1", "Завдання 6.2"],
    },
    7: {
        1: ["Завдання 1.1", "Завдання 1.2"],
        7: ["Завдання 7.1", "Завдання 7.2"],
    },
    8: {
        1: ["Завдання 1.1", "Завдання 1.2"],
        8: ["Завдання 8.1", "Завдання 8.2"],
    },
    9: {
        1: ["Завдання 1.1", "Завдання 1.2"],
        9: ["Завдання 9.1", "Завдання 9.2"],
    },
}

# Запуск /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("6 працівників", callback_data="workers_6")],
        [InlineKeyboardButton("7 працівників", callback_data="workers_7")],
        [InlineKeyboardButton("8 працівників", callback_data="workers_8")],
        [InlineKeyboardButton("9 працівників", callback_data="workers_9")],
    ]
    await update.message.reply_text("Виберіть кількість працівників на зміні:", reply_markup=InlineKeyboardMarkup(keyboard))

# Обробка вибору кількості працівників
async def select_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    workers = int(query.data.split("_")[1])
    context.user_data["workers"] = workers

    # Генеруємо кнопки для вибору блоку
    keyboard = []
    for block in range(1, workers + 1):
        keyboard.append([InlineKeyboardButton(f"Блок {block}", callback_data=f"block_{block}")])

    await query.edit_message_text(
        text=f"Вибрано {workers} працівників. Тепер виберіть свій блок:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обробка вибору блоку
async def select_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    block = int(query.data.split("_")[1])
    workers = context.user_data.get("workers", 6)

    tasks = TASKS.get(workers, {}).get(block, ["Немає завдань для цього блоку"])

    await query.edit_message_text(
        text=f"Ваші завдання для блоку {block}:\n" + "\n".join(f"🔹 {task}" for task in tasks)
    )

# Запуск бота
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_workers, pattern=r"^workers_\d+$"))
    app.add_handler(CallbackQueryHandler(select_block, pattern=r"^block_\d+$"))

    print("Бот запущено.")
    app.run_polling()

if __name__ == '__main__':
    main()