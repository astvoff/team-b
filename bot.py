import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(str(i))] for i in range(6, 10)]
    await update.message.reply_text(
        "Оберіть кількість працівників на зміні:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.isdigit() and int(text) in TASKS:
        user_state[user_id] = {"workers": int(text)}
        kb = [[KeyboardButton(str(i))] for i in TASKS[int(text)]]
        await update.message.reply_text(
            "Оберіть свій блок:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
    elif user_id in user_state and "workers" in user_state[user_id]:
        workers = user_state[user_id]["workers"]
        if text in TASKS[workers]:
            tasks = "\n".join(TASKS[workers][text])
            await update.message.reply_text(f"Ваші завдання на сьогодні:\n{tasks}")

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()