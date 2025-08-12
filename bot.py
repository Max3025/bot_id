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

# Налаштування таймзони - різниця з UTC в годинах
# Для України (UTC+2 зимой, UTC+3 літом) - зараз літо, тому +3
TIMEZONE_OFFSET_HOURS = 3  # Змініть на вашу різницю з UTC

# Альтернативно можете використати pytz (якщо встановлена):
# import pytz
# TIMEZONE = pytz.timezone('Europe/Kiev')

# Робочі години (у вашій місцевій таймзоні)
WORK_START_HOUR = 8   # 8:00
WORK_END_HOUR = 24    # 24:00 (0:00 наступного дня)

logging.basicConfig(level=logging.INFO)

def get_local_time():
    """Отримує поточний час у встановленій таймзоні"""
    utc_now = datetime.datetime.utcnow()
    local_time = utc_now + datetime.timedelta(hours=TIMEZONE_OFFSET_HOURS)
    return local_time

def is_work_time():
    """Перевіряє чи зараз робочий час у місцевій таймзоні"""
    current_time = get_local_time()
    current_hour = current_time.hour
    return WORK_START_HOUR <= current_hour < WORK_END_HOUR

def get_next_work_start():
    """Повертає час наступного початку робочого дня у місцевій таймзоні"""
    now = get_local_time()
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
                        
                        # Метод 4: подвійний парсинг для escaped JSON
                        try:
                            # Якщо JSON був escaped як string у Railway
                            if json_str.startswith('"') and json_str.endswith('"'):
                                # Перший парсинг: розпаковуємо escaped string
                                unescaped = json.loads(json_str)
                                logging.info(f"Після першого парсингу: {type(unescaped)} - {repr(unescaped[:100])}")
                                
                                # Другий парсинг: парсимо сам JSON
                                if isinstance(unescaped, str):
                                    creds_dict = json.loads(unescaped)
                                    logging.info("✅ Метод 4: подвійний парсинг успішний")
                                else:
                                    creds_dict = unescaped
                                    logging.info("✅ Метод 4: перший парсинг достатній")
                            else:
                                # Пробуємо подвійний парсинг навіть без лапок
                                try:
                                    first_parse = json.loads(json_str)
                                    if isinstance(first_parse, str):
                                        creds_dict = json.loads(first_parse)
                                        logging.info("✅ Метод 4b: подвійний парсинг без лапок успішний")
                                    else:
                                        raise ValueError("Перший парсинг не дав строку")
                                except:
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
        "Надішліть ID акаунта, якщо хочете додати додаткову інформацію про соц або вебнейм - то записуйте все в один рядок:\n\n"
        "1232145 вебнейм/ агенство\n"
        f"⏰ Робочий час: {WORK_START_HOUR:02d}:00 - {WORK_END_HOUR:02d}:00 (UTC+{TIMEZONE_OFFSET_HOURS})"
    )
    await update.message.reply_text(help_text)

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test"""
    try:
        sheet = connect_sheet()
        local_time = get_local_time()
        await update.message.reply_text(
            f"✅ Підключення до Google Sheets працює!\n"
            f"🕐 Час сервера: {local_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🌍 Таймзона: UTC+{TIMEZONE_OFFSET_HOURS}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка підключення: {str(e)}")

async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /time"""
    local_time = get_local_time()
    utc_time = datetime.datetime.utcnow()
    
    time_info = (
        f"🕐 Місцевий час: {local_time.strftime('%H:%M:%S')}\n"
        f"🌍 Дата: {local_time.strftime('%Y-%m-%d')}\n"
        f"🌐 UTC час: {utc_time.strftime('%H:%M:%S')}\n"
        f"⏰ Таймзона: UTC+{TIMEZONE_OFFSET_HOURS}\n"
        f"📅 Робочий час: {WORK_START_HOUR:02d}:00 - {WORK_END_HOUR:02d}:00"
    )
    await update.message.reply_text(time_info)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    local_time = get_local_time()
    is_working = is_work_time()
    status_text = (
        f"📊 Статус бота\n\n"
        f"🕐 Поточний час: {local_time.strftime('%H:%M:%S')}\n"
        f"📅 Дата: {local_time.strftime('%Y-%m-%d')}\n"
        f"🌍 Таймзона: UTC+{TIMEZONE_OFFSET_HOURS}\n"
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
        # Використовуємо місцевий час для дати
        date_str = get_local_time().strftime("%Y-%m-%d")
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
    
    # Виводимо інформацію про таймзону при запуску
    local_time = get_local_time()
    utc_time = datetime.datetime.utcnow()
    logging.info(f"🌍 Налаштована таймзона: UTC+{TIMEZONE_OFFSET_HOURS}")
    logging.info(f"🕐 Місцевий час: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"🌐 UTC час: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"⏰ Робочий час: {WORK_START_HOUR:02d}:00 - {WORK_END_HOUR:02d}:00")
    
    while not shutdown_handler.shutdown:
        if is_work_time():
            current_time = get_local_time()
            logging.info(f"🟢 Запускаємо бота - робочий час ({current_time.strftime('%H:%M')})")
            
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
                    current_time = get_local_time()
                    logging.info(f"🔴 Зупинили бота - кінець робочого дня ({current_time.strftime('%H:%M')})")
                
            except Exception as e:
                logging.error(f"❌ Помилка при роботі бота: {e}")
                await asyncio.sleep(300)  # Чекаємо 5 хвилин перед перезапуском
                
        else:
            # Не робочий час - чекаємо
            next_start = get_next_work_start()
            now = get_local_time()
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
