import logging
import datetime
import re
import gspread
import os
import base64

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# Настройки
SPREADSHEET_NAME = 'AccountsList'
SHEET_NAME = 'Аркуш1'
CREDENTIALS_FILE = "credentials.json"

# Логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Розпаковуємо credentials.json з Base64 (змінна оточення)
credentials_base64 = os.getenv("睥杯䍉お塥求橉杯湉汎湣灚㉙晖坙橎㍢畖䍤獉楃杁湉祂㉢汰㍙晒坡楑楏楁㍣祒㉢渵坌癎塢灂䝢祖呌㉑橎硉楎栱楍獉楃杁湉祂塡桚䝤晖㉡㕖㉘歬橉杯橉祧呙㕕呙㑑橙橤䝎㍉䑍橚䝍穕㉎㕉穙橎坍歆浍㕙呍㉁䑍睫呏楫䅌杯䍉睊浣㉬塙汒㉘汴卥㙉䍉瑉卌琰啌䙊げ佬䙉卂噓䉚䕖杕こ婖卌琰卌挱止䨱啓㉖ず䍬啑䉒歔湊㍡潆㉡䡬塏督歑剆啒䉚噑䑎歑湴㉤湤㉕䉴ず䉖坑䨹歑剆㉑桖啢偖㍢䑰㉖㍎噓捰楢䩴ぎ牷䕍䰹呍さ塑㑣㍑さ楓伹ㅒ灂卡楴䙕䥆䕍㑣湢框さ啴䑏潊塤䭆坎䭚呗㉙坤䵸坣汴浥㑒橕卖浓捨橢獬䝖㕸歖睧湥つ步䵒橤塬ぎ䌵䝎䐹湣䙨䑚㉅啎癳坖漵噏䭒䝤牫坣砵浗䘹ご卬卍乴㉌佊䝓〵穎呬啑挱浢䘹汎啂坕楚塡告橖でが䥎ㅓ穰浗噴浣硍䡓㉣ㅖ印呎坆呒癧坒济つ䰵䕔畬穎癉䕣ぴ䙗潂䕕㉷坙偒㍑捤止佬塎偖噤㑆汕睂が癫楕側橓䝨ず奬䝔奤䑗癒坒䙖䝒䍸さ㑫䍖䤹かㅉ湒煨䕎祚㉖漹䝣猵坤乖楕焹歓捸湢楊坑啴䡔祎卥唹浔洱橓祎噤呒げ㑯㉍㕳湒灂坎癷块瘸㉖䡨䕗典䍓礸楡塴䑎䡚㉙呆䝓却ㅒ㍙㍙㍣湓捬止兰䙍䩰䕖䵴坑乤歑䉆啒湎ず䉖㍒䙨祒睳歙祒浤䉴穚睊歍け坒坰呙癒䑚穉橎癆汗獨汍穨ㅖ䉬㉎獬歕捖橢慊䡔硉穋䥖ご㑎ご穙坡㑉浥硧䑒灬坔欱歑獨歑䝎湒祤歔㉑䙕睰卢夹橤噎ご㉍䝡砰湔㍑橎睕啥癸塓捒止半橗穂㉣祚䡡睊噗乨㉍㍒坑䜵浙䩎䕎塴步婸穖乨坎ぴ浚佴䡢癫橙卖穤穒䙢坰㉋㕆㍙潖䡡㉑湑潤䕍捊橢㑅䝢〱橖㍕啥㍎㉋ぅㅒ潰䡕ㅙ噍桊穚ㅊ歖渱㍚低汙䱰浑㈸㉕丹㉒氹㉒呤汣㑤䍔氹歕塒汔ㅧ䡤㕬䙡捤湢灎啥䝴噗剎塙畎䡤睍䕖倹塔う䕍䝨䡒橂汖癉止礹塚瑒䙗㑑楒䉴浗湴䝒坎坏汴歗㍫㍒㉂㍡ㅫ䡍楨湍捬橢此啒㘱歓䌵䡔癯穡䡚橓剖湎癖歖潨浡湤坍䑚浖稱䕍㑨䙗祙䑏佖啕䍴ㅚ䕆塗㉉䕡䠱䕍䝎汙䙚楤獴㉖捚浢塊穋䕤㍡䙆塑瑨䝡湬汣祒䙚䑬橔佊㉍䉚䝎䱤歚祅橚睅穑獒啕〱歙㙰啑氱啎兰㍣硙呥煎啤做浢ㅯ浕捚浢潒汖ㅅ䡏但啔癫浤〸呢穚歓兤啒䩆䕒䈱啥但塔㑆呣煆䙍湂歍瑊㍚癎歑っ䝕䕴䙍䱚橒牨䡖佬噥卖呥捆止㐴块歚汚卬塙灎䕡瑊湔潬噤噊䝡硧㍤剨こ湊啕㍍こ㕑䡣つ止㍖き浬䕍祫步桊浔噎汎䵤橣癁䡕婖䕢挵橢橎楖爸湕偒䝚䑆啙䝖华堹䕕㕅問塨橒䝖䝖ㅫ啤佖䙡㕂㉑夵汍癊济䑤䝕欵䕍潴䕚䩬ㅒ橰噓㍚啍票卓捴止䥤浑儹䕚樵䡕㉧啥㄰浤㑎䕍㌴䑡票浚䉚穢䥖穕啒歗癯䝡㑫穣㕁ぎ电䡚桰歎㑖坏坤ㅍ㉅坎㉕呤䉨䕗捨湢穊䕚牒噑祎䡒䱤浑剤䙒潂䙥䭒䑣剂汗湊楕㙴噚慆楗汴䝚䠹䙚畂噚㍉噙獖䙔偎塏汨浚灰穢桨浢報䑔捬橢ㅎ啚㍣䡣偎ㅌ癎塢䵆㉖䭤す䭬歓ㅳ䡓汊䑏㕒䕕吹䝣慚噤噬啒䕤䍢橴歗圹䕥げ㍑睁塤䱤橚歒浓穒呗捊浢塖坕穒湑潬湗桂㍔湤䝚䙰ぢ歸䑏汚䝒牯䝕䍴浙奸㉋穳歚橸橤䕖㍒剖䙡㙊䡖䙤啤潬汒䥰ㅌ䱆浑剤穑捖楢䨹坓㑙啔䡤浒瘸䑓癙ㅒ穖塕睆㉕砵䡚䩖す祆济㑴塍㑬噗睅䕎漹浥獤坕器ㅖ瑎䝖㉊橓ㅑ㍚䡰啖穚ㅢ捰止䙸浢ㅕ此佖歒㐹呍瑖此ㅅ橙煨䡔此䝣乴汒䕬䡓瑤塍周浒穴啔㙎湙乎浙祒橎䩚䑎䱒䝖䕊浓異坢湰浚挱湢㍙坍奖䙥牉穔坖噤奆っ䱎汔硎块けㅚ楚䍖ㅳ块癸汎湚䑚兎穖癊つ䍴ず煨䝗㌴坢但㉓䉊ぎ睙塕橬が捴止楴䙚穎橡䕬㉣牨が橒䝎但䝗楴坑呸汖䙂橢橤䕚䝬䕕吱浗牧䑡牫汤乊ㅓ婰䡕穚㍣㍧浖椵䑓㕬ち噰卍挹止煬正䤹祖礸䡖剚歕儹汗慤け乨啚穴此㍑塍穫䝎奴祙㘹啣歎ぢ䩊塑奤ㅙ睆止硉卓䭴坙噸䕗兎汍㍒橡捨楢堹噤婤湑䍆䑤硆坖乖問唵積乖啗䝸汔畸卌琰卌䘱歔村䙕䩊歖商卒䱂噒瑫卌琰噌畸楉䭷䍉楁㉙灸坚〵㉘瑖坙獬橉杯湉湒浙〹㉣汨塚䅒㍣祒㉢渵坌癎塢灂䝢祖呌㉑橎硉楎栱楍瀵坙田㍚汎湣灚㉙桖㉙癎坤〵浌癎卢獉楃杁浉獎坡畖䙤瀹䍚㙉䍉硉呍祅呏硅呏ㅁ呍ㅁ䑍㍑積㑁呏楧䅌杯䍉桊塤潒㍘祖卡㙉䍉潊䡤睒穣癯㉌橆㉙ㄹ湢穒浌癤㉢獤博樵㉢瘰祢瘹塙ざ䑡癉塙ざ䍡獉楃杁湉癒㉡畖㍘祖卡㙉䍉潊䡤睒穣癯㉌根塤潒楍渵㉢渹䝢桖䝣穬浌癎卢〹㉢汴楢獉楃杁浉ㅆ䝤晨䡣癊浤歬塚晊䑥睕噏樹塚お㍘祖䍢㙉䍉潊䡤睒穣癯㍌㍤祤渵㉢渹䝢桖䝣穬浌癎卢瘹塙ざ䑡癉橤癅㉙祖䡤楍䅌杯䍉橊䝢汬湢晒䑥睕噏樹塚お㍘祖䍢㙉䍉潊䡤睒穣癯㍌㍤祤渵㉢渹䝢桖䝣穬浌癎卢礹㉢癊䍤㈹卍琹塚桒䝚う卙㐹呎㕁㍌湒浙〹㉣汨塚汑䑎穂䡤癊浢瑣㉙琹䝣獬塚瑉䑎㉙橍㉅坌祅浌桬卢渵㉣祖浤橬坚橆㉙ㄹ湢畑㉙琹楉䭷䍉楁坤瀵浤祖㉣晖䝚琹坙畬橉杯浉癤㉢獤坚睆塡畍㉙琹杉㥰权㴽਍")
if not credentials_base64:
    logger.error("GOOGLE_CREDENTIALS_BASE64 not set. Завантажте Base64 ключ у змінні оточення.")
else:
    try:
        with open(CREDENTIALS_FILE, "wb") as f:
            f.write(base64.b64decode(credentials_base64))
        logger.info("credentials.json записано")
    except Exception as e:
        logger.exception("Не вдалося записати credentials.json: %s", e)
        raise

# Підключення до Google Sheets
def connect_sheet():
    try:
        client = gspread.service_account(filename=CREDENTIALS_FILE)
        sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        logger.exception("Помилка підключення до Google Sheets: %s", e)
        raise

# Обробка повідомлень
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

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
        logger.exception("Помилка при обробці:", exc_info=e)
        await update.message.reply_text(f"❌ Помилка: {e}")

# Запуск бота
if __name__ == '__main__':
    TELEGRAM_TOKEN = os.getenv("7671254962:AAFhQh2TnOeu2MabFaS7LwGIg7H8_4pPFY4")
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN не встановлено в оточенні")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot запущений, polling...")
    app.run_polling()
