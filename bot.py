import logging
import datetime
import re
import gspread
import os
import json
import asyncio
import signal
import sys
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

# === Налаштування ===
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
SPREADSHEET_NAME = 'AccountsList'
SHEET_NAME = 'Аркуш1'

# Робочі години
WORK_START_HOUR = 8   # 8:00
WORK_END_HOUR = 24    # 24:00 (0:00 наступного дня)

logging.basicConfig(level=logging.INFO)

def is_work_time():
    """Перевіряє чи зараз робочий час"""
    current_hour = datetime.datetime.now().hour
    return WORK_START_HOUR <= current_hour < WORK_END_HOUR

def get_next_work_start():
    """Повертає час наступного початку робочого дня"""
    now = datetime.datetime.now()
    next_start = now.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    
    # Якщо вже пізніше робочого часу, то наступний день
    if now.hour >= WORK_END_HOUR or now.hour < WORK_START_HOUR:
        if now.hour >= WORK_END_HOUR:
            next_start += datetime.timedelta(days=1)
    
    return next_start

def get_credentials():
    """Створюємо credentials напряму з JSON string"""
    try:
        logging.info(f"JSON type: {type(GOOGLE_CREDENTIALS_JSON)}")
        logging.info(f"JSON length: {len(GOOGLE_CREDENTIALS_JSON)}")
        logging.info(f"First 100 chars: {GOOGLE_CREDENTIALS_JSON[:100]}")
        
        # Спробуємо різні способи парсингу
        creds_dict = None
        
        # Спосіб 1: якщо це вже словник
        if isinstance(GOOGLE_CREDENTIALS_JSON, dict):
            creds_dict = GOOGLE_CREDENTIALS_JSON
            logging.info("✅ JSON вже є словником")
        else:
            # Спосіб 2: парсимо як JSON string
            try:
                creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
                logging.info("✅ JSON розпарсено успішно")
            except json.JSONDecodeError as e:
                logging.warning(f"❌ Помилка парсингу JSON: {e}")
                
                # Спосіб 3: очищуємо та парсимо
                try:
                    cleaned_json = GOOGLE_CREDENTIALS_JSON.strip().replace('\n', '').replace('\r', '')
                    creds_dict = json.loads(cleaned_json)
                    logging.info("✅ JSON розпарсено після очищення")
                except json.JSONDecodeError as e2:
                    logging.warning(f"❌ Помилка після очищення: {e2}")
                    
                    # Спосіб 4: decode escape sequences
                    try:
                        decoded_json = GOOGLE_CREDENTIALS_JSON.encode().decode('unicode_escape')
                        creds_dict = json.loads(decoded_json)
                        logging.info("✅ JSON розпарсено після декодування")
                    except Exception as e3:
                        logging.error(f"❌ Всі способи не вдалися: {e3}")
                        raise
        
        if not creds_dict or not isinstance(creds_dict, dict):
            raise ValueError("Не вдалося отримати валідний словник з JSON")
            
        # Перевіряємо обов'язкові поля
        required_fields = ['type', 'project_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in creds_dict]
        
        if missing_fields:
            raise ValueError(f"Відсутні обов'язкові поля: {missing_fields}")
            
        logging.info(f"✅ Знайдені поля: {list(creds_dict.keys())}")
        logging.info(f"✅ Client email: {creds_dict.get('client_email', 'N/A')}")
        
        # Створюємо credentials
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
        logging.info("✅ Credentials створено успішно")
        return credentials
        
    except Exception as e:
        logging.error(f"❌ Помилка створення credentials: {e}")
        logging.error(f"GOOGLE_CREDENTIALS_JSON type: {type(GOOGLE_CREDENTIALS_JSON)}")
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка повідомлень"""
    try:
        text = update.message.text.strip()
        
        # Тестова команда
        if text.lower() == '/test':
            try:
                sheet = connect_sheet()
                await update.message.reply_text("✅ Підключення до Google Sheets працює!")
            except:
                await update.message.reply_text("❌ Помилка підключення до Google Sheets")
            return
            
        # Команда для перевірки часу
        if text.lower() == '/time':
            now = datetime.datetime.now()
            await update.message.reply_text(f"🕐 Зараз: {now.hour:02d}:{now.minute:02d}\n📅 Робочий час: {WORK_START_HOUR:02d}:00 - {WORK_END_HOUR:02d}:00")
            return
            
        # Довідка
        if text.lower() == '/help' or text.lower() == '/start':
            help_text = (
                "🤖 Бот для роботи з Google Таблицями\n\n"
                "Команди:\n"
                "/help - ця довідка\n"
                "/test - перевірка підключення\n"
                "/time - поточний час\n"
                "/status - статус бота\n\n"
                "Як користуватися:\n"
                "Надішліть рядки з ID та соціальними мережами:\n\n"
                "123456 Instagram\n"
                "789012 TikTok\n\n"
                "⏰ Робочий час: 08:00 - 24:00"
            )
            await update.message.reply_text(help_text)
            return
            
        # Статус бота
        if text.lower() == '/status':
            now = datetime.datetime.now()
            is_working = is_work_time()
            status_text = (
                f"📊 Статус бота\n\n"
                f"🕐 Поточний час: {now.hour:02d}:{now.minute:02d}\n"
                f"📅 Дата: {now.strftime('%Y-%m-%d')}\n"
                f"⚡ Статус: {'🟢 Працює' if is_working else '🔴 Не працює'}\n"
                f"⏰ Робочий час: {WORK_START_HOUR:02d}:00 - {WORK_END_HOUR:02d}:00"
            )
            if not is_working:
                next_start = get_next_work_start()
                status_text += f"\n🌅 Наступний запуск: {next_start.strftime('%H:%M')}"
            await update.message.reply_text(status_text)
            return
            
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            await update.message.reply_text(
                "Надішли рядки з ID і соц.\n\n"
                "Приклад:\n"
                "123456 Instagram\n"
                "789012 TikTok\n\n"
                "Команди:\n"
                "/help - довідка\n"
                "/test - тест підключення\n" 
                "/time - поточний час\n"
                "/status - статус бота"
            )
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

class GracefulShutdown:
    """Клас для graceful shutdown"""
    def __init__(self):
        self.shutdown = False
        signal.signal(signal.SIGTERM, self._exit_gracefully)
        signal.signal(signal.SIGINT, self._exit_gracefully)

    def _exit_gracefully(self, signum, frame):
        logging.info(f"🛑 Отримано сигнал {signum}, зупиняємо бота...")
        self.shutdown = True

async def run_scheduled_bot():
    """Запускає бота тільки в робочий час"""
    shutdown_handler = GracefulShutdown()
    
    while not shutdown_handler.shutdown:
        if is_work_time():
            logging.info(f"🟢 Запускаємо бота - робочий час ({datetime.datetime.now().hour:02d}:00)")
            
            # Створюємо додаток
            app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            try:
                # Запускаємо бота
                await app.initialize()
                await app.start()
                await app.updater.start_polling()
                
                # Працюємо поки робочий час
                while is_work_time() and not shutdown_handler.shutdown:
                    await asyncio.sleep(60)  # Перевіряємо кожну хвилину
                
                # Зупиняємо бота
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
                
                if not shutdown_handler.shutdown:
                    logging.info("🔴 Зупинили бота - кінець робочого дня")
                
            except Exception as e:
                logging.error(f"❌ Помилка при роботі бота: {e}")
                await asyncio.sleep(300)  # Чекаємо 5 хвилин перед перезапуском
                
        else:
            # Не робочий час - чекаємо
            next_start = get_next_work_start()
            now = datetime.datetime.now()
            sleep_seconds = (next_start - now).total_seconds()
            
            logging.info(f"😴 Бот спить до {next_start.strftime('%H:%M')} ({sleep_seconds/3600:.1f} год)")
            
            # Спимо, але перевіряємо сигнали кожні 5 хвилин
            while sleep_seconds > 0 and not shutdown_handler.shutdown:
                sleep_time = min(300, sleep_seconds)  # Максимум 5 хвилин
                await asyncio.sleep(sleep_time)
                sleep_seconds -= sleep_time
                
                # Перевіряємо чи не настав робочий час
                if is_work_time():
                    break

if __name__ == '__main__':
    try:
        logging.info("🚀 Запускаємо scheduled бота...")
        asyncio.run(run_scheduled_bot())
    except KeyboardInterrupt:
        logging.info("🛑 Бота зупинено вручну")
    except Exception as e:
        logging.error(f"❌ Критична помилка: {e}")
        sys.exit(1)
