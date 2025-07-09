import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ.get("TOKEN")

BLOCK_TASKS = {
    6: {
        "1": ["Черговий (-a)", "Вітрини/Шоуруми", "Запити Сайту"],
        "2": ["Замовлення сайту", "Перевірка переміщень", "Запити Сайту"],
        "3": ["Замовлення наші", "Стіна аксесуарів", "Прийомка товару"],
        "4": ["OLX", "Стани техніка і тел.", "Прийомка товару"],
        "5": ["Цінники", "Зарядка телефонів", "Звіт-витрати", "Прийомка товару"],
        "6": ["Каса", 'Запити "Нова Техніка"', 'Запити "Акси"']
    },
    # Додай аналогічно 7, 8, 9 блоки!
}

SUBTASKS = {
    "Замовлення сайту": [
        "Перевірити актуальність, уточнити у менеджера сайта",
        "Всі замовлення мають стікер з № замовлення",
        "Зарядити вживані телефони",
        "Вживані телефони в фірмових коробках",
        "Все відкладено на поличці замовлень",
        "Перевірити закази на складі"
    ],
    "Замовлення наші": [
        "Звірити товар факт/база",
        "Проінформувати клієнта про наявність (за потреби)",
        "Поновити резерви (за потреби)",
        "Техніка підписана відповідальним",
        "Зарядити б/у телефони",
        "Неактуальні закази закрити"
    ],
    # ... додай свої підзавдання для кожного завдання, де це потрібно
}

user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"state": "idle"}
    kb = [[KeyboardButton("▶️ Початок робочого дня")]]
    await update.message.reply_text(
        "Натисніть «Початок робочого дня», щоб розпочати.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def main_menu(update, context):
    user_id = update.effective_user.id
    kb = [[KeyboardButton(str(i))] for i in [6, 7, 8, 9]]
    await update.message.reply_text(
        "Оберіть кількість працівників на зміні:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    user_state[user_id]["state"] = "select_workers"

async def select_block(update, context):
    user_id = update.effective_user.id
    workers = int(update.message.text)
    user_state[user_id]["workers"] = workers
    user_state[user_id]["state"] = "select_block"
    kb = [[KeyboardButton(str(i))] for i in BLOCK_TASKS[workers].keys()]
    kb.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text(
        "Оберіть свій блок:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def confirm_block(update, context):
    user_id = update.effective_user.id
    block = update.message.text
    user_state[user_id]["block"] = block
    user_state[user_id]["state"] = "confirm_block"
    kb = [
        [KeyboardButton(f"✅ Так, блок {block}")],
        [KeyboardButton("⬅️ Назад")]
    ]
    await update.message.reply_text(
        f"Ви впевнені, що обрали блок {block}? Після підтвердження змінити не можна.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def block_tasks(update, context):
    user_id = update.effective_user.id
    workers = user_state[user_id]["workers"]
    block = user_state[user_id]["block"]
    tasks = BLOCK_TASKS[workers][block]
    # Якщо state вже tasks -- не перезаписувати completed_tasks, щоб після повернення зберігались виконані
    if user_state[user_id].get("state") != "tasks":
        user_state[user_id]["tasks"] = {t: False for t in tasks}
        user_state[user_id]["completed_tasks"] = set()
    user_state[user_id]["state"] = "tasks"
    left_tasks = [t for t in tasks if not user_state[user_id]["tasks"][t]]
    if left_tasks:
        kb = [[KeyboardButton(t)] for t in left_tasks]
        kb.append([KeyboardButton("⬅️ Назад")])
        await update.message.reply_text(
            "Оберіть завдання:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
    else:
        await update.message.reply_text(
            "Всі завдання виконані! Дякуємо 🎉",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("⬅️ Назад")]],
                resize_keyboard=True
            )
        )

async def handle_task(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    # Якщо є підзавдання
    if text in SUBTASKS:
        user_state[user_id]["state"] = "subtasks"
        user_state[user_id]["current_task"] = text
        user_state[user_id]["current_subtasks"] = {s: False for s in SUBTASKS[text]}
        left_sub = [s for s in SUBTASKS[text] if not user_state[user_id]["current_subtasks"][s]]
        kb = [[KeyboardButton(s)] for s in left_sub]
        kb.append([KeyboardButton("⬅️ Назад")])
        await update.message.reply_text(
            f"Підзавдання для «{text}»:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
    else:
        # Якщо підзавдань немає
        user_state[user_id]["tasks"][text] = True
        user_state[user_id]["completed_tasks"].add(text)
        user_state[user_id]["state"] = "task_done"
        kb = [[KeyboardButton("Перейти до інших завдань")]]
        await update.message.reply_text(
            f"Завдання «{text}» виконано!",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )

async def handle_subtask(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    state = user_state[user_id]
    if text == "⬅️ Назад":
        user_state[user_id]["state"] = "tasks"
        return await block_tasks(update, context)
    if text == "Перейти до інших завдань":
        user_state[user_id]["state"] = "tasks"
        return await block_tasks(update, context)
    if text in state["current_subtasks"]:
        state["current_subtasks"][text] = True
        left = [s for s, done in state["current_subtasks"].items() if not done]
        if left:
            kb = [[KeyboardButton(s)] for s in left]
            kb.append([KeyboardButton("⬅️ Назад")])
            await update.message.reply_text(
                f"Залишилось підзавдань: {len(left)}",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )
        else:
            # всі підзавдання виконані
            main_task = state["current_task"]
            state["tasks"][main_task] = True
            state["completed_tasks"].add(main_task)
            del state["current_subtasks"]
            del state["current_task"]
            user_state[user_id]["state"] = "subtasks_done"
            kb = [[KeyboardButton("Перейти до інших завдань")]]
            await update.message.reply_text(
                f"Всі підзавдання виконані! Завдання «{main_task}» закрито.",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
            )

async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = user_state.get(user_id, {"state": "idle"})["state"]

    if text == "/start":
        return await start(update, context)
    if text == "▶️ Початок робочого дня":
        return await main_menu(update, context)
    if state == "select_workers":
        if text.isdigit() and int(text) in BLOCK_TASKS:
            return await select_block(update, context)
    if state == "select_block":
        if text == "⬅️ Назад":
            return await main_menu(update, context)
        if text in BLOCK_TASKS[user_state[user_id]["workers"]]:
            return await confirm_block(update, context)
    if state == "confirm_block":
        if text == "⬅️ Назад":
            return await select_block(update, context)
        if text.startswith("✅ Так, блок"):
            return await block_tasks(update, context)
    if state == "tasks":
        if text == "⬅️ Назад":
            return await confirm_block(update, context)
        if text in user_state[user_id]["tasks"] and not user_state[user_id]["tasks"][text]:
            return await handle_task(update, context)
    if state == "subtasks":
        return await handle_subtask(update, context)
    if state == "subtasks_done":
        if text == "Перейти до інших завдань":
            user_state[user_id]["state"] = "tasks"
            return await block_tasks(update, context)
    if state == "task_done":
        if text == "Перейти до інших завдань":
            user_state[user_id]["state"] = "tasks"
            return await block_tasks(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), main_handler))
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()