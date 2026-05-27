import os
import telebot
from telebot import types
from groq import Groq
import re

# KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# DATABASE
kas_rt = {"total": 0}
warga_database = {} 
user_states = {} 
pending_approvals = {}
chat_history = {}

def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

# HANDLER START
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = {'name': message.from_user.first_name, 'username': message.from_user.username}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga!", parse_mode='Markdown', reply_markup=markup)

def broadcast_emergency(reason):
    for uid in warga_database:
        try:
            # Kirim peringatan 3 kali (batas aman biar gak kena ban Telegram)
            for _ in range(3):
                bot.send_message(uid, f"🚨 DITETAPKAN DARURAT: {reason}! Segera amankan diri! 🚨")
        except: continue

# HANDLER UTAMA
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or (message.caption if message.caption else "")
    warga_database[uid] = {'name': message.from_user.first_name, 'username': message.from_user.username}
    
    # 1. State Machine (Iuran)
    if uid in user_states:
        handle_lapor_steps(message)
        return
        
    # 2. Logika Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Masukkan nama lengkap:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: Rp {kas_rt['total']:,}")
        return

    # 3. Warranty System
    mentioned = re.findall(r'@(\w+)', text)
    # TRIGGER SPAM DARURAT
    if any(k in text.lower() for k in ["kemalingan", "kebakaran", "rampok"]):
        broadcast_emergency(text)
    for username in mentioned:
        target_uid = next((u for u, data in warga_database.items() if data.get('username') == username), None)
        if target_uid:
            try: bot.send_message(target_uid, f"⚠️ *Warning*: Anda di-tag oleh {warga_database[uid]['name']} dalam laporan: '{text}'")
            except: pass

    # 4. Notif Admin (Format Screenshot_20260528-042346.jpg)
    if not is_admin(uid) and any(k in text.lower() for k in ["parkir", "lapor", "ganggu"]):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Japri Warga", url=f"tg://user?id={uid}"))
        bot.send_message(ADMIN_ID, f"🚨 *Laporan Warga*:\n{warga_database[uid]['name']} ({uid})\nIsi: {text}", reply_markup=markup)

    # 5. AI dengan History
    is_tag = f"@{bot.get_me().username}" in text or message.reply_to_message
    if is_admin(uid) or is_tag or any(k in text.lower() for k in ["parkir", "lapor"]):
        if uid not in chat_history: chat_history[uid] = []
        chat_history[uid].append({"role": "user", "content": text})
        if len(chat_history[uid]) > 5: chat_history[uid].pop(0)
        

        # prompt system
        system_prompt = """
        Anda adalah asisten cerdas untuk Smart RT. 
        Tugas Anda:
        1. Jawab dengan gaya bahasa gaul, sopan, dan solutif (seperti warga lokal).
        2. Jangan pernah mengarang jawaban (halu) tentang masalah keamanan atau kebakaran.
        3. Fokus pada urusan lingkungan RT, iuran warga, dan informasi jadwal kerja bakti.
        4. Jika tidak tahu, sarankan warga untuk menghubungi Pak RT.
        5. Kas RT saat ini: """ + str(kas_rt['total']) + """
        6. Anda memiliki akses pengetahuan luas. Untuk topik sensitif/kriminalitas (pembunuhan/kematian), berikan informasi umum lalu arahkan warga ke pihak berwenang (Polisi/RS).
        7. Jika terjadi kondisi DARURAT (Kemalingan/Kebakaran), anda WAJIB mengirimkan pesan peringatan ke seluruh warga di database.
        """
        res = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}] + chat_history[uid], 
            model="llama-3.3-70b-versatile"
        )
        ans = res.choices[0].message.content
        chat_history[uid].append({"role": "assistant", "content": ans})
        bot.reply_to(message, ans)

# HANDLER IURAN
def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Nominal?")
    elif state == "WAITING_AMOUNT":
        user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': message.text}
        bot.reply_to(message, "Kirim foto bukti:")
    elif state == "WAITING_PHOTO" and message.photo:
        pending_approvals[uid] = {'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah']}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"))
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"Iuran: {user_states[uid]['nama']} - Rp {user_states[uid]['jumlah']}", reply_markup=markup)
        bot.reply_to(message, "Laporan terkirim!")
        del user_states[uid]

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    if action == "approve":
        kas_rt["total"] += int(pending_approvals[uid]['jumlah'])
        bot.send_message(uid, f"✅ Lunas! Kas RT: Rp {kas_rt['total']:,}")
    bot.edit_message_caption(f"Status: {action.upper()}", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
