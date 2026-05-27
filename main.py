import os
import telebot
from telebot import types
from groq import Groq
import re

# 1. KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# DATABASE & STATE
kas_rt = {"total": 0}
warga_database = {} 
user_states = {} 
pending_approvals = {}

def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

# 2. START
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = message.from_user.first_name
    if message.from_user.username: warga_database[message.from_user.username] = uid
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga!", parse_mode='Markdown', reply_markup=markup)

# 3. HANDLER IURAN (STATE MACHINE + AUTO CALCULATE)
def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Masukkan nominal:")
    elif state == "WAITING_AMOUNT":
        try:
            jumlah = int(message.text)
            user_states[uid] = {'state': 'WAITING_CATEGORY', 'nama': user_states[uid]['nama'], 'jumlah': jumlah}
            bot.reply_to(message, "Pilih kategori (Iuran Bulanan/Kebersihan/Kematian):")
        except: bot.reply_to(message, "Harus angka!")
    elif state == "WAITING_CATEGORY":
        user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah'], 'kategori': message.text}
        bot.reply_to(message, "Kirim foto bukti transfer:")
    elif state == "WAITING_PHOTO" and message.photo:
        photo_id = message.photo[-1].file_id
        pending_approvals[uid] = {'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah'], 'photo': photo_id}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
        bot.send_photo(ADMIN_ID, photo_id, caption=f"🚨 *Laporan Iuran Baru*\nDari: {warga_database[uid]}\nJumlah: Rp {user_states[uid]['jumlah']}", reply_markup=markup)
        bot.reply_to(message, "Laporan terkirim ke Pak RT!")
        del user_states[uid]

# 4. HANDLER UTAMA (GROUP & TAG LOGIC)
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or (message.caption if message.caption else "")
    warga_database[uid] = message.from_user.first_name
    
    if uid in user_states:
        handle_lapor_steps(message)
        return
        
    # MENU
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Masukkan nama lengkap:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: Rp {kas_rt['total']:,}")
        return

    # WARRANTY SYSTEM (Tag warga = warning)
    mentioned = re.findall(r'@(\w+)', text)
    for username in mentioned:
        target_uid = warga_database.get(username)
        if target_uid:
            try: bot.send_message(target_uid, f"⚠️ *Warning*: Anda dilaporkan oleh {warga_database[uid]}!")
            except: pass

    # NOTIF ADMIN (Format Screenshot)
    if not is_admin(uid) and any(k in text.lower() for k in ["parkir", "lapor", "masalah"]):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Japri Warga", url=f"tg://user?id={uid}"))
        bot.send_message(ADMIN_ID, f"🚨 *Laporan Warga*:\n{warga_database[uid]} ({uid})\nIsi: {text}", reply_markup=markup)

    # AI FILTER
    is_tag = f"@{bot.get_me().username}" in text or message.reply_to_message
    if is_admin(uid) or is_tag or any(k in text.lower() for k in ["parkir", "lapor"]):
        try:
            res = client.chat.completions.create(messages=[{"role": "system", "content": "Asisten RT ramah."}, {"role": "user", "content": text}], model="llama-3.3-70b-versatile")
            bot.reply_to(message, res.choices[0].message.content)
        except: pass

# 5. APPROVAL (AUTO CALCULATE)
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    if action == "approve":
        kas_rt["total"] += int(pending_approvals[uid]['jumlah'])
        bot.send_message(uid, f"✅ Lunas! Kas RT: Rp {kas_rt['total']:,}")
    bot.edit_message_caption(f"Status: {action.upper()}", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
