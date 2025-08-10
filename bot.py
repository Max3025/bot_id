import logging
import datetime
import re
import gspread
import os
import json

from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# Завантажуємо токен та JSON з оточення
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
json_content = os.getenv('GOOGLE_CREDENTIALS_JSON')



CREDS_FILE = "credentials.json"

# Підключення до Google Sheets
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SPREADSHEET_NAME = 'AccountsList'
SHEET_NAME = 'Аркуш1'

# Логування
logging.basicConfig(level=logging.INFO)

# Підключення до таблиці
def connect_sheet():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
    return sheet

# Обробка повідомлень
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        if not lines:
            await update.message.reply_text("Надішли рядки з ID і соц.")
            return

        sheet = connect_sheet()
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        count = 0

        for line in lines:
            match = re.search(r'\d{6,}', line)
            if not match:
                continue

            id_ = match.group()
            social = line.replace(id_, '').strip()

            sheet.append_row([id_, date_str, social])
            count += 1

        if count > 0:
            await update.message.reply_text(f"✅ Додано {count} рядків до таблиці.")
        else:
            await update.message.reply_text("❗ Не знайдено жодного ID.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {str(e)}")
        print("Помилка при обробці:", e)

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()