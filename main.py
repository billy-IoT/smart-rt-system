import os
import telebot
from telebot import types
from groq import Groq
import re
import datetime

# --- KONFIGURASI ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # Pastikan ini diisi ID Telegram lu
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE ---
kas_rt = {"total": 0} # Contoh awal
warga_database = {} 
user_states = {} 
pending_approvals = {}
chat_history = {}

# --- FUNGSI BANTU ---
def get_role(uid): return "Pak RT" if str(uid) == str(ADMIN_ID) else "Warga"

def get_greeting():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12: return "Selamat Pagi"
    elif 12 <= hour < 15: return "Selamat Siang"
    elif 15 <= hour < 19: return "Selamat Sore"
    else: return "Selamat Malam"

def broadcast_emergency(reason):
    for uid in warga_database:
        try: bot.send_message(uid, f"🚨 DITETAPKAN DARURAT: {reason}! Segera amankan diri! 🚨")
        except: continue

# --- HANDLER START ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = {'name': message.from_user.first_name, 'username': message.from_user.username}
    role = get_role(uid)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, f"{get_greeting()}, {role}! Selamat datang di Smart RT.", reply_markup=markup)

# --- HANDLER UTAMA ---
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or (message.caption if message.caption else "")
    role = get_role(uid)
    
    # Update DB setiap ada chat
    warga_database[uid] = {'name': message.from_user.first_name, 'username': message.from_user.username}
    
    # 1. State Machine (Iuran)
    if uid in user_states:
        handle_lapor_steps(message)
        return
        
    # 2. Greeting Dinamis
    if text.lower() in ["halo", "hi", "pagi", "siang"]:
        bot.reply_to(message, f"{get_greeting()}, {role}!")
        return

    # 3. Logika Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Masukkan nama lengkap:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: Rp {kas_rt['total']:,}")
        return

    # 4. Emergency & Warranty
    if any(k in text.lower() for k in ["kemalingan", "maling", "kebakaran", "rampok"]):
        broadcast_emergency(text)
        return # Langsung stop di sini
        
    mentioned = re.findall(r'@(\w+)', text)
    for username in mentioned:
        target_uid = next((u for u, data in warga_database.items() if data.get('username') == username), None)
        if target_uid:
            try: bot.send_message(target_uid, f"⚠️ *Warning*: Anda di-tag oleh {role} dalam laporan: '{text}'")
            except: pass

    # 5. AI Processor
    if uid not in chat_history: chat_history[uid] = []
    chat_history[uid].append({"role": "user", "content": text})
    
    system_prompt = f"""
    Anda adalah asisten cerdas Smart RT. Anda sedang bicara dengan {role}.
    - Gunakan bahasa yang sopan, solutif, dan gaul sesuai role tersebut.
    - Cari info terbaru di internet jika ada pertanyaan umum/edukasi.
    - Kas RT saat ini: {kas_rt['total']}.
    - Jangan ngarang (halu). Jika tidak tahu, arahkan ke Pak RT.
    """
    
    res = client.chat.completions.create(
        messages=[{"role": "system", "content": system_prompt}] + chat_history[uid][-5:], 
        model="llama-3.3-70b-versatile"
    )
    ans = res.choices[0].message.content
    bot.reply_to(message, ans)

# --- HANDLER IURAN ---
def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Berapa nominal iurannya?")
    elif state == "WAITING_AMOUNT":
        user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': message.text}
        bot.reply_to(message, "Kirim foto bukti iuran:")
    elif state == "WAITING_PHOTO" and message.photo:
        pending_approvals[uid] = {'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah']}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"))
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"Iuran dari {user_states[uid]['nama']}\nNominal: Rp {user_states[uid]['jumlah']}", reply_markup=markup)
        bot.reply_to(message, "Laporan iuran terkirim ke Pak RT!")
        del user_states[uid]

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    if action == "approve":
        kas_rt["total"] += int(pending_approvals[uid]['jumlah'])
        bot.send_message(uid, f"✅ Laporan iuran lunas! Kas RT kini: Rp {kas_rt['total']:,}")
    bot.edit_message_caption(f"Status: {action.upper()}", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
