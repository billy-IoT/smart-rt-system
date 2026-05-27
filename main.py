import os
import telebot
from telebot import types
from groq import Groq

# 1. Konfigurasi
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

data = {"kas": 0, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 2. Main Menu (Keyboard Bawah)
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga!", parse_mode='Markdown', reply_markup=markup)

# 3. Handler Utama (Logic State dipisah biar gak keder)
@bot.message_handler(func=lambda message: True)
def main_handler(message):
    uid = message.from_user.id
    text = message.text

    # A. Pengecekan State (Ini harus jalan duluan!)
    if uid in user_states:
        handle_lapor_steps(message)
        return # STOP di sini, jangan lanjut ke AI!

    # B. Routing Menu (Kalau bukan state, cek menu)
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Siap! Siapa nama kamu?")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas: {data['kas']}\n🅿️ Status Parkir: {data['parkir']}")
        return

    # C. Baru deh AI (Hanya kalau gak lagi lapor & bukan menu)
    try:
        persona = "Pak RT" if is_admin(uid) else "Warga"
        prompt = f"Anda asisten nya pak RT. Bicara dengan {persona}. Gaya bicara: gaul/santai/sopan tergantung warganya gimana kalo bapak bapak/ibu ibu lebih formal dan sopan sememtara kalo remaja gen z gaul ala tongkrongan tapi sopan."
        res = client.chat.completions.create(messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}], model="llama-3.3-70b-versatile")
        bot.reply_to(message, res.choices[0].message.content)
    except: pass

# 4. Fungsi Lapor yang Bener (State Machine)
def handle_lapor_steps(message):
    uid = message.from_user.id
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, f"Halo {message.text}! Sekarang masukin nominalnya (angka aja):")
        
    elif state == "WAITING_AMOUNT":
        try:
            jumlah = int(message.text)
            user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': jumlah}
            bot.reply_to(message, "Mantap. Sekarang kirim bukti fotonya:")
        except: bot.reply_to(message, "Masukin angka yang bener woi!")
        
    elif state == "WAITING_PHOTO":
        if message.photo:
            # Selesai, simpan & kirim ke admin
            bot.reply_to(message, "Bukti diterima! Tunggu Pak RT approve ya.")
            # ... (Logic kirim ke admin sama kayak sebelumnya)
            del user_states[uid]
        else:
            bot.reply_to(message, "Mana fotonya? Harus kirim foto bukti bayar!")

bot.infinity_polling()
