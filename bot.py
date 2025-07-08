from pathlib import Path

# Повний код Telegram-бота (в одному файлі)
code = '''
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
import logging
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get('TOKEN')

logging.basicConfig(level=logging.INFO)

# Інструкція для всіх завдань
INSTRUCTION = """🧾 Інструкція:
Чергування:
• Відкрити зміну ТОВ
• Звести касу на ранок
• Перевірити пропущені Binotel
• Ранкове прибирання:
  1. Протерти скло вітрин
  2. Зробити вологе прибирання поверхонь
  3. Протерти чохли від пилу
  4. Прибрати дитячу зону
  5. Помити підлогу

Підсобка:
  1. Порядок на стелажах
  2. Порядок на робочому столі
  3. Порядок в касовій зоні
  4. Віднести габаритну техніку на склад
"""

# Завдання по блоках залежно від кількості працівників
TASKS = {
    6: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        3: ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        4: ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        6: ["Каса", "Запити 'Нова Техніка'", "Запити 'Акси'"]
    },
    7: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        3: ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        4: ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        6: ["Каса", "Запити 'Акси'"],
        7: ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"]
    },
    8: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Запити Сайту"],
        3: ["Замовлення наші", "Прийомка товару"],
        4: ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        6: ["Каса"],
        7: ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
        8: ["Перевірка переміщень", "Стіна аксесуарів", "Запити 'Акси'"]
    },
    9: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Запити Сайту"],
        3: ["Замовлення наші", "Прийомка товару"],
        4: ["OLX", "Прийомка товару"],
        5: ["Цінники", "Прийомка товару"],
        6: ["Каса"],
        7: ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
        8: ["Перевірка переміщень", "Стіна аксесуарів", "Запити 'Акси'"],
        9: ["Стани техніка і тел.", "Зарядка телефонів"]
    }
}

user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[KeyboardButton(str(i))] for i in range(6, 10)]
    await update.message.reply_text("Скільки працівників на зміні?", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
    return

async def handle_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⬅️ Назад":
        return await start(update, context)

    if not text.isdigit() or int(text) not in TASKS:
        return await update.message.reply_text("Будь ласка, обери від 6 до 9.")

    user_data[update.effective_user.id] = {"workers": int(text)}
    max_block = len(TASKS[int(text)])
    buttons = [[KeyboardButton(str(i))] for i in range(1, max_block + 1)]
    buttons.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text("Оберіть свій блок завдань:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

async def handle_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⬅️ Назад":
        return await handle_workers(update, context)

    if not text.isdigit():
        return

    user_data[update.effective_user.id]["block"] = int(text)
    workers = user_data[update.effective_user.id]["workers"]
    tasks = TASKS[workers][int(text)]

    buttons = [[KeyboardButton(task)] for task in tasks]
    buttons.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text(
        "Оберіть, з якого завдання почати:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await handle_blocks(update, context)

    task = update.message.text
    await update.message.reply_text(f"🔧 Обране завдання: {task}")
    await update.message.reply_text(INSTRUCTION)

    buttons = [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]]
    await update.message.reply_text(
        "Після виконання натисни «✅ Виконано»",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await handle_blocks(update, context)

    if update.message.text == "✅ Виконано":
        await update.message.reply_text("✅ Завдання виконано. Гарна робота!")
        return await start(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^[6-9]$"), handle_workers))
    app.add_handler(MessageHandler(filters.Regex("^[1-9]$"), handle_blocks))
    app.add_handler(MessageHandler(filters.Regex("^(?!✅ Виконано$|⬅️ Назад$).+"), handle_tasks))
    app.add_handler(MessageHandler(filters.Regex("^(✅ Виконано|⬅️ Назад)$"), handle_done))
    app.run_polling()

if __name__ == "__main__":
    main()
'''

# Зберігаємо у файл
file_path = Path("/mnt/data/telegram_task_bot.py")
file_path.write_text(code.strip())
file_path.name