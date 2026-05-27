import os
import telebot
from telebot import types
from groq import Groq

# 1. Konfigurasi
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # ID Telegram lu
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# Data RT
data = {"kas": 0, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}

# 2. Helper Fungsi: Bedain Admin vs Warga
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 3. Main Menu
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💰 Lapor Iuran Kas", callback_data="lapor_kas"))
    markup.add(types.InlineKeyboardButton("📋 Info RT", callback_data="info"))
    bot.reply_to(message, "🏠 *Smart RT Dashboard*\n\nHalo! Mau apa hari ini?", parse_mode='Markdown', reply_markup=markup)

# 4. Handler AI & Chat
@bot.message_handler(func=lambda message: message.from_user.id not in user_states)
def reply(message):
    text = message.text.lower()
    user_id = message.from_user.id
    
    # --- A. Perintah Khusus Admin ---
    if is_admin(user_id):
        if text.startswith("set kas "):
            data['kas'] = text.replace("set kas ", "").strip()
            bot.reply_to(message, "✅ Kas diupdate!")
            return

    # --- B. AI Logic (The Savage AI) ---
    try:
        # Pembeda persona
        persona = "Pak RT (Admin)" if is_admin(user_id) else "Warga RT"
        system_prompt = (
            f"Lu adalah asisten RT gaul. Role lu sekarang lagi ngomong sama: {persona}. "
            f"Data RT: Kas {data['kas']}, Parkir {data['parkir']}. "
            f"Gaya bicara: Santai, lucu, ala pos ronda. "
            f"Penting: Kalau yang nanya {persona} adalah warga, layani dengan ramah. "
            f"Kalau dia nanya tugas e-Learning, bantu jawab tapi tetep sok asik."
        )

        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message.text}],
            model="llama-3.3-70b-versatile",
        )
        bot.reply_to(message, chat_completion.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"Sistem lagi error: {e}")

# 5. Handler Laporan Kas & Approval
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "lapor_kas":
        user_states[call.from_user.id] = {"state": "WAITING_NAME"}
        bot.send_message(call.message.chat.id, "Siap! Tulis Nama kamu:")
    elif call.data.startswith("approve_"):
        if not is_admin(call.from_user.id): return
        lapor_id = call.data.split("_")[1]
        item = pending_approvals.pop(lapor_id)
        bot.send_message(ADMIN_ID, f"✅ Approve {item['nama']}!")
    
# (Fungsi process_input buat state machine lanjutannya sama kaya kode sebelumnya)

print("Bot Smart RT Siap Tempur! 😹")
bot.infinity_polling()
