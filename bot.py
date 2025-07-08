import os
import logging
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('TOKEN')
CHAT_ID = int(os.environ.get('CHAT_ID'))

# Часовий пояс Києва
kyiv_tz = pytz.timezone('Europe/Kyiv')

# Розклад нагадувань
reminders = {
    "10:00": "Не забудь відкрити касу ТОВ 👻",
    "10:15": "Перевір пропущені Binotel за сьогодні та за вчора 📞",
    "12:00": "Що там OLX 👀 Перевір повідомлення 📩",
    "12:10": "Час рахувати касу 👻",
    "14:30": "Що там OLX 👀 Перевір повідомлення 📩",
    "15:00": "Час рахувати касу 👻",
    "17:30": "Перевір чи включена реклама на телефонах, та протри їх, якщо вони брудні 👾",
    "18:30": "Час рахувати касу 👻",
    "19:30": "Що там OLX 👀 Перевір повідомлення 📩",
}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот працює по Києву 🕰️")

# Щохвилинна перевірка часу
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    now_kyiv = datetime.now(kyiv_tz).strftime("%H:%M")
    if now_kyiv in reminders:
        text = reminders[now_kyiv]
        await context.bot.send_message(chat_id=CHAT_ID, text=text)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # Запуск перевірки щохвилини
    app.job_queue.run_repeating(check_reminders, interval=60, first=0)

    logging.info("Бот із нагадуваннями по Києву запущено.")
    app.run_polling()

if __name__ == '__main__':
    main()