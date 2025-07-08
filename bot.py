import os
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

TOKEN = os.environ.get("TOKEN")  # Або заміни на прямий токен як "123456:ABC..."
user_state = {}

TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", "Запити \"Нова Техніка\"", "Запити \"Акси\""]
    },
    7: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса", "Запити \"Акси\""],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"]
    },
    8: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Запити Сайту"],
        "3": ["Замовлення наші", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса"],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"],
        "8": ["Перевірка переміщень", "Стіна аксесуарів", "Запити \"Акси\""]
    },
    9: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Запити Сайту"],
        "3": ["Замовлення наші", "Прийомка товару"],
        "4": ["OLX", "Прийомка товару"],
        "5": ["Цінники", "Прийомка товару"],
        "6": ["Каса"],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"],
        "8": ["Перевірка переміщень", "Стіна аксесуарів", "Запити \"Акси\""],
        "9": ["Стани техніка і тел.", "Зарядка телефонів"]
    }
}

INSTRUCTION = """🔹 *Інструкція до виконання:*
— Відкрити зміну ТОВ
— Звести касу на ранок
— Перевірити пропущені Binotel
— Ранкове прибирання:
  1) Протерти скло вітрин
  2) Вологе прибирання поверхонь
  3) Протерти чохли
  4) Прибрати дитячу зону
  5) Помити підлогу
— Підсобка:
  1) Порядок на стелажах
  2) Порядок на столі
  3) Порядок у касовій зоні
  4) Віднести техніку на склад
"""

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id] = {}
    buttons = [[KeyboardButton(str(n))] for n in range(6, 10)]
    await update.message.reply_text(
        "Скільки працівників на зміні?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# Вибір кількості
async def handle_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⬅️ Назад":
        return await start(update, context)
    if text.isdigit() and int(text) in TASKS:
        user_state[update.effective_user.id]["workers"] = int(text)
        blocks = TASKS[int(text)]
        buttons = [[KeyboardButton(k)] for k in blocks.keys()]
        buttons.append([KeyboardButton("⬅️ Назад")])
        await update.message.reply_text(
            "Оберіть свій блок завдань:",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )
    else:
        await update.message.reply_text("Будь ласка, оберіть число від 6 до 9.")

# Вибір блоку
async def handle_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⬅️ Назад":
        return await handle_workers(update, context)
    workers = user_state[update.effective_user.id]["workers"]
    blocks = TASKS.get(workers, {})
    if text in blocks:
        user_state[update.effective_user.id]["block"] = text
        tasks = blocks[text]
        buttons = [[KeyboardButton(t)] for t in tasks]
        buttons.append([KeyboardButton("⬅️ Назад")])
        await update.message.reply_text(
            "Оберіть, з якого завдання почати:",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )
    else:
        await update.message.reply_text("Оберіть правильний блок.")

# Завдання
async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await handle_blocks(update, context)
    task = update.message.text
    await update.message.reply_text(f"🛠 Обране завдання: *{task}*", parse_mode="Markdown")
    await update.message.reply_text(INSTRUCTION, parse_mode="Markdown")
    buttons = [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]]
    await update.message.reply_text(
        "Після виконання натисни «✅ Виконано»",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# Завершення
async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await handle_blocks(update, context)
    if update.message.text == "✅ Виконано":
        await update.message.reply_text("✅ Завдання виконано. Гарна робота! 💪")
        return await start(update, context)

# Запуск
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^[6-9]$"), handle_workers))
    app.add_handler(MessageHandler(filters.Regex("^[1-9]$"), handle_blocks))
    app.add_handler(MessageHandler(filters.Regex("^(?!⬅️ Назад$).*"), handle_tasks))
    app.add_handler(MessageHandler(filters.TEXT, handle_done))
    app.run_polling()

if __name__ == "__main__":
    main()