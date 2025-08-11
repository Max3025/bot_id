import logging
import datetime
import re
import gspread
import os
import json
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# === Завантажуємо токен та JSON з оточення ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN не встановлено в оточенні!")
if not GOOGLE_CREDENTIALS_JSON:
    raise RuntimeError("❌ GOOGLE_CREDENTIALS_JSON не встановлено в оточенні!")

# === Налаштування Google Sheets ===
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
SPREADSHEET_NAME = 'AccountsList'
SHEET_NAME = 'Аркуш1'

logging.basicConfig(level=logging.INFO)

def get_credentials():
    """Створюємо credentials напряму з JSON string"""
    try:
        # Логуємо перші та останні символи для діагностики
        logging.info(f"JSON довжина: {len(GOOGLE_CREDENTIALS_JSON)}")
        logging.info(f"Перші 50 символів: {GOOGLE_CREDENTIALS_JSON[:50]}")
        logging.info(f"Останні 50 символів: {GOOGLE_CREDENTIALS_JSON[-50:]}")
        
        # Спробуємо різні способи парсингу
        creds_dict = None
        
        # Спосіб 1: прямий JSON parse
        try:
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            logging.info("✅ JSON парсинг успішний (спосіб 1)")
        except json.JSONDecodeError as e:
            logging.warning(f"❌ Спосіб 1 не вдався: {e}")
            
            # Спосіб 2: з декодуванням escape-послідовностей
            try:
                decoded_json = GOOGLE_CREDENTIALS_JSON.encode().decode('unicode_escape')
                creds_dict = json.loads(decoded_json)
                logging.info("✅ JSON парсинг успішний (спосіб 2)")
            except json.JSONDecodeError as e2:
                logging.warning(f"❌ Спосіб 2 не вдався: {e2}")
                
                # Спосіб 3: очищення від зайвих символів
                try:
                    cleaned_json = GOOGLE_CREDENTIALS_JSON.strip().replace('\n', '').replace('\r', '')
                    creds_dict = json.loads(cleaned_json)
                    logging.info("✅ JSON парсинг успішний (спосіб 3)")
                except json.JSONDecodeError as e3:
                    logging.error(f"❌ Всі способи парсингу не вдалися: {e3}")
                    raise
        
        if not creds_dict:
            raise ValueError("Не вдалося розпарсити JSON")
            
        # Перевіряємо обов'язкові поля
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email', 'client_id']
        missing_fields = [field for field in required_fields if field not in creds_dict]
        
        if missing_fields:
            raise ValueError(f"Відсутні обов'язкові поля в JSON: {missing_fields}")
            
        logging.info(f"✅ Знайдені поля: {list(creds_dict.keys())}")
        logging.info(f"✅ Client email: {creds_dict.get('client_email', 'N/A')}")
        
        # Створюємо credentials напряму з словника
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
        logging.info("✅ Credentials створено успішно")
        return credentials
        
    except Exception as e:
        logging.error(f"❌ Помилка створення credentials: {e}")
        raise

def connect_sheet():
    """Підключаємося до Google Sheets"""
    try:
        credentials = get_credentials()
        client = gspread.authorize(credentials)
        sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
        logging.info("✅ Підключення до Google Sheets успішне")
        return sheet
    except Exception as e:
        logging.error(f"❌ Помилка підключення до Google Sheets: {e}")
        raise

# === Тестова функція для перевірки підключення ===
def test_connection():
    """Тестуємо підключення до Google Sheets"""
    try:
        sheet = connect_sheet()
        # Спробуємо прочитати перший рядок
        first_row = sheet.row_values(1) if sheet.row_count > 0 else []
        logging.info(f"✅ Тест підключення успішний. Перший рядок: {first_row}")
        return True
    except Exception as e:
        logging.error(f"❌ Тест підключення не вдався: {e}")
        return False

# === Обробка повідомлень ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        
        # Спеціальна команда для тестування
        if text.lower() == '/test':
            if test_connection():
                await update.message.reply_text("✅ Підключення до Google Sheets працює!")
            else:
                await update.message.reply_text("❌ Помилка підключення до Google Sheets")
            return
            
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            await update.message.reply_text("Надішли рядки з ID і соц.\nАбо відправ /test для перевірки підключення.")
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
    try:
        # Тестуємо підключення при запуску
        logging.info("🔧 Тестуємо підключення до Google Sheets...")
        test_connection()
        
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logging.info("🚀 Запускаємо бота...")
        app.run_polling()
    except Exception as e:
        logging.error(f"❌ Помилка запуску: {e}")
        raise
