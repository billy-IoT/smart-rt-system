import os
import telebot
from telebot import types
from groq import Groq

# 1. Konfigurasi
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# State Management (Temporary in-memory)
user_states = {} # Buat nyimpen status warga pas lagi lapor kas
pending_approvals = {} # Buat nyimpen list iuran yg nunggu approve Pa Rete

data = {"kas": 0, "parkir": "🟢 Buka"}

# 2. Main Menu
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💰 Lapor Iuran Kas", callback_data="lapor_kas"))
    markup.add(types.InlineKeyboardButton("📋 Cek Kas & Status", callback_data="info"))
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Selamat Datang Warga!", parse_mode='Markdown', reply_markup=markup)

# 3. Callback Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "lapor_kas":
        user_states[call.from_user.id] = "WAITING_NAME"
        bot.send_message(call.message.chat.id, "Oke, tulis Nama kamu:")
    elif call.data == "info":
        bot.send_message(call.message.chat.id, f"💰 Kas: Rp {data['kas']}\n🅿️ Parkir: {data['parkir']}")
    elif call.data.startswith("approve_"):
        lapor_id = call.data.split("_")[1]
        if lapor_id in pending_approvals:
            item = pending_approvals[lapor_id]
            data['kas'] += item['jumlah']
            bot.send_message(ADMIN_ID, f"✅ Iuran {item['nama']} sebesar {item['jumlah']} berhasil disetujui!")
            del pending_approvals[lapor_id]

# 4. State Machine (Input Warga)
@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def process_input(message):
    uid = message.from_user.id
    state = user_states[uid]
    
    if state == "WAITING_NAME":
        user_states[uid] = {"nama": message.text, "state": "WAITING_AMOUNT"}
        bot.reply_to(message, "Mantap. Sekarang masukkan jumlah uangnya (angka saja):")
    
    elif isinstance(user_states[uid], dict) and user_states[uid]["state"] == "WAITING_AMOUNT":
        try:
            nama = user_states[uid]["nama"]
            jumlah = int(message.text)
            lapor_id = str(uid)
            pending_approvals[lapor_id] = {"nama": nama, "jumlah": jumlah}
            
            # Kirim ke Pak RT untuk di-approve
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{lapor_id}"))
            bot.send_message(ADMIN_ID, f"🚨 *Laporan Iuran Baru*\nDari: {nama}\nJumlah: {jumlah}", parse_mode='Markdown', reply_markup=markup)
            
            bot.reply_to(message, "Laporan iuran sudah dikirim ke Pak RT, tunggu approval ya!")
            del user_states[uid]
        except:
            bot.reply_to(message, "Masukin angka yang bener woi!")

# 5. Handler AI
@bot.message_handler(func=lambda message: True)
def reply(message):
    # (Biarkan handler AI tetap jalan buat ngobrol santai)
    pass 

print("Bot Smart RT Finance Mode Active! 😹")
bot.infinity_polling()
