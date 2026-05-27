import os
import telebot
from telebot import types
from groq import Groq

# 1. Setup
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

data = {"kas": 5000000, "parkir": "🟢 Buka"}
user_states = {} # Simpan state warga: {'state': '...', 'nama': '...'}
pending_approvals = {}

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 2. Handler Utama (Pusat Kendali)
@bot.message_handler(func=lambda message: True)
def main_handler(message):
    user_id = message.from_user.id
    text = message.text.lower()

    # A. Kalau user lagi proses lapor kas (State Management)
    if user_id in user_states:
        handle_lapor_kas(message)
        return

    # B. Perintah Admin (Update Data)
    if is_admin(user_id):
        if text.startswith("set kas "):
            data['kas'] = text.replace("set kas ", "").strip()
            bot.reply_to(message, "✅ Kas diupdate!")
            return

    # C. Filter Grup (Anti Spam)
    if message.chat.type in ['group', 'supergroup']:
        if not (f"@{bot.get_me().username}" in message.text or 
               (message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id)):
            return

    # D. Logic AI (Savage & Cerdas)
    try:
        persona = "Pak RT (Admin)" if is_admin(user_id) else "Warga"
        system_prompt = (
            f"Anda asisten RT yang gaul dan lucu. Anda bicara dengan {persona}. "
            f"Data: Kas {data['kas']}, Parkir {data['parkir']}. "
            f"Jika warga bertanya tentang kas/parkir, jawab sesuai data. "
            f"Bantu warga dengan sopan tapi tetap santai."
        )
        
        response = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message.text}],
            model="llama-3.3-70b-versatile",
        )
        bot.reply_to(message, response.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"Aduh, AI-nya lagi macet: {e}")

# 3. Fungsi Lapor Kas (State Machine)
def handle_lapor_kas(message):
    uid = message.from_user.id
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Sip! Sekarang masukin jumlah iurannya (angka saja):")
    elif state == "WAITING_AMOUNT":
        try:
            jumlah = int(message.text)
            nama = user_states[uid]['nama']
            pending_approvals[str(uid)] = {'nama': nama, 'jumlah': jumlah}
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"))
            bot.send_message(ADMIN_ID, f"🚨 *Laporan Baru*\nNama: {nama}\nJumlah: {jumlah}", reply_markup=markup, parse_mode='Markdown')
            
            bot.reply_to(message, "Laporan udah dikirim ke Pak RT ya!")
            del user_states[uid]
        except:
            bot.reply_to(message, "Masukin angka yang bener woi!")

# 4. Callback Button
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "lapor_kas":
        user_states[call.from_user.id] = {'state': 'WAITING_NAME'}
        bot.send_message(call.message.chat.id, "Siap, sebutin nama kamu:")
    elif call.data.startswith("approve_"):
        uid = call.data.split("_")[1]
        if uid in pending_approvals:
            item = pending_approvals.pop(uid)
            data['kas'] = int(str(data['kas']).replace("Rp ", "").replace(".", "")) + item['jumlah']
            bot.send_message(call.message.chat.id, f"✅ Kas diupdate jadi {data['kas']}")

bot.infinity_polling()
