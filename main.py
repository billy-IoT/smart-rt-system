import os
import telebot
from telebot import types
from groq import Groq

# 1. Konfigurasi
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

data = {"kas": 5000000, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 2. MENU UTAMA (Tombol di bawah keyboard)
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🏠 *Smart RT Dashboard*\n\nSelamat datang Warga! Gunakan menu di bawah ya:", 
                 parse_mode='Markdown', reply_markup=main_menu())

# 3. HANDLER UTAMA (Menu + AI)
@bot.message_handler(func=lambda message: True)
def main_handler(message):
    uid = message.from_user.id
    text = message.text

    # A. Routing Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Sip! Masukin nama kamu:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: *{data['kas']}*\n🅿️ Parkir: *{data['parkir']}*", parse_mode='Markdown')
        return

    # B. State Machine (Lapor Iuran)
    if uid in user_states:
        # ... (Logika State Waiting_Name, Amount, Photo yang tadi) ...
        # [Kodingan state machine tetap sama seperti sebelumnya]
        return

    # C. AI Response (Savage Mode)
    try:
        persona = "Pak RT" if is_admin(uid) else "Warga"
        prompt = f"Anda asisten RT. Bicara dengan {persona}. Kas RT: {data['kas']}. Gaya bicara: gaul/santai."
        res = client.chat.completions.create(messages=[{"role": "system", "content": prompt}, {"role": "user", "content": message.text}], model="llama-3.3-70b-versatile")
        bot.reply_to(message, res.choices[0].message.content)
    except: pass

bot.infinity_polling()
