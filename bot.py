import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
TOKEN = "7623138223:AAFbvuzI9GxfGw8nKULGBhTzJWKOiOMxF4g"

# Завдання по блоках
TASKS = {
    6: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        3: ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        4: ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        6: ["Каса", "Запити 'Нова Техніка'", "Запити 'Акси'"],
    },
    7: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        3: ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        4: ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        6: ["Каса", "Запити 'Акси'"],
        7: ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
    },
    8: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Запити Сайту"],
        3: ["Замовлення наші", "Прийомка товару"],
        4: ["OLХ", "Стани техніка і тел.", "Прийомка товару"],
        5: ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        6: ["Каса"],
        7: ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
        8: ["Перевірка переміщень", "Стіна аксесуарів", "Запити 'Акси'"],
    },
    9: {
        1: ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        2: ["Замовлення сайту", "Запити Сайту"],
        3: ["Замовлення наші", "Прийомка товару"],
        4: ["OLХ", "Прийомка товару"],
        5: ["Цінники", "Прийомка товару"],
        6: ["Каса"],
        7: ["Звіт-витрати", "Запити 'Нова Техніка'", "Прийомка товару"],
        8: ["Перевірка переміщень", "Стіна аксесуарів", "Запити 'Акси'"],
        9: ["Стани техніка і тел.", "Зарядка телефонів"],
    }
}

# Інструкція
INSTRUCTION = (
    "✅ Інструкція:\n\n"
    "*Чергування:*\n"
    "- Відкрити зміну ТОВ\n- Звести касу на ранок\n- Перевірити пропущені Binotel\n"
    "- Ранкове прибирання:\n  1) Протерти скло вітрин\n  2) Вологе прибирання поверхонь\n"
    "  3) Протерти чохли від пилу\n  4) Прибрати дитячу зону\n  5) Помити підлогу\n\n"
    "*Підсобка:*\n"
    "  1) Порядок на стелажах\n  2) Порядок на робочому столі\n"
    "  3) Порядок в касовій зоні\n  4) Віднести габаритну техніку на склад"
)

def back_button():
    return [KeyboardButton("⬅️ Назад")]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[KeyboardButton(str(i)) for i in [6, 7, 8, 9]], back_button()]
    await update.message.reply_text(
        "Привіт! Скільки працівників на зміні?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    context.user_data.clear()

async def handle_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await start(update, context)
    if update.message.text.isdigit() and int(update.message.text) in TASKS:
        count = int(update.message.text)
        context.user_data['workers'] = count
        buttons = [[KeyboardButton(str(i)) for i in range(1, count + 1)], back_button()]
        await update.message.reply_text("Оберіть свій блок завдань:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
    else:
        await update.message.reply_text("Будь ласка, оберіть кількість працівників (6-9) або натисніть Назад.")

async def handle_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        return await start(update, context)
    workers = context.user_data.get('workers')
    if update.message.text.isdigit() and workers and int(update.message.text) in TASKS[workers]:
        block = int(update.message.text)
        context.user_data['block'] = block
        tasks = TASKS[workers][block]
        buttons = [[KeyboardButton(task)] for task in tasks] + [back_button()]
        await update.message.reply_text("Виберіть завдання для старту:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))
    else:
        await update.message.reply_text("Будь ласка, оберіть блок або натисніть Назад.")

async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        workers = context.user_data.get('workers')
        return await handle_workers(update, context) if workers else await start(update, context)
    await update.message.reply_text(f"Ти обрав завдання: {update.message.text}")
    await update.message.reply_text(INSTRUCTION, parse_mode=constants.ParseMode.MARKDOWN)
    buttons = [[KeyboardButton("✅ Виконано")], back_button()]
    await update.message.reply_text("Після виконання натисни «✅ Виконано»", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        block = context.user_data.get('block')
        workers = context.user_data.get('workers')
        return await handle_blocks(update, context) if block and workers else await start(update, context)
    if update.message.text == "✅ Виконано":
        await update.message.reply_text("✅ Завдання відмічено як виконане!")
        return await start(update, context)

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^[6-9]$|⬅️ Назад"), handle_workers))
    app.add_handler(MessageHandler(filters.Regex("^[1-9]$"), handle_blocks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tasks))
    app.add_handler(MessageHandler(filters.Regex("^✅ Виконано$|⬅️ Назад"), handle_done))
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())