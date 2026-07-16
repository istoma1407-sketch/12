import telebot
from telebot import types
import re
import os
from datetime import datetime
from collections import defaultdict
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import html

TOKEN = "8919797557:AAGprMy0GohOMKX4gLrNMxtxmd3E5OlKWZk"

session = requests.Session()
retry = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 429])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

bot = telebot.TeleBot(TOKEN)
bot.session = session

user_data = defaultdict(lambda: {
    "media": [],
    "txt": None,
    "extra_text": "",
    "txt_file_name": None,
    "entities": []
})

FIELDS_ORDER = [
    "ФИО", "Дата рождения", "Возраст", "Номер", "Оператор", "Регион",
    "Место рождения", "Адрес", "Родственники", "Учёба",
    "Вконтакте", "Одноклассники", "Telegram", "Instagram", "MAX",
    "Email", "Паспорт", "СНИЛС", "ИНН", "Мобильный банк"
]

def get_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("✅ Отправить всё", callback_data="send_all"))
    markup.add(types.InlineKeyboardButton("🗑 Очистить", callback_data="clear"))
    return markup

def save_media_locally(message, chat_id):
    media_dir = f"media/{chat_id}"
    os.makedirs(media_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        ext = ".jpg"
        mtype = "photo"
    elif message.content_type == 'video':
        file_id = message.video.file_id
        ext = ".mp4"
        mtype = "video"
    elif message.content_type == 'video_note':
        file_id = message.video_note.file_id
        ext = ".mp4"
        mtype = "video"
    elif message.content_type == 'voice':
        file_id = message.voice.file_id
        ext = ".ogg"
        mtype = "voice"
    elif message.content_type == 'document':
        file_id = message.document.file_id
        ext = os.path.splitext(message.document.file_name or "file")[1]
        mtype = "document"
    else:
        return None, None
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        filename = f"{timestamp}_{mtype}{ext}"
        filepath = os.path.join(media_dir, filename)
        with open(filepath, "wb") as f:
            f.write(downloaded)
        return filepath, mtype
    except Exception as e:
        print(f"[save_media] Ошибка: {e}")
        return None, None

def format_link(field, value, real_url=None):
    val = html.escape(str(value).strip())
    url = real_url
    if not url:
        if field == "Вконтакте" and ("vk.com" in str(value).lower() or str(value).lower().startswith("id")):
            url = str(value) if str(value).startswith("http") else f"https://vk.com/{value}"
        elif field == "Одноклассники" and "ok.ru" in str(value).lower():
            url = str(value) if str(value).startswith("http") else f"https://ok.ru/{value}"
        elif field == "Instagram" and ("instagram.com" in str(value).lower() or str(value).startswith("@")):
            clean = str(value).replace("@", "")
            url = str(value) if "instagram.com" in str(value).lower() else f"https://instagram.com/{clean}"
        elif field == "MAX" and str(value).startswith("http"):
            url = value
        elif field == "Telegram":
            tg = re.search(r'@(\w+)', str(value))
            if tg:
                url = f"https://t.me/{tg.group(1)}"
            else:
                num = re.search(r'(\d{9,})', str(value))
                if num:
                    url = f"https://t.me/{num.group(1)}"
        elif field == "Email" and "@" in str(value):
            em = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', str(value))
            if em:
                url = f"mailto:{em.group(0)}"
    return f'<a href="{url}">{val}</a>' if url else val

def parse_client_data(txt_content, extra_text, entities_list):
    full_text = (txt_content or "") + "\n" + (extra_text or "")
    parsed = {}
    field_urls = {}
    for ent in entities_list:
        if ent.type == 'text_link' and ent.url:
            url = ent.url
            if "vk.com" in url.lower() or "/id" in url.lower():
                field_urls["Вконтакте"] = url
            elif "ok.ru" in url.lower():
                field_urls["Одноклассники"] = url
            elif "instagram.com" in url.lower():
                field_urls["Instagram"] = url
            elif "max.ru" in url.lower():
                field_urls["MAX"] = url

    def clean_line(line):
        return re.sub(r'^[\U0001F000-\U0001FFFF\U00002700-\U000027BF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\s🧢🧑‍💻👨‍🦳💬📧👁🔎📱🏦]+', '', line).strip()

    lines = full_text.split('\n')
    for line in lines:
        cleaned = clean_line(line)
        if not cleaned or ':' not in cleaned:
            continue
        parts = cleaned.split(':', 1)
        if len(parts) < 2:
            continue
        field_raw = parts[0].strip().lower()
        value = parts[1].strip()
        if not value or value in ["===", "—", "-", "пусто", "нет"] or value.startswith("==="):
            continue

        if "дата рождения" in field_raw or "день рождения" in field_raw:
            parsed["Дата рождения"] = value
            continue
        if field_raw.startswith("возраст"):
            parsed["Возраст"] = value
            continue
        if field_raw.startswith("оператор"):
            parsed["Оператор"] = value
            continue
        if field_raw.startswith("регион"):
            parsed["Регион"] = value
            continue
        if "место рождения" in field_raw:
            parsed["Место рождения"] = value
            continue
        if "мобильный банк" in field_raw:
            parsed["Мобильный банк"] = value
            continue
        if field_raw.startswith("telegram"):
            tg_match = re.search(r'@(\w+)', value)
            if tg_match:
                parsed["Telegram"] = "@" + tg_match.group(1)
            else:
                num_match = re.search(r'\[(\d{9,})\]', value)
                if num_match:
                    parsed["Telegram"] = num_match.group(1)
            continue
        if field_raw.startswith("max"):
            parsed["MAX"] = value
            continue
        if field_raw.startswith("вконтакте"):
            parsed["Вконтакте"] = value
            continue
        if field_raw.startswith("одноклассники"):
            parsed["Одноклассники"] = value
            continue
        if field_raw.startswith("instagram"):
            parsed["Instagram"] = value
            continue
        if field_raw.startswith("e-mail") or field_raw.startswith("email"):
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', value)
            if emails:
                parsed["Email"] = ", ".join(list(dict.fromkeys(emails))[:3])
            continue
        if field_raw.startswith("телефон") or field_raw.startswith("номер"):
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 10:
                parsed["Номер"] = digits[:11]
            continue
        if "телефонные книги" in field_raw or "личности" in field_raw:
            parsed["Родственники"] = value
            continue
        if field_raw.startswith("адрес"):
            parsed["Адрес"] = value
            continue
        if field_raw.startswith("паспорт"):
            parsed["Паспорт"] = value
            continue
        if field_raw.startswith("снилс"):
            parsed["СНИЛС"] = value
            continue
        if field_raw.startswith("инн"):
            digits = re.sub(r'\D', '', value)
            if digits:
                parsed["ИНН"] = digits
            continue
        if field_raw.startswith("школа") or field_raw.startswith("учёба"):
            parsed["Учёба"] = value
            continue

    for field, url in field_urls.items():
        if field in parsed:
            parsed[field + "_url"] = url
        else:
            parsed[field] = url

    if "Вконтакте" not in parsed:
        vk = re.search(r'https?://(?:www\.)?vk\.com/[^\s\)]+', full_text, re.IGNORECASE)
        if vk:
            parsed["Вконтакте"] = vk.group(0)
    if "Одноклассники" not in parsed:
        ok = re.search(r'https?://(?:www\.)?ok\.ru/[^\s\)]+', full_text, re.IGNORECASE)
        if ok:
            parsed["Одноклассники"] = ok.group(0)
    if "Instagram" not in parsed:
        ig = re.search(r'https?://(?:www\.)?instagram\.com/[^\s\)]+', full_text, re.IGNORECASE)
        if ig:
            parsed["Instagram"] = ig.group(0)
    if "MAX" not in parsed:
        max_link = re.search(r'https?://max\.ru/[^\s]+', full_text)
        if max_link:
            parsed["MAX"] = max_link.group(0)

    if "MAX" in parsed and "max.ru" not in str(parsed.get("MAX", "")).lower() and 2 < len(str(parsed["MAX"])) < 50:
        parsed["ФИО"] = parsed["MAX"]
    elif "Вконтакте" in parsed and 2 < len(str(parsed.get("Вконтакте", ""))) < 50 and "http" not in str(parsed.get("Вконтакте", "")).lower():
        parsed["ФИО"] = parsed["Вконтакте"]
    elif "Одноклассники" in parsed and 2 < len(str(parsed.get("Одноклассники", ""))) < 50:
        parsed["ФИО"] = parsed["Одноклассники"]

    for field in list(parsed.keys()):
        if field.endswith("_url"):
            continue
        val = parsed[field]
        if not val or len(str(val)) < 2 or str(val) in ["===", "—", "-", "пусто", "нет"]:
            del parsed[field]

    return parsed

@bot.message_handler(commands=['start'])
def start(message):
    user_data[message.chat.id] = {"media": [], "txt": None, "extra_text": "", "txt_file_name": None, "entities": []}
    bot.send_message(message.chat.id, "✅ <b>Бот готов!</b>\n\nКидай .txt + пересланные сообщения + медиа", parse_mode='HTML', reply_markup=get_keyboard())

@bot.message_handler(content_types=['text'])
def handle_text(message):
    ud = user_data[message.chat.id]
    ud["extra_text"] += message.text + "\n\n"
    if message.entities:
        ud["entities"].extend(message.entities)
    bot.reply_to(message, "✅ Текст принят", reply_markup=get_keyboard())

@bot.message_handler(content_types=['photo', 'video', 'voice', 'video_note', 'document'])
def handle_content(message):
    chat_id = message.chat.id
    ud = user_data[chat_id]
    if message.document and message.document.file_name and message.document.file_name.endswith('.txt'):
        file_info = bot.get_file(message.document.file_id)
        text = bot.download_file(file_info.file_path).decode('utf-8', errors='replace')
        ud["txt"] = text
        ud["txt_file_name"] = message.document.file_name
        bot.reply_to(message, "✅ .txt принят", reply_markup=get_keyboard())
    else:
        filepath, mtype = save_media_locally(message, chat_id)
        if filepath:
            ud["media"].append({"path": filepath, "type": mtype})
            bot.reply_to(message, f"✅ {mtype} сохранён ({len(ud['media'])})", reply_markup=get_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    ud = user_data[chat_id]
    if call.data == "send_all":
        if not ud.get("txt") and not ud.get("extra_text"):
            bot.answer_callback_query(call.id, "❌ Нужен .txt или текст!")
            return

        parsed = parse_client_data(ud.get("txt"), ud.get("extra_text"), ud.get("entities", []))

        # Медиа
        if ud["media"]:
            try:
                media_group = []
                for item in ud["media"][:10]:
                    if item["type"] == "photo":
                        media_group.append(types.InputMediaPhoto(open(item["path"], 'rb')))
                    elif item["type"] in ["video", "video_note"]:
                        media_group.append(types.InputMediaVideo(open(item["path"], 'rb'), supports_streaming=True))
                if media_group:
                    bot.send_media_group(chat_id, media_group)
            except:
                for item in ud["media"][:10]:
                    try:
                        if item["type"] == "photo":
                            bot.send_photo(chat_id, open(item["path"], 'rb'))
                        elif item["type"] in ["video", "video_note"]:
                            bot.send_video(chat_id, open(item["path"], 'rb'), supports_streaming=True)
                        elif item["type"] == "voice":
                            bot.send_voice(chat_id, open(item["path"], 'rb'))
                        time.sleep(0.7)
                    except:
                        pass

        # === КАРТОЧКА ===
        caption = "<blockquote>"
        for field in FIELDS_ORDER:
            if field in parsed and parsed[field]:
                value = str(parsed[field]).strip()
                real_url = parsed.get(field + "_url")
                linked_value = format_link(field, value, real_url)
                caption += f"<b>{field}:</b> {linked_value}\n\n"
        caption += "\nНа данный момент у тебя 2 исхода:\n\n"
        caption += "1. 5000p — закрываешь вопрос навсегда, и мы стираем все данные.\n\n"
        caption += "2. Полный слив — вceм poдным, дрyзьям, рaбoтoдaтeлям, в гoрoдскиe чaты.\n\n"
        caption += "❗️ИГНОР - РАССЫЛКА, БЛОКИРУЕШЬ- РАССЫЛКА , ОЧИЩАЕШЬ ПЕРЕПИСКУ - РАССЫЛКА❗️\n\n"
        caption += "А также полностью вся информация у выше стоящих людей, я всего лишь пешка имеющая небольшую часть информации, если ты не скидываешь бабки - передаю им чтоб начинали рассылку, и они уже дальше занимаются тобой.\n\n"
        caption += "Телеграм канал со сливами: https://t.me/+O7WsdDV7o3JmMDFh"
        caption += "</blockquote>"

        bot.send_message(chat_id, caption, parse_mode='HTML', disable_web_page_preview=False)

        user_data[chat_id] = {"media": [], "txt": None, "extra_text": "", "txt_file_name": None, "entities": []}

    elif call.data == "clear":
        user_data[chat_id] = {"media": [], "txt": None, "extra_text": "", "txt_file_name": None, "entities": []}
        bot.answer_callback_query(call.id, "🗑 Очищено")
        bot.send_message(chat_id, "Сессия очищена", reply_markup=get_keyboard())

print("🤖 Бот запущен...")
bot.infinity_polling(none_stop=True, interval=1, timeout=20)
