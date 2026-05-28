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
# Ganti baris hardcode tadi dengan ini
CHAT_ID_GRUP = os.getenv("CHAT_ID_GRUP")
bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)
bot_name = "SATRIA (Sistem Tanggap RT Ih Asique)"

# =========================================
# DATABASE & STATE
# =========================================
kas_rt = {"total": 0, "Kebersihan": 0, "Keamanan": 0, "Lain-lain": 0}
warga_database = {}
user_states = {}
pending_approvals = {}
chat_history = {}
spam_counter = {}
laporan_warga = []

# =========================================
# HELPER FUNCTIONS
# =========================================
def get_role(uid):
    return "Pak RT" if str(uid) == ADMIN_ID else "Warga"

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
    if uid in chat_history:
        chat_history[uid] = chat_history[uid][-6:]

def get_ai_response(uid, text, role):
    nama = warga_database.get(uid, {}).get("name", "Warga")
    system_prompt = f"Lu adalah {bot_name}. Aturan: santai, singkat, jangan formal, flow manusia. Kalau Pak RT: hormati."
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt}, *chat_history.get(uid, [])]
        )
        return response.choices[0].message.content
    except: return "Lagi gangguan nih, bentar ya 😹"

# =========================================
# MAIN HANDLER
# =========================================
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    role = get_role(uid)
    text = message.text or message.caption or ""
    warga_database.setdefault(uid, {"name": message.from_user.first_name, "username": message.from_user.username})

    # 1. Flow Iuran
    if uid in user_states:
        handle_iuran(message)
        return

    # 2. Perintah Pak RT
    if role == "Pak RT" and "laporan" in text.lower():
        bot.reply_to(message, "📋 Daftar laporan:\n" + "\n".join(laporan_warga) if laporan_warga else "Kosong.")
        return

    # 3. LOGIKA LAPOR (Pusat Masalah Kamu)
    if any(k in text.lower() for k in ["lapor", "parkir", "bermasalah"]):
        laporan_warga.append(f"{message.from_user.first_name} melapor: {text}")
        
        try:
            prompt = f"Buat teguran buat warga yang: {text}. Singkat, tegas, akhiri dengan - {bot_name}"
            res = client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "user", "content": prompt}])
            pesan_ai = res.choices[0].message.content
        except: pesan_ai = f"⚠️ Teguran terkait: {text}\n\n- {bot_name}"

        # Spill ke Grup
        if message.chat.type == "private":
            bot.send_message(CHAT_ID_GRUP, f"📢 [LAPORAN VIA JAPRI]\n\n{pesan_ai}")
            bot.reply_to(message, "✅ Laporan sudah diteruskan ke grup.")
        else:
            bot.reply_to(message, f"📢 TEGURAN TERBUKA\n\n{pesan_ai}")

        # Japri ke pelaku
        for username in re.findall(r'@(\w+)', text):
            target_uid = next((u for u, data in warga_database.items() if data.get("username", "").lower() == username.lower()), None)
            if target_uid:
                try: bot.send_message(target_uid, f"📢 Teguran RT (Private):\n\n{pesan_ai}")
                except: pass
        return # BERHENTI, jangan lanjut ke AI Chat

    # 4. CHAT AI (Hanya jika di-reply/mention atau Pak RT)
    if role == "Pak RT" or is_bot_target(message):
        chat_history.setdefault(uid, [])
        chat_history[uid].append({"role": "user", "content": text})
        limit_history(uid)
        ans = get_ai_response(uid, text, role)
        chat_history[uid].append({"role": "assistant", "content": ans})
        bot.reply_to(message, ans)

# =========================================
# FUNGSI LAIN (Iuran & Callback)
# =========================================
def handle_iuran(message):
    # (Kode iuran kamu tetap di sini)
    pass

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    # (Kode callback kamu tetap di sini)
    pass

bot.infinity_polling()
