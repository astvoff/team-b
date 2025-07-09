import os
import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ.get("TOKEN")
user_state = {}
daily_blocks_taken = {}  # {date: {block_number: username}}

INSTRUCTION = """🧾 Інструкція до «Чергування»:
• Відкрити зміну ТОВ
• Звести касу на ранок
• Перевірити пропущені Binotel
• Ранкове прибирання:
   - Протерти скло
   - Вологе прибирання поверхонь
   - Протерти чохли
   - Прибрати дитячу зону
   - Помити підлогу
• Підсобка:
   - Порядок на стелажах, столі, касі
   - Віднести техніку на склад
"""

TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", "Запити \"Нова Техніка\"", "Запити \"Акси\""],
    },
    7: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Прийомка товару"],
        "6": ["Каса", "Запити \"Акси\""],
        "7": ["Звіт-витрати", "Запити \"Нова Техніка\"", "Прийомка товару"],
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id] = {"step": "start", "done": []}
    await update.message.reply_text(
        "Привіт! Щоб почати день, натисни:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("🚀 Розпочати день")]],
            resize_keyboard=True,
        ),
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"id_{user_id}"
    text = update.message.text
    state = user_state.get(user_id, {})
    step = state.get("step", "start")

    if text == "⬅️ Назад":
        return await go_back(update)

    if text == "🚀 Розпочати день":
        user_state[user_id]["step"] = "workers"
        return await update.message.reply_text(
            "Скільки працівників сьогодні на зміні?",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton(str(n))] for n in range(6, 10)],
                resize_keyboard=True,
            ),
        )

    if step == "workers":
        if text.isdigit() and int(text) in TASKS:
            user_state[user_id]["workers"] = int(text)
            user_state[user_id]["step"] = "block"
            return await show_blocks(update)
        else:
            return await update.message.reply_text("Оберіть число від 6 до 9")

    if step == "block":
        today = str(datetime.date.today())
        block_taken = daily_blocks_taken.get(today, {})
        if block_taken.get(text):
            return await update.message.reply_text("⛔ Цей блок уже зайнято іншим працівником сьогодні.")
        user_state[user_id]["selected_block"] = text
        user_state[user_id]["step"] = "confirm_block"
        return await update.message.reply_text(f"Ви точно обрали блок {text}?", reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("✅ Так")], [KeyboardButton("⬅️ Назад")]],
            resize_keyboard=True
        ))

    if step == "confirm_block":
        if text == "✅ Так":
            block = user_state[user_id]["selected_block"]
            today = str(datetime.date.today())
            daily_blocks_taken.setdefault(today, {})[block] = username
            user_state[user_id]["block"] = block
            user_state[user_id]["step"] = "tasks"
            return await show_tasks(update)
        else:
            user_state[user_id]["step"] = "block"
            return await show_blocks(update)

    if step == "tasks":
        if text.startswith("✅"):
            return
        user_state[user_id]["current_task"] = text
        user_state[user_id]["step"] = "in_task"
        if "Черг" in text:
            await update.message.reply_text(INSTRUCTION)
        return await update.message.reply_text(
            f"Завдання: {text}",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]],
                resize_keyboard=True,
            ),
        )

    if step == "in_task" and text == "✅ Виконано":
        task = user_state[user_id]["current_task"]
        user_state[user_id].setdefault("done", []).append((task, datetime.datetime.now()))
        user_state[user_id]["step"] = "tasks"
        return await show_tasks(update)

    if text == "🏁 Завершити день":
        return await end_day(update)

async def go_back(update):
    user_id = update.effective_user.id
    step = user_state[user_id].get("step")
    if step == "block":
        user_state[user_id]["step"] = "workers"
        return await update.message.reply_text("⬅️ Назад до вибору кількості працівників")
    elif step == "confirm_block":
        user_state[user_id]["step"] = "block"
        return await show_blocks(update)
    elif step == "tasks":
        user_state[user_id]["step"] = "block"
        return await show_blocks(update)
    elif step == "in_task":
        user_state[user_id]["step"] = "tasks"
        return await show_tasks(update)

async def show_blocks(update):
    user_id = update.effective_user.id
    blocks = TASKS[user_state[user_id]["workers"]].keys()
    buttons = [[KeyboardButton(b)] for b in blocks]
    return await update.message.reply_text("Оберіть свій блок:", reply_markup=ReplyKeyboardMarkup(buttons + [[KeyboardButton("⬅️ Назад")]], resize_keyboard=True))

async def show_tasks(update):
    user_id = update.effective_user.id
    workers = user_state[user_id]["workers"]
    block = user_state[user_id]["block"]
    done = [task for task, _ in user_state[user_id].get("done", [])]
    tasks = TASKS[workers][block]
    buttons = []
    for t in tasks:
        label = f"✅ {t}" if t in done else t
        buttons.append([KeyboardButton(label)])
    buttons.append([KeyboardButton("🏁 Завершити день")])
    return await update.message.reply_text("Оберіть завдання:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True))

async def end_day(update):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"id_{user_id}"
    done_tasks = user_state[user_id].get("done", [])
    summary = f"Звіт для @{username}:\n"
    for task, t in done_tasks:
        summary += f"• {task} — {t.strftime('%H:%M')}\n"
    await update.message.reply_text(summary)
    user_state[user_id] = {"step": "start", "done": []}
    return await update.message.reply_text("✅ День завершено! Дані очищено.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()