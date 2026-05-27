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

# 2. DATABASE & MEMORY
kas_rt = {"total": 0}
warga_database = {} 
user_states = {} 
pending_approvals = {}
chat_history = {} # Biar AI gak pelupa

def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

# 3. HANDLER UTAMA
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = message.from_user.first_name
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga! Sistem siap membantu.", parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or (message.caption if message.caption else "")
    warga_database[uid] = message.from_user.first_name
    
    # State Machine Iuran
    if uid in user_states:
        handle_lapor_steps(message)
        return

    # Logika Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Masukkan nama lengkap:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: Rp {kas_rt['total']:,}")
        return

    # Warranty System (Tag warga)
    mentioned = re.findall(r'@(\w+)', text)
    for username in mentioned:
        target_uid = next((k for k, v in warga_database.items() if v == username), None)
        if target_uid:
            try: bot.send_message(target_uid, f"⚠️ *Warning*: Anda dilaporkan {warga_database[uid]} terkait: {text}")
            except: pass

    # Notif Admin (Format Rapi)
    if not is_admin(uid) and any(k in text.lower() for k in ["parkir", "lapor", "ganggu"]):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Japri Warga", url=f"tg://user?id={uid}"))
        bot.send_message(ADMIN_ID, f"🚨 *Laporan Warga*:\n{warga_database[uid]} ({uid})\nIsi: {text}", reply_markup=markup)

    # AI Response dengan Memory
    if is_admin(uid) or f"@{bot.get_me().username}" in text or message.reply_to_message:
        if uid not in chat_history: chat_history[uid] = []
        chat_history[uid].append({"role": "user", "content": text})
        if len(chat_history[uid]) > 5: chat_history[uid].pop(0)

        prompt = "Anda asisten RT Smart. Jawab gaul, sopan, solutif, dilarang halu. Kas RT saat ini: " + str(kas_rt['total'])
        res = client.chat.completions.create(messages=[{"role": "system", "content": prompt}] + chat_history[uid], model="llama-3.3-70b-versatile")
        ans = res.choices[0].message.content
        chat_history[uid].append({"role": "assistant", "content": ans})
        bot.reply_to(message, ans)

# 4. STATE MACHINE & APPROVAL
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
