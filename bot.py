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
    user_id = update.effective_user.id
    user_state[user_id] = {"state": "start"}
    kb = [[KeyboardButton("▶️ Початок робочого дня")]]
    await update.message.reply_text("Натисніть «Початок робочого дня», щоб розпочати.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"state": "workers"}
    kb = [[KeyboardButton(str(i))] for i in TASKS.keys()]
    await update.message.reply_text("Оберіть кількість працівників на зміні:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def select_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    workers = int(update.message.text)
    user_state[user_id].update({"workers": workers, "state": "block"})
    blocks = TASKS[workers]
    kb = [[KeyboardButton(str(i))] for i in blocks.keys()]
    kb.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text("Оберіть свій блок:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def confirm_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    block = update.message.text
    user_state[user_id].update({"block": block, "state": "confirm_block"})
    kb = [
        [KeyboardButton(f"✅ Так, блок {block}")],
        [KeyboardButton("⬅️ Назад")]
    ]
    await update.message.reply_text(
        f"Ви впевнені, що обрали блок {block}? Після підтвердження змінити не можна.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def block_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    workers = user_state[user_id]["workers"]
    block = user_state[user_id]["block"]
    tasks = TASKS[workers][block]
    user_state[user_id].update({"state": "tasks", "current_tasks": set(tasks), "completed_tasks": set()})
    kb = [[KeyboardButton(t)] for t in tasks]
    kb.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text(
        "Оберіть завдання:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def task_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    workers = user_state[user_id]["workers"]
    block = user_state[user_id]["block"]
    tasks = TASKS[workers][block]
    if text in tasks and text not in user_state[user_id]["completed_tasks"]:
        user_state[user_id]["state"] = "task_detail"
        user_state[user_id]["current_task"] = text
        kb = [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]]
        await update.message.reply_text(f"Інструкція для завдання «{text}»", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    elif text in user_state[user_id]["completed_tasks"]:
        await update.message.reply_text("Завдання вже виконано!")

async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if "current_task" in user_state[user_id]:
        task = user_state[user_id]["current_task"]
        user_state[user_id]["completed_tasks"].add(task)
        del user_state[user_id]["current_task"]
        workers = user_state[user_id]["workers"]
        block = user_state[user_id]["block"]
        tasks = TASKS[workers][block]
        left_tasks = [t for t in tasks if t not in user_state[user_id]["completed_tasks"]]
        user_state[user_id]["state"] = "tasks"
        if left_tasks:
            kb = [[KeyboardButton(t)] for t in left_tasks]
            kb.append([KeyboardButton("⬅️ Назад")])
            await update.message.reply_text(f"Завдання «{task}» виконано! Оберіть наступне:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        else:
            await update.message.reply_text("Всі завдання виконані! Дякуємо 🎉")
    else:
        await update.message.reply_text("Спочатку оберіть завдання.")

async def route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # СТАРТ
    if text == "/start":
        return await start(update, context)

    state = user_state.get(user_id, {}).get("state", "start")

    # На кожному етапі: якщо "⬅️ Назад", повертаємося на попередній крок
    if text == "⬅️ Назад":
        if state == "block":
            return await main_menu(update, context)
        if state == "confirm_block":
            return await select_block(update, context)
        if state == "tasks":
            return await confirm_block(update, context)
        if state == "task_detail":
            return await block_tasks(update, context)

    # Розпочати день
    if text == "▶️ Початок робочого дня":
        return await main_menu(update, context)

    # Вибір кількості працівників
    if state == "workers" and text.isdigit() and int(text) in TASKS:
        return await select_block(update, context)

    # Вибір блоку
    if state == "block" and text in TASKS[user_state[user_id]["workers"]]:
        return await confirm_block(update, context)

    # Підтвердження блоку
    if state == "confirm_block" and text.startswith("✅ Так, блок "):
        return await block_tasks(update, context)

    # Вибір завдання
    if state == "tasks" and text in TASKS[user_state[user_id]["workers"]][user_state[user_id]["block"]]:
        return await task_instruction(update, context)

    # Відмітка виконання
    if state == "task_detail" and text == "✅ Виконано":
        return await mark_done(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route))
    app.run_polling()

if __name__ == "__main__":
    main()