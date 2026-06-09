import os
import re
import telebot
import datetime
import pytz
import threading
import queue
import logging
from telebot import types
from groq import Groq, BadRequestError, RateLimitError

# =========================================
# SETUP LOGGING & CONFIG
# =========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID"))
CHAT_ID_GRUP = os.getenv("CHAT_ID_GRUP")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)
bot_name = "SATRIA (Sistem Tanggap RT Ih Asique)"

# =========================================
# QUEUE SYSTEM (Background Worker)
# =========================================
task_queue = queue.Queue()

def worker():
    logging.info("Worker thread started.")
    while True:
        task = task_queue.get()
        try:
            # Generate response via AI
            ans = get_ai_response(task['uid'], task['text'], task['role'], task['is_lapor'])
            
            # 1. Reply ke pelapor
            bot.reply_to(task['message'], ans)
            
            # 2. Khusus Lapor: Broadcast Grup + Japri Tag
            if task['is_lapor']:
                # Kirim ke Grup
                if CHAT_ID_GRUP:
                    try: bot.send_message(CHAT_ID_GRUP, f"📢 [LAPORAN WARGA]\n\n{ans}")
                    except: pass
                
                # Kirim Japri ke yang di-tag (@username)
                usernames = re.findall(r'@(\w+)', task['text'])
                for username in usernames:
                    target_uid = next((u for u, d in warga_database.items() if d.get("username", "").lower() == username.lower()), None)
                    if target_uid:
                        try: 
                            bot.send_message(target_uid, f"📢 Teguran RT (Japri):\n\n{ans}")
                        except: pass

        except Exception as e:
            logging.error(f"Worker Runtime Error: {e}")
        finally:
            task_queue.task_done()

threading.Thread(target=worker, daemon=True).start()

# =========================================
# DATABASE & STATE (In-Memory)
# =========================================
kas_rt = {"total": 0, "Kebersihan": 0, "Keamanan": 0, "Lain-lain": 0}
laporan_warga = []
warga_database = {}
user_states = {}
pending_approvals = {}
spam_counter = {}

# =========================================
# HELPERS
# =========================================
def get_role(uid): return "Pak RT" if str(uid) == ADMIN_ID else "Warga"

def is_bot_target(message):
    if message.chat.type == "private": return True
    if message.reply_to_message and message.reply_to_message.from_user.is_bot: return True
    if message.text and f"@{bot.get_me().username}" in message.text: return True
    return False

def get_ai_response(uid, text, role, is_lapor=False):
    nama = warga_database.get(uid, {}).get("name", "Warga")
    # Prompt "mantap" sesuai permintaan
    system_prompt = (f"Kamu adalah {bot_name}, asisten RT yang bijak tapi sarkas dan tegas. "
                     f"Berikan teguran singkat, mantap, dan solutif untuk masalah berikut: {text}. "
                     f"Akhiri pesan dengan: - {bot_name}") if is_lapor else (f"{bot_name}. Nama: {nama}, Role: {role}. Chat santai, manusiawi.")
    try:
        res = client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}])
        return res.choices[0].message.content
    except BadRequestError: return "⚠️ Pesan terlalu panjang (Token Limit)."
    except RateLimitError: return "⚠️ AI lagi sibuk banget, tunggu sebentar ya."
    except Exception as e:
        logging.error(f"AI Call Error: {e}")
        return f"⚠️ Gangguan AI: {str(e)[:30]}"

# =========================================
# HANDLERS
# =========================================
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or message.caption or ""
    warga_database.setdefault(uid, {"name": message.from_user.first_name, "username": message.from_user.username})

    # Iuran State
    if uid in user_states: handle_iuran(message); return

    # Admin Logic
    if get_role(uid) == "Pak RT":
        if "laporan" in text.lower():
            bot.reply_to(message, "📋 Daftar laporan:\n" + "\n".join(laporan_warga) if laporan_warga else "Kosong.")
            return
        if text.startswith("/bc "):
            for u in warga_database:
                try: bot.send_message(u, f"📢 Pengumuman RT\n\n{text.replace('/bc ', '')}")
                except: pass
            return

    # Lapor Queueing
    if any(k in text.lower() for k in ["lapor", "parkir", "bermasalah"]):
        laporan_warga.append(f"{message.from_user.first_name}: {text}")
        task_queue.put({'type': 'ai_chat', 'uid': uid, 'text': text, 'role': get_role(uid), 'is_lapor': True, 'message': message})
        bot.reply_to(message, "✅ Laporan diproses dengan gaya RT...")
        return

    # Iuran Entry
    if text == "💰 Lapor Iuran":
        user_states[uid] = {"state": "WAITING_NAME"}
        bot.reply_to(message, "Masukin nama lengkap:")
        return

    # AI Chat
    if is_bot_target(message):
        task_queue.put({'type': 'ai_chat', 'uid': uid, 'text': text, 'role': get_role(uid), 'is_lapor': False, 'message': message})
        bot.reply_to(message, "⏳ Satria lagi mikir...")

# =========================================
# IURAN FLOW
# =========================================
def handle_iuran(message):
    uid = str(message.from_user.id)
    state_data = user_states[uid]
    if state_data["state"] == "WAITING_NAME":
        state_data["nama"] = message.text; state_data["state"] = "WAITING_CATEGORY"
        bot.reply_to(message, "Pilih kategori:\n1. Kebersihan\n2. Keamanan\n3. Lain-lain")
    elif state_data["state"] == "WAITING_CATEGORY":
        cat_map = {"1": "Kebersihan", "2": "Keamanan", "3": "Lain-lain"}
        if message.text in cat_map:
            state_data["kategori"] = cat_map[message.text]
            state_data["state"] = "WAITING_DESC" if message.text == "3" else "WAITING_AMOUNT"
            bot.reply_to(message, "Masukin keterangan:" if message.text == "3" else "Masukin nominal:")
    elif state_data["state"] == "WAITING_DESC":
        state_data["keterangan"] = message.text; state_data["state"] = "WAITING_AMOUNT"
        bot.reply_to(message, "Masukin nominal:")
    elif state_data["state"] == "WAITING_AMOUNT":
        raw = re.sub(r'\D', '', message.text)
        if raw.isdigit() and int(raw) >= 10000:
            state_data["jumlah"] = int(raw); state_data["state"] = "WAITING_PHOTO"
            bot.reply_to(message, "Kirim foto bukti transfer:")
        else: bot.reply_to(message, "⚠️ Minimal Rp10.000")
    elif state_data["state"] == "WAITING_PHOTO":
        if message.photo:
            pending_approvals[uid] = state_data
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
            bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💰 Iuran: {state_data['nama']}", reply_markup=markup)
            bot.reply_to(message, "✅ Terkirim ke Pak RT."); del user_states[uid]

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    if uid in pending_approvals:
        data = pending_approvals[uid]
        if action == "approve":
            kas_rt[data['kategori']] += data['jumlah']; kas_rt["total"] += data['jumlah']
            bot.send_message(uid, "✅ Disetujui.")
        else: bot.send_message(uid, "❌ Ditolak.")
        del pending_approvals[uid]

if __name__ == "__main__":
    print("Bot Smart RT nyala")
    bot.remove_webhook()
    bot.infinity_polling(none_stop=True)
