import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ.get("TOKEN")  # або впиши прямо: TOKEN = "123456:ABC..."

user_state = {}

# Блоки завдань
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


# Інструкція 
INSTRUCTION = """Інструкція лише до Чергування: ..."""

TASK_DESCRIPTIONS = {
    "Замовлення сайту": [
        "1) Перевірити актуальність, уточнити у менеджера сайта",
        "2) Всі замовлення мають стікер з № замовлення",
        "3) Зарядити вживані телефони",
        "4) Вживані телефони в фірмових коробках",
        "5) Все відкладено на поличці замовлень",
        "6) Перевірити закази на складі"
    ],
    "Замовлення наші": [
        "1) Звірити товар факт/база",
        "2) Проінформувати клієнта про наявність (за потреби)",
        "3) Поновити резерви (за потреби)",
        "4) Техніка підписана відповідальним",
        "5) Зарядити б/у телефони",
        "6) Неактуальні закази закрити"
    ],
    "OLX": [
        "1) Відповідати на повідомлення",
        "2) Перевірити кількість оголошень (більше 45)",
        "3) Запустити рекламу (7-9 оголошень)",
        "4) Звірити актуальність цін"
    ],
    "Стани в базі": [
        "1) На всю б/у техніку та телефони мають стояти актуальні стани",
        "2) Контролювати проставлення станів після прийняття в Trade-in"
    ],
    "Цінники": [
        "1) Перевірити всю б/у техніку на якість наклеєних цінників",
        "2) Перевірити якість поклейки цінників на всій техніці (в тому числі і шоурум)",
        "3) Перевірити наявні переоцінки, та проконтролювати переклейку"
    ],
    "Звіт витрати": [
        "1) Всі витрати мають бути проведені по базі",
        "2) Перевірити правильність проведення (правильні статті)",
        "3) Зробити та скинути файл exel в групу 'Звіти' з усіма чеками"
    ],
    "Звірка переміщень": [
        "1) Перевірити переміщення яким більше двох днів (ГО, Склади, містами)",
        "2) Переглянути переміщення по Одесі між магазинами за минулі дні",
        "3) Знайти всі переміщення фізично або розібратись чому воно не доїхало на магазин"
    ]
}


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id] = {"step": "workers", "done": []}
    buttons = [[KeyboardButton(str(n))] for n in range(6, 8)]
    await update.message.reply_text(
        "Скільки працівників на зміні?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# Основний обробник
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = user_state.get(user_id, {})
    step = state.get("step", "workers")

    if text == "⬅️ Назад":
        if step == "block":
            return await start(update, context)
        elif step == "task":
            user_state[user_id]["step"] = "block"
            return await show_blocks(update, context)
        elif step == "confirm":
            user_state[user_id]["step"] = "task"
            return await show_tasks(update, context)

    if step == "workers":
        if text.isdigit() and int(text) in TASKS:
            user_state[user_id]["workers"] = int(text)
            user_state[user_id]["step"] = "block"
            return await show_blocks(update, context)
        else:
            return await update.message.reply_text("Будь ласка, обери число від 6 до 7")

    elif step == "block":
        if text in TASKS[user_state[user_id]["workers"]]:
            user_state[user_id]["block"] = text
            user_state[user_id]["step"] = "task"
            return await show_tasks(update, context)

    elif step == "task":
        user_state[user_id]["current_task"] = text
        user_state[user_id]["step"] = "confirm"
        await update.message.reply_text(f"🛠 Обране завдання: {text}")
        if "Черг" in text:
            await update.message.reply_text(INSTRUCTION)
        buttons = [[KeyboardButton("✅ Виконано")], [KeyboardButton("⬅️ Назад")]]
        return await update.message.reply_text(
            "Після виконання натисни «✅ Виконано»",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )

    elif step == "confirm":
        if text == "✅ Виконано":
            done = user_state[user_id].get("done", [])
            done.append(user_state[user_id]["current_task"])
            user_state[user_id]["done"] = done
            user_state[user_id]["step"] = "task"
            await update.message.reply_text("✅ Завдання виконано!")
            return await show_tasks(update, context)

# Показ блоку
async def show_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    workers = user_state[user_id]["workers"]
    blocks = TASKS[workers].keys()
    buttons = [[KeyboardButton(b)] for b in blocks]
    buttons.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text(
        "Оберіть свій блок завдань:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# Показ завдань
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    workers = user_state[user_id]["workers"]
    block = user_state[user_id]["block"]
    done = user_state[user_id].get("done", [])
    all_tasks = TASKS[workers][block]
    buttons = []
    for task in all_tasks:
        if task in done:
            buttons.append([KeyboardButton(f"✅ {task}")])
        else:
            buttons.append([KeyboardButton(task)])
    buttons.append([KeyboardButton("⬅️ Назад")])
    await update.message.reply_text(
        "Оберіть, з якого завдання почати:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

# Запуск
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()