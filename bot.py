# telegram_bot_v2.py

import os
import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ.get("TOKEN")

# Державні змінні
user_state = {}
used_blocks = {}  # dict на день, що зберігає зайняті блоки
admin_id = 123456789  # заміни на свій Telegram ID

# Завдання по блоках для 6–9 працівників
TASKS = {
    6: {"1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"], ...},  # скорочено
    7: {"1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"], ...},
    8: {...},  # додай завдання самостійно
    9: {...}
}

INSTRUCTION = """Інструкція лише до Чергування: ..."""

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"step": "begin"}
    kb = [[KeyboardButton("▶️ Розпочати день")]]
    await update.message.reply_text("Привіт!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# Хендлер
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = user_state.get(user_id, {})
    step = state.get("step", "begin")

    # Кнопка назад
    if text == "⬅️ Назад":
        if step == "confirm_block":
            user_state[user_id]["step"] = "block"
            return await show_blocks(update, context)
        if step == "block":
            user_state[user_id]["step"] = "workers"
            return await ask_workers(update, context)
        if step == "task":
            user_state[user_id]["step"] = "confirm_block"
            return await confirm_block(update, context)

    if text == "▶️ Розпочати день":
        user_state[user_id] = {"step": "workers", "done": []}
        return await ask_workers(update, context)

    if step == "workers":
        if text.isdigit() and int(text) in TASKS:
            user_state[user_id]["workers"] = int(text)
            user_state[user_id]["step"] = "block"
            return await show_blocks(update, context)

    if step == "block":
        block = text.strip()
        workers = user_state[user_id]["workers"]
        today = datetime.date.today().isoformat()
        used_today = used_blocks.get(today, set())
        if block in used_today:
            return await update.message.reply_text("❗Цей блок вже зайнятий іншим працівником.")
        user_state[user_id]["block"] = block
        user_state[user_id]["step"] = "confirm_block"
        return await confirm_block(update, context)

    if step == "confirm_block":
        if text == f"✅ Так, блок {user_state[user_id]['block']}":
            block = user_state[user_id]['block']
            today = datetime.date.today().isoformat()
            used_blocks.setdefault(today, set()).add(block)
            user_state[user_id]["step"] = "task"
            return await show_tasks(update, context)
        else:
            return await show_blocks(update, context)

    if step == "task":
        current_task = text.replace("✅ ", "")
        if current_task.startswith("✅"):
            return
        user_state[user_id]["current_task"] = current_task
        user_state[user_id]["step"] = "confirm_task"
        await update.message.reply_text(f"🛠 Завдання: {current_task}")
        if "Черг" in current_task:
            await update.message.reply_text(INSTRUCTION)
        kb = [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]]
        return await update.message.reply_text("Після виконання — натисни «✅ Виконано»",
                                              reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

    if step == "confirm_task":
        if text == "✅ Виконано":
            task = user_state[user_id].get("current_task")
            done = user_state[user_id].get("done", [])
            if task not in done:
                done.append(task)
                user_state[user_id]["done"] = done
            user_state[user_id]["step"] = "task"
            await update.message.reply_text("✅ Завдання виконано!")
            return await show_tasks(update, context)

    if text == "⏹ Завершити день":
        return await finish_day(update, context)

# Завершити день
async def finish_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_state.get(user_id, {})
    username = update.effective_user.username
    block = data.get("block")
    done = data.get("done", [])
    now = datetime.datetime.now().strftime("%H:%M:%S")
    # TODO: зберегти в Google Sheets тут
    user_state[user_id] = {}
    return await update.message.reply_text(f"Дякую {username}, твій день завершено. Всього доброго!")

async def ask_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(str(n))] for n in range(6, 10)]
    await update.message.reply_text("Скільки працівників на зміні?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def show_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    workers = user_state[update.effective_user.id]["workers"]
    kb = [[KeyboardButton(str(n))] for n in TASKS[workers].keys()]
    kb.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text("Оберіть блок:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def confirm_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    block = user_state[update.effective_user.id]["block"]
    kb = [[KeyboardButton(f"✅ Так, блок {block}"), KeyboardButton("⬅️ Назад")]]
    await update.message.reply_text(f"Ви точно обрали блок {block}?",
                                    reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = user_state[update.effective_user.id]
    workers = state["workers"]
    block = state["block"]
    done = state.get("done", [])
    all_tasks = TASKS[workers][block]
    kb = [[KeyboardButton(("✅ " if t in done else "") + t)] for t in all_tasks]
    kb.append([KeyboardButton("⏹ Завершити день")])
    kb.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text("Оберіть завдання:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# Запуск
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()
