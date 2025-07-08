import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get('TOKEN')

# Завдання по блоках
TASKS = {
    6: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        3: ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        4: ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        6: ["Каса", 'Запити "Нова Техніка"', 'Запити "Акси"'],
    },
    7: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        3: ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        4: ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        6: ["Каса", 'Запити "Акси"'],
        7: ["Звіт-витрати", 'Запити "Нова Техніка"', "Прийомка товару"],
    }
}

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("6 працівників", callback_data="workers_6")],
        [InlineKeyboardButton("7 працівників", callback_data="workers_7")],
    ]
    await update.message.reply_text("Виберіть кількість працівників на зміні:", reply_markup=InlineKeyboardMarkup(keyboard))

# Вибір кількості працівників
async def select_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    workers = int(query.data.split("_")[1])
    context.user_data["workers"] = workers

    keyboard = []
    for block in range(1, workers + 1):
        keyboard.append([InlineKeyboardButton(f"Блок {block}", callback_data=f"block_{block}")])

    await query.edit_message_text(
        text=f"Вибрано {workers} працівників. Тепер виберіть свій блок:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Вибір блоку
async def select_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    block = int(query.data.split("_")[1])
    context.user_data["block"] = block
    workers = context.user_data.get("workers", 6)

    tasks = TASKS.get(workers, {}).get(block, ["Немає завдань для цього блоку"])

    # Відправляємо перелік завдань
    await query.edit_message_text(
        text=f"Ваші завдання для блоку {block}:\n" + "\n".join(f"🔹 {task}" for task in tasks)
    )

    # Запитуємо, з чого почне
    keyboard = []
    for idx, task in enumerate(tasks, start=1):
        keyboard.append([InlineKeyboardButton(f"{task}", callback_data=f"starttask_{idx}")])

    await query.message.reply_text(
        "З якого завдання ти почнеш?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обробка вибору завдання
async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    task_idx = int(query.data.split("_")[1])
    workers = context.user_data.get("workers", 6)
    block = context.user_data.get("block", 1)

    task = TASKS.get(workers, {}).get(block, ["Немає завдань"])[task_idx - 1]

    await query.edit_message_text(text=f"Добре, починай із завдання: ✅ {task}")

# Основний запуск
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_workers, pattern=r"^workers_\d+$"))
    app.add_handler(CallbackQueryHandler(select_block, pattern=r"^block_\d+$"))
    app.add_handler(CallbackQueryHandler(start_task, pattern=r"^starttask_\d+$"))

    print("Бот запущено.")
    app.run_polling()

if __name__ == '__main__':
    main()