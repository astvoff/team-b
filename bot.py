import os
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
import logging
from datetime import time

TOKEN = os.environ.get('TOKEN')
CHAT_ID = int(os.environ.get('CHAT_ID'))

logging.basicConfig(level=logging.INFO)

def start(update, context: CallbackContext):
    update.message.reply_text('Привіт, я корпоративний бот магазину. Використовуйте /help для команд.')

def help_command(update, context: CallbackContext):
    update.message.reply_text('Доступні команди:\n/start - запуск\n/help - список команд')

def send_reminder(context: CallbackContext):
    message = context.job.context['text']
    chat_id = context.job.context['chat_id']
    context.bot.send_message(chat_id=chat_id, text=message)

def main():
    bot = Bot(TOKEN)
    updater = Updater(bot=bot, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))

    job_queue = updater.job_queue

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
        job_queue.run_daily(
            send_reminder,
            reminder['time'],
            context={"chat_id": CHAT_ID, "text": reminder['text']}
        )

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
