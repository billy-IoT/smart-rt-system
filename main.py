import os
import telebot
from telebot import types
from groq import Groq
import re
import datetime
import pytz 

# --- KONFIGURASI ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") 
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE ---
kas_rt = {"total": 0} 
warga_database = {} 
user_states = {} 
pending_approvals = {}
chat_history = {}
muted_users = set()  
spam_counter = {}    

# --- FUNGSI BANTU ---
def get_role(uid): return "Pak RT" if str(uid) == str(ADMIN_ID) else "Warga"

def get_greeting():
    wib = pytz.timezone('Asia/Jakarta')
    hour = datetime.datetime.now(wib).hour
    if 5 <= hour < 12: return "Selamat Pagi"
    elif 12 <= hour < 15: return "Selamat Siang"
    elif 15 <= hour < 19: return "Selamat Sore"
    else: return "Selamat Malam"

def is_bot_target(message):
    uid = str(message.from_user.id)
    if get_role(uid) == "Pak RT": return True
    if message.chat.type == 'private': return True
    if message.reply_to_message and message.reply_to_message.from_user.is_bot: return True
    if message.text and f"@{bot.get_me().username}" in message.text: return True
    return False

def broadcast_message(message_text):
    for uid in warga_database:
        try:
            bot.send_message(uid, f"📢 Pengumuman RT:\n\n{message_text}")
        except: continue

# --- COMMAND START ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = {'name': message.from_user.first_name, 'username': message.from_user.username}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, f"{get_greeting()}! Selamat datang di Smart RT. Gunakan menu di bawah ya:", reply_markup=markup)

# --- HANDLER UTAMA ---
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    text = message.text or (message.caption if message.caption else "")
    role = get_role(uid)
    
    # Prioritas: State Machine Iuran
    if uid in user_states:
        handle_lapor_steps(message)
        return

    # 1. Fitur Admin
    if role == "Pak RT":
        if text.startswith("/bc "):
            broadcast_message(text.replace("/bc ", ""))
            bot.reply_to(message, "✅ Pesan disiarkan ke warga.")
            return
        if text.startswith("/mute "):
            target = text.split(" ")[1].replace("@", "")
            muted_users.add(target)
            bot.reply_to(message, f"✅ User {target} dimute.")
            return

    # 2. Anti Spam
    if uid in muted_users: return
    spam_counter[uid] = spam_counter.get(uid, 0) + 1
    if spam_counter[uid] > 10:
        muted_users.add(uid)
        bot.reply_to(message, "🚫 Anda di-mute karena spam.")
        return

    # 3. Logika Laporan (Private Warning)
    if "lapor" in text.lower() or "parkir" in text.lower():
        mentioned = re.findall(r'@(\w+)', text)
        for username in mentioned:
            target_uid = next((u for u, data in warga_database.items() if data.get('username') == username), None)
            if target_uid:
                try:
                    bot.send_message(target_uid, f"⚠️ Notifikasi Laporan: Anda dilaporkan oleh {warga_database[uid]['name']} terkait: '{text}'.")
                    bot.reply_to(message, f"✅ Laporan terhadap @{username} telah diteruskan secara privat.")
                except: bot.reply_to(message, f"❌ Gagal kirim japri ke @{username}.")

    # 4. Menu Utama
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Masukkan nama lengkap Anda:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"{get_greeting()}! Kas RT saat ini: Rp {kas_rt['total']:,}")
        return

    # 5. AI Processor
    if is_bot_target(message):
        if uid not in chat_history: chat_history[uid] = []
        chat_history[uid].append({"role": "user", "content": text})
        system_prompt = f"""Anda adalah Smart RT Assistant. Persona: Profesional, ramah, tegas, solutif.
        Format Jawaban (WAJIB): 1. Tanpa Markdown/bold. 2. Pakai penomoran 1, 2, 3. 3. Jangan mengulang pesan di akhir.
        Identitas: {role} {warga_database.get(uid, {}).get('name', 'Warga')}. Kas RT: Rp {kas_rt['total']:,}."""
        res = client.chat.completions.create(messages=[{"role": "system", "content": system_prompt}] + chat_history[uid][-5:], model="llama-3.3-70b-versatile")
        bot.reply_to(message, res.choices[0].message.content)

# --- HANDLER IURAN & KATEGORI ---
def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        warga_database[uid]['name'] = message.text
        user_states[uid] = {'state': 'WAITING_CATEGORY', 'nama': message.text}
        bot.reply_to(message, "Pilih kategori:\n1. Kebersihan\n2. Keamanan\n3. Lain-lain\nKetik angkanya:")
        
    elif state == "WAITING_CATEGORY":
        cat_map = {"1": "Kebersihan", "2": "Keamanan", "3": "Lain-lain"}
        if message.text in cat_map:
            user_states[uid].update({'state': 'WAITING_DESC' if message.text == "3" else 'WAITING_AMOUNT', 'kategori': cat_map[message.text]})
            if message.text == "3": bot.reply_to(message, "Masukkan keterangan iuran:")
            else: bot.reply_to(message, "Masukkan nominal iuran (minimal 10.000):")
        else: bot.reply_to(message, "Pilih 1, 2, atau 3.")

    elif state == "WAITING_DESC":
        user_states[uid].update({'state': 'WAITING_AMOUNT', 'keterangan': message.text})
        bot.reply_to(message, "Masukkan nominal iuran (minimal 10.000):")

    elif state == "WAITING_AMOUNT":
        raw = re.sub(r'\D', '', message.text)
        if raw.isdigit() and int(raw) >= 10000:
            user_states[uid].update({'state': 'WAITING_PHOTO', 'jumlah': int(raw)})
            bot.reply_to(message, "Kirim foto bukti iuran:")
        else: bot.reply_to(message, "⚠️ Nominal minimal Rp 10.000, masukkan angka saja.")

    elif state == "WAITING_PHOTO":
        if message.photo:
            data = user_states[uid]
            pending_approvals[uid] = data
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
            ket = f"\nKeterangan: {data.get('keterangan')}" if 'keterangan' in data else ""
            bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"Iuran {data['kategori']}\nDari: {data['nama']}\nNominal: Rp {data['jumlah']:,}{ket}", reply_markup=markup)
            bot.reply_to(message, "Laporan terkirim ke Pak RT!")
            del user_states[uid]
        else:
            bot.reply_to(message, "⚠️ Harap kirimkan foto bukti iuran.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    action, uid = call.data.split("_")
    if action == "approve":
        kas_rt["total"] += pending_approvals[uid]['jumlah']
        bot.send_message(uid, f"✅ Iuran diterima! Kas RT kini: Rp {kas_rt['total']:,}")
        bot.edit_message_caption(f"Status: ✅ DISETUJUI", call.message.chat.id, call.message.message_id)
    elif action == "reject":
        bot.send_message(uid, "❌ Iuran ditolak.")
        bot.edit_message_caption(f"Status: ❌ DITOLAK", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
