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
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

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
        logging.info("=== ДІАГНОСТИКА JSON ===")
        logging.info(f"JSON type: {type(GOOGLE_CREDENTIALS_JSON)}")
        logging.info(f"JSON length: {len(GOOGLE_CREDENTIALS_JSON)}")
        logging.info(f"First 200 chars: {repr(GOOGLE_CREDENTIALS_JSON[:200])}")
        logging.info(f"Last 100 chars: {repr(GOOGLE_CREDENTIALS_JSON[-100:])}")
        
        # Перевіряємо що це не порожня строка
        if not GOOGLE_CREDENTIALS_JSON or len(GOOGLE_CREDENTIALS_JSON.strip()) == 0:
            raise ValueError("JSON змінна порожня!")
            
        creds_dict = None
        json_str = GOOGLE_CREDENTIALS_JSON.strip()
        
        # Якщо це вже словник
        if isinstance(json_str, dict):
            creds_dict = json_str
            logging.info("✅ JSON вже є словником")
        else:
            # Метод 1: прямий парсинг
            try:
                creds_dict = json.loads(json_str)
                logging.info("✅ Метод 1: прямий парсинг успішний")
            except json.JSONDecodeError as e:
                logging.warning(f"❌ Метод 1 не вдався: {e}")
                
                # Метод 2: видаляємо зайві символи
                try:
                    cleaned = json_str.replace('\r', '').replace('\n', '').replace('\t', '')
                    # Видаляємо подвійні пробіли
                    while '  ' in cleaned:
                        cleaned = cleaned.replace('  ', ' ')
                    creds_dict = json.loads(cleaned)
                    logging.info("✅ Метод 2: очищення успішне")
                except json.JSONDecodeError as e2:
                    logging.warning(f"❌ Метод 2 не вдався: {e2}")
                    
                    # Метод 3: decode escape sequences
                    try:
                        decoded = json_str.encode('utf-8').decode('unicode_escape')
                        creds_dict = json.loads(decoded)
                        logging.info("✅ Метод 3: декодування успішне")
                    except Exception as e3:
                        logging.warning(f"❌ Метод 3 не вдався: {e3}")
                        
                        # Метод 4: перевіряємо чи це escaped JSON
                        try:
                            # Якщо JSON був escaped як string
                            if json_str.startswith('"') and json_str.endswith('"'):
                                unescaped = json.loads(json_str)  # Розпаковуємо escaped string
                                creds_dict = json.loads(unescaped)  # Потім парсимо JSON
                                logging.info("✅ Метод 4: розпакування escaped JSON успішне")
                            else:
                                raise ValueError("JSON має неправильний формат")
                        except Exception as e4:
                            logging.error(f"❌ Всі методи не вдалися. Останній: {e4}")
                            
                            # Показуємо частину JSON для діагностики
                            sample = json_str[:500] if len(json_str) > 500 else json_str
                            logging.error(f"JSON sample: {repr(sample)}")
                            raise ValueError(f"Не вдалося розпарсити JSON. Перевірте формат у Railway Variables. Помилка: {e}")
        
        # Перевіряємо що отримали словник
        if not isinstance(creds_dict, dict):
            logging.error(f"❌ Результат не словник: {type(creds_dict)}")
            raise ValueError(f"JSON розпарсився не як словник, а як {type(creds_dict)}")
            
        logging.info(f"✅ Отримано словник з {len(creds_dict)} полями")
        logging.info(f"Ключі: {list(creds_dict.keys())}")
        
        # Перевіряємо обов'язкові поля
        required_fields = ['type', 'project_id', 'private_key', 'client_email', 'client_id']
        missing_fields = [field for field in required_fields if field not in creds_dict]
        
        if missing_fields:
            logging.error(f"❌ Відсутні поля: {missing_fields}")
            logging.error(f"Наявні поля: {list(creds_dict.keys())}")
            raise ValueError(f"Відсутні обов'язкові поля: {missing_fields}")
            
        # Перевіряємо що ключі не порожні
        empty_fields = [field for field in required_fields if not creds_dict.get(field)]
        if empty_fields:
            logging.error(f"❌ Порожні поля: {empty_fields}")
            raise ValueError(f"Поля не можуть бути порожніми: {empty_fields}")
            
        logging.info(f"✅ Client email: {creds_dict.get('client_email', 'N/A')}")
        logging.info(f"✅ Project ID: {creds_dict.get('project_id', 'N/A')}")
        
        # Створюємо credentials
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
        logging.info("✅ Credentials створено успішно")
        return credentials
        
    except Exception as e:
        logging.error(f"❌ Критична помилка створення credentials: {e}")
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

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help або /start"""
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

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test"""
    try:
        sheet = connect_sheet()
        await update.message.reply_text("✅ Підключення до Google Sheets працює!")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка підключення: {str(e)}")

async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /time"""
    now = datetime.datetime.now()
    await update.message.reply_text(f"🕐 Зараз: {now.hour:02d}:{now.minute:02d}\n📅 Робочий час: {WORK_START_HOUR:02d}:00 - {WORK_END_HOUR:02d}:00")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка звичайних повідомлень (не команд)"""
    try:
        text = update.message.text.strip()
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
            
            # Додаємо обробники команд
            app.add_handler(CommandHandler("start", cmd_help))
            app.add_handler(CommandHandler("help", cmd_help))
            app.add_handler(CommandHandler("test", cmd_test))
            app.add_handler(CommandHandler("time", cmd_time))
            app.add_handler(CommandHandler("status", cmd_status))
            
            # Додаємо обробник звичайних повідомлень
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
