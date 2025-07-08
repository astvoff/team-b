import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ.get('TOKEN')

logging.basicConfig(level=logging.INFO)

INSTRUCTION_TEXT = """
📋 Інструкція до завдання:

🔸 Чергування:
- Відкрити зміну ТОВ
- Звести касу на ранок
- Перевірити пропущені Binotel
- Ранкове прибирання:
  1. Протерти скло вітрин
  2. Зробити вологе прибирання поверхонь
  3. Протерти чохли від пилу
  4. Прибрати дитячу зону
  5. Помити підлогу

🔸 Підсобка:
  1. Порядок на стелажах
  2. Порядок на робочому столі
  3. Порядок у касовій зоні
  4. Віднести техніку на склад
"""

tasks_by_shift = {
    "6": {
        "1": ["Чергування", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", "Запити 'Нова Техніка'", "Запити 'Акси'"]
    },
    "7": {
        "1": ["Чергування", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса", "Запити 'Акси'"],
        "7": ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"]
    },
    "8": {
        "1": ["Чергування", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Запити Сайту"],
        "3": ["Замовлення наші", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса"],
        "7": ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
        "8": ["Перевірка переміщень", "Стіна аксесуарів", "Запити 'Акси'"]
    },
    "9": {
        "1": ["Чергування", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Запити Сайту"],
        "3": ["Замовлення наші", "Прийомка товару"],
        "4": ["OLX", "Прийомка товару"],
        "5": ["Цінники", "Прийомка товару"],
        "6": ["Каса"],
        "7": ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
        "8": ["Перевірка переміщень", "Стіна аксесуарів", "Запити 'Акси'"],
        "9": ["Стани техніка і тел.", "Зарядка телефонів"]
    }
}

user_state = {}

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[KeyboardButton(i)] for i in ["6", "7", "8", "9"]]
    await update.message.reply_text(
        "👥 Скільки працівників на зміні?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    user_state[update.effective_chat.id] = {}

# ОБРОБКА КІЛЬКОСТІ
async def handle_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text not in tasks_by_shift:
        return await update.message.reply_text("Будь ласка, оберіть число від 6 до 9.")
    
    user_state[update.effective_chat.id]["workers"] = text
    blocks = tasks_by_shift[text].keys()
    buttons = [[KeyboardButton(str(i))] for i in blocks] + [[KeyboardButton("⬅️ Назад")]]
    await update.message.reply_text(
        "🔢 Оберіть свій блок:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# ОБРОБКА БЛОКУ
async def handle_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⬅️ Назад":
        return await start(update, context)
    
    chat_id = update.effective_chat.id
    workers = user_state[chat_id].get("workers")
    if text not in tasks_by_shift[workers]:
        return await update.message.reply_text("❗ Невірний номер блоку.")

    user_state[chat_id]["block"] = text
    tasks = tasks_by_shift[workers][text]
    buttons = [[KeyboardButton(t)] for t in tasks] + [[KeyboardButton("⬅️ Назад")]]
    await update.message.reply_text(
        "✅ Завдання блоку:\n" + "\n".join(f"– {t}" for t in tasks),
    )
    await update.message.reply_text(
        "🔽 З якого завдання ти почнеш?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# ОБРОБКА ЗАВДАННЯ
async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await handle_workers(update, context)

    task = update.message.text
    await update.message.reply_text(f"🛠️ Обране завдання: *{task}*", parse_mode='Markdown')
    await update.message.reply_text(INSTRUCTION_TEXT)
    buttons = [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]]
    await update.message.reply_text(
        "Після виконання натисни «✅ Виконано»",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# ПІДТВЕРДЖЕННЯ
async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await handle_blocks(update, context)
    if update.message.text == "✅ Виконано":
        await update.message.reply_text("✅ Завдання завершено!")
        return await start(update, context)

# MAIN
async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^(6|7|8|9)$"), handle_workers))
    app.add_handler(MessageHandler(filters.Regex("^[1-9]$"), handle_blocks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tasks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_done))
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())