import logging
import datetime
import re
import gspread
import os

from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# === Завантажуємо токен та JSON з оточення ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не встановлено в оточенні!")

if not GOOGLE_CREDENTIALS_JSON:
    raise RuntimeError("❌ GOOGLE_CREDENTIALS_JSON не встановлено в оточенні!")

# === Створюємо credentials.json ===
try:
    # Декодуємо escape-послідовності, якщо є \\n
    creds_data = GOOGLE_CREDENTIALS_JSON.encode().decode('unicode_escape')
    with open("credentials.json", "w", encoding="utf-8") as f:
        f.write(creds_data)
except Exception as e:
    raise RuntimeError(f"❌ Помилка при створенні credentials.json: {e}")

# === Налаштування Google Sheets ===
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SPREADSHEET_NAME = 'AccountsList'
SHEET_NAME = 'Аркуш1'

logging.basicConfig(level=logging.INFO)

def connect_sheet():
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
    return sheet

# === Обробка повідомлень ===
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
        logging.error("Помилка при обробці:", exc_info=True)

# === Запуск бота ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

