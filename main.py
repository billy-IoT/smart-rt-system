import os
import re
import telebot
import datetime
import pytz
from telebot import types
from groq import Groq

# =========================================
# CONFIG
# =========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID"))
CHAT_ID_GRUP = os.getenv("CHAT_ID_GRUP")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)
bot_name = "SATRIA (Sistem Tanggap RT Ih Asique)"

# =========================================
# DATABASE & STATE
# =========================================
kas_rt = {"total": 0, "Kebersihan": 0, "Keamanan": 0, "Lain-lain": 0}
laporan_warga = []
warga_database = {}
user_states = {}
pending_approvals = {}
chat_history = {}
spam_counter = {}

# =========================================
# HELPER FUNCTIONS
# =========================================
def get_role(uid): return "Pak RT" if str(uid) == ADMIN_ID else "Warga"

def get_greeting():
    hour = datetime.datetime.now(pytz.timezone("Asia/Jakarta")).hour
    if 5 <= hour < 12: return "Pagi"
    if 12 <= hour < 15: return "Siang"
    if 15 <= hour < 18: return "Sore"
    return "Malam"

def is_bot_target(message):
    if message.chat.type == "private": return True
    if message.reply_to_message and message.reply_to_message.from_user.is_bot: return True
    if message.text and f"@{bot.get_me().username}" in message.text: return True
    return False

def limit_history(uid):
    if uid in chat_history: chat_history[uid] = chat_history[uid][-6:]

def broadcast_message(text, is_emergency=False):
    announcement = f"🚨 DARURAT 🚨\n\n{text}\n\nMohon perhatian seluruh warga." if is_emergency else f"📢 Pengumuman RT\n\n{text}"
    for uid in warga_database:
        try: bot.send_message(uid, announcement)
        except: pass

def get_ai_response(uid, text, role, is_lapor=False):
    nama = warga_database.get(uid, {}).get("name", "Warga")
    if is_lapor:
        system_prompt = f"Buat teguran singkat, tegas, namun sopan. Masalah: {text}. Akhiri dengan: - {bot_name}"
    else:
        system_prompt = f"{bot_name}. Nama: {nama}, Role: {role}. Chat santai, manusiawi. Kalau Pak RT: hormati."
    try:
        res = client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}])
        ans = res.choices[0].message.content
        if "tidak dapat membantu" in ans.lower() or "maaf" in ans.lower():
            return f"📢 Teguran RT: Laporan '{text}' diterima. Mohon jaga ketertiban. - {bot_name}"
        return ans
    except: return f"⚠️ Gangguan AI: {text}"

# =========================================
# MAIN HANDLER (Logic Lengkap)
# =========================================
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or message.caption or ""
    warga_database.setdefault(uid, {"name": message.from_user.first_name, "username": message.from_user.username})

    if uid in user_states: handle_iuran(message); return

    # Admin Logic
    if get_role(uid) == "Pak RT":
        if "laporan" in text.lower():
            bot.reply_to(message, "📋 Daftar laporan:\n" + "\n".join(laporan_warga) if laporan_warga else "Kosong.")
            return
        if text.startswith("/bc "): broadcast_message(text.replace("/bc ", "")); return
        if text.startswith("/mute "):
            target_username = text.split(" ")[1].replace("@", "")
            target_uid = next((u for u, d in warga_database.items() if d.get("username", "").lower() == target_username.lower()), None)
            if target_uid and target_uid != ADMIN_ID:
                try: 
                    bot.restrict_chat_member(message.chat.id, int(target_uid), until_date=datetime.datetime.now() + datetime.timedelta(minutes=5))
                    bot.reply_to(message, f"🔇 @{target_username} dimute 5 menit.")
                except: pass
            return

    # Spam Counter
    spam_counter[uid] = spam_counter.get(uid, 0) + 1
    if spam_counter[uid] > 10:
        if message.chat.type != "private":
            try: bot.restrict_chat_member(message.chat.id, int(uid), until_date=datetime.datetime.now() + datetime.timedelta(minutes=5))
            except: pass
        return

    # Logika Lapor (Grup & Japri)
    if any(k in text.lower() for k in ["lapor", "parkir", "bermasalah"]):
        laporan_warga.append(f"{message.from_user.first_name}: {text}")
        pesan_ai = get_ai_response(uid, text, get_role(uid), is_lapor=True)
        if CHAT_ID_GRUP:
            try: bot.send_message(CHAT_ID_GRUP, f"📢 [LAPORAN WARGA]\n\n{pesan_ai}")
            except: pass
        for username in re.findall(r'@(\w+)', text):
            target_uid = next((u for u, d in warga_database.items() if d.get("username", "").lower() == username.lower()), None)
            if target_uid:
                try: bot.send_message(target_uid, f"📢 Teguran RT (Japri):\n\n{pesan_ai}")
                except: pass
        bot.reply_to(message, "✅ Laporan diteruskan.")
        return

    if text == "💰 Lapor Iuran":
        user_states[uid] = {"state": "WAITING_NAME"}
        bot.reply_to(message, "Masukin nama lengkap:")
        return

    # Chat AI Biasa
    if is_bot_target(message):
        chat_history.setdefault(uid, [])
        chat_history[uid].append({"role": "user", "content": text})
        ans = get_ai_response(uid, text, get_role(uid))
        bot.reply_to(message, ans)

# =========================================
# FLOW IURAN & CALLBACK (Lengkap sesuai aslimu)
# =========================================
def handle_iuran(message):
    uid = str(message.from_user.id)
    state_data = user_states[uid]
    state = state_data["state"]
    if state == "WAITING_NAME":
        state_data["nama"] = message.text
        state_data["state"] = "WAITING_CATEGORY"
        bot.reply_to(message, "Pilih kategori:\n1. Kebersihan\n2. Keamanan\n3. Lain-lain")
    elif state == "WAITING_CATEGORY":
        cat_map = {"1": "Kebersihan", "2": "Keamanan", "3": "Lain-lain"}
        if message.text in cat_map:
            state_data["kategori"] = cat_map[message.text]
            if message.text == "3": state_data["state"] = "WAITING_DESC"; bot.reply_to(message, "Masukin keterangan:")
            else: state_data["state"] = "WAITING_AMOUNT"; bot.reply_to(message, "Masukin nominal:")
    elif state == "WAITING_DESC":
        state_data["keterangan"] = message.text
        state_data["state"] = "WAITING_AMOUNT"
        bot.reply_to(message, "Masukin nominal:")
    elif state == "WAITING_AMOUNT":
        raw = re.sub(r'\D', '', message.text)
        if raw.isdigit() and int(raw) >= 10000:
            state_data["jumlah"] = int(raw)
            state_data["state"] = "WAITING_PHOTO"
            bot.reply_to(message, "Kirim foto bukti transfer:")
        else: bot.reply_to(message, "⚠️ Minimal Rp10.000")
    elif state == "WAITING_PHOTO":
        if message.photo:
            pending_approvals[uid] = state_data
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
            bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💰 Laporan Iuran: {state_data['nama']}", reply_markup=markup)
            bot.reply_to(message, "✅ Terkirim ke Pak RT.")
            del user_states[uid]

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    if uid in pending_approvals:
        data = pending_approvals[uid]
        if action == "approve":
            kas_rt[data['kategori']] += data['jumlah']
            kas_rt["total"] += data['jumlah']
            bot.send_message(uid, "✅ Disetujui.")
        else: bot.send_message(uid, "❌ Ditolak.")
        del pending_approvals[uid]

print("Bot Smart RT nyala")
bot.remove_webhook()
bot.infinity_polling(none_stop=True, skip_pending=True)
