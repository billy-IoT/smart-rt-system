import os
import telebot
from telebot import types
from groq import Groq

# 1. KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

data = {"kas": 0, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}
warga_database = {} 

def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

@bot.message_handler(commands=['start'])
def start(message):
    warga_database[str(message.from_user.id)] = message.from_user.first_name
    bot.reply_to(message, "🏠 *Smart RT* - Halo Warga! Ada yang bisa dibantu?", parse_mode='Markdown')

@bot.message_handler(content_types=['text', 'photo', 'document'])
def main_handler(message):
    uid = str(message.from_user.id)
    warga_database[uid] = message.from_user.first_name
    
    if uid in user_states:
        handle_lapor_steps(message)
        return

    text = message.text if message.text else ""
    keywords = ["parkir", "ganggu", "lapor", "masalah", "tolong"]
    
    # 1. LOGIKA PERINGATAN OTOMATIS KE WARGA
    if any(k in text.lower() for k in keywords) and not is_admin(uid):
        # Tegur warga langsung
        try:
            bot.send_message(uid, "⚠️ *Peringatan Otomatis*:\nLaporan Anda mengenai masalah lingkungan sudah diterima. Mohon kerjasamanya agar tidak mengganggu warga lain ya.")
        except: pass
        # Notifikasi ke Pak RT
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Japri Warga", url=f"tg://user?id={uid}"))
        bot.send_message(ADMIN_ID, f"🚨 *Laporan Warga*:\n{warga_database[uid]} ({uid})\nIsi: {text}", reply_markup=markup)

    # 2. AI RESPONSE
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Masukkan nama lengkap:")
        return
    
    try:
        res = client.chat.completions.create(
            messages=[{"role": "system", "content": "Anda asisten RT. Jawab ramah. Kas RT: 5jt."}, {"role": "user", "content": text}],
            model="llama-3.3-70b-versatile"
        )
        bot.reply_to(message, res.choices[0].message.content)
    except: pass

def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Masukkan nominal iuran:")
    elif state == "WAITING_AMOUNT":
        try:
            user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': int(message.text)}
            bot.reply_to(message, "Kirim foto bukti transfer:")
        except: bot.reply_to(message, "Harus angka!")
    elif state == "WAITING_PHOTO":
        photo_id = message.photo[-1].file_id if message.photo else None
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
        bot.send_photo(ADMIN_ID, photo_id, caption=f"🚨 *Iuran Baru*: {user_states[uid]['nama']} - Rp {user_states[uid]['jumlah']}", reply_markup=markup)
        bot.reply_to(message, "Laporan terkirim!")
        del user_states[uid]

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    bot.send_message(uid, f"Status laporan Anda: {action.upper()}")
    bot.edit_message_caption(f"Status: {action.upper()}", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
