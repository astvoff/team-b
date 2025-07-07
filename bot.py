import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import time

TOKEN = os.environ.get('TOKEN')
CHAT_ID = int(os.environ.get('CHAT_ID'))

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привіт, я корпоративний бот магазину. Використовуйте /help для команд.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Доступні команди:\n/start - запуск\n/help - список команд')

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    message = context.job.data['text']
    await context.bot.send_message(chat_id=context.job.data['chat_id'], text=message)

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

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

    for reminder in reminders:
        app.job_queue.run_daily(
            send_reminder,
            reminder['time'],
            data={"chat_id": CHAT_ID, "text": reminder['text']},
            timezone="Europe/Kyiv"
        )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())