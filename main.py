import os
import telebot
from telebot import types
from groq import Groq

# 1. KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # ID Telegram lu
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# DATA
data = {"kas": 0, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}
warga_database = {} 

# FUNGSI IDENTITAS
def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

# 2. START
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = message.from_user.first_name
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga! Ada yang bisa dibantu?", parse_mode='Markdown', reply_markup=markup)

# 3. HANDLER UTAMA (LOGIKA IDENTITY & AI)
@bot.message_handler(content_types=['text', 'photo', 'document'])
def main_handler(message):
    uid = str(message.from_user.id)
    warga_database[uid] = message.from_user.first_name
    
    # State Machine Lapor
    if uid in user_states:
        handle_lapor_steps(message)
        return

    text = message.text if message.text else ""
    is_tag = f"@{bot.get_me().username}" in text or message.reply_to_message
    
    # Filter Cerdas: Warga cuma dibalas kalau penting/di-tag, Pak RT bebas curhat
    keywords = ["parkir", "iuran", "lapor", "masalah", "tolong"]
    if not is_admin(uid) and not is_tag and not any(k in text.lower() for k in keywords):
        return

    # Routing Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Siap! Masukkan nama lengkap Anda:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: *{data['kas']}*\n🅿️ Parkir: *{data['parkir']}*", parse_mode='Markdown')
        return

    # AI RESPONSE (Identity Aware)
    try:
        persona = "Pak RT" if is_admin(uid) else "Warga"
        system_prompt = f"""
        Anda asisten Smart RT. 
        User saat ini: {persona}. 
        Gaya bahasa: Gaul, sopan, solutif.
        Aturan: Jangan halu kebakaran, jawab fokus lingkungan RT. Kas RT: {data['kas']}.
        """
        res = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], 
            model="llama-3.3-70b-versatile"
        )
        jawaban = res.choices[0].message.content
        bot.reply_to(message, jawaban)

        # FORWARD LAPORAN KE PAK RT
        if any(k in text.lower() for k in keywords) and not is_admin(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💬 Japri Warga Ini", url=f"tg://user?id={uid}"))
            bot.send_message(ADMIN_ID, f"🚨 *Laporan {persona}*:\nDari: {warga_database[uid]}\nID: {uid}\nIsi: {text}", reply_markup=markup)
    except: pass

# 4. STATE MACHINE (Iuran)
def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Masukkan nominal iuran (angka saja):")
    elif state == "WAITING_AMOUNT":
        try:
            jumlah = int(message.text)
            user_states[uid] = {'state': 'WAITING_CATEGORY', 'nama': user_states[uid]['nama'], 'jumlah': jumlah}
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.row("Iuran Bulanan", "Dana Kematian", "Dana Kebersihan")
            bot.reply_to(message, "Pilih kategori:", reply_markup=markup)
        except: bot.reply_to(message, "Input harus angka!")
    elif state == "WAITING_CATEGORY":
        user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah'], 'kategori': message.text}
        bot.reply_to(message, "Kirim foto bukti transfernya:")
    elif state == "WAITING_PHOTO":
        photo_id = message.photo[-1].file_id if message.photo else None
        if not photo_id: return bot.reply_to(message, "Kirim fotonya dulu!")
        pending_approvals[uid] = {'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah'], 'kategori': user_states[uid]['kategori'], 'photo': photo_id}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
        bot.send_photo(ADMIN_ID, photo_id, caption=f"🚨 *Laporan Iuran*\nDari: {warga_database[uid]}\nJumlah: {pending_approvals[uid]['jumlah']}", reply_markup=markup)
        bot.reply_to(message, "Laporan terkirim ke Pak RT!")
        del user_states[uid]

# 5. APPROVAL (Admin Only)
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if not is_admin(call.from_user.id): return
    action, uid = call.data.split("_")
    if uid in pending_approvals:
        item = pending_approvals.pop(uid)
        if action == "approve":
            data['kas'] += item['jumlah']
            bot.send_message(uid, "✅ Lunas! Laporan iuran diterima.")
            bot.edit_message_caption(f"✅ Disetujui: {item['nama']}", call.message.chat.id, call.message.message_id)
        else:
            bot.send_message(uid, "❌ Maaf, laporan ditolak.")
            bot.edit_message_caption(f"❌ Ditolak: {item['nama']}", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
