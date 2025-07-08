import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, JobQueue
from datetime import time
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('TOKEN')
CHAT_ID = int(os.environ.get('CHAT_ID'))  # з Environment Variables

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот працює. Я готовий надсилати нагадування!")

# Функція для надсилання нагадувань
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    message = context.job.data['text']
    await context.bot.send_message(chat_id=CHAT_ID, text=message)

def main():
    # встановлюємо часову зону
    kyiv_timezone = ZoneInfo("Europe/Kyiv")

    # створюємо застосунок з часовою зоною
    app = ApplicationBuilder().token(TOKEN).timezone(kyiv_timezone).build()

    # додаємо обробник /start
    app.add_handler(CommandHandler("start", start))

    # перелік нагадувань
    reminders = [
        {"time": time(10, 0), "text": "Не забудь відкрити касу ТОВ 👻"},
        {"time": time(10, 15), "text": "Перевір пропущені Binotel за сьогодні та за вчора 📞"},
        {"time": time(12, 0), "text": "Що там OLX 👀 Перевір повідомлення 📩"},
        {"time": time(12, 10), "text": "Час рахувати касу 👻"},
        {"time": time(14, 30), "text": "Що там OLX 👀 Перевір повідомлення 📩"},
        {"time": time(15, 0), "text": "Час рахувати касу 👻"},
        {"time": time(17, 30), "text": "Перевір чи включена реклама на телефонах, та протри їх, якщо вони брудні 👾"},
        {"time": time(18, 30), "text": "Час рахувати касу 👻"},
        {"time": time(19, 30), "text": "Що там OLX 👀 Перевір повідомлення 📩"},
    ]

    # додаємо нагадування в JobQueue
    for reminder in reminders:
        app.job_queue.run_daily(
            send_reminder,
            reminder['time'],
            data={"text": reminder['text']}
        )

    logging.info("Бот із нагадуваннями запущено.")
    app.run_polling()

if __name__ == '__main__':
    main()