import os
import re
import telebot
import datetime
import pytz

from telebot import types
from groq import Groq

# =========================================
# CONFIG
# =========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# =========================================
# DATABASE
# =========================================
kas_rt = {
    "total": 0,
    "Kebersihan": 0,
    "Keamanan": 0,
    "Lain-lain": 0
}
warga_database = {}
user_states = {}
pending_approvals = {}
chat_history = {}
spam_counter = {}
muted_users = set()

# =========================================
# HELPER
# =========================================
def get_role(uid):
    return "Pak RT" if str(uid) == ADMIN_ID else "Warga"

def get_greeting():
    wib = pytz.timezone("Asia/Jakarta")
    hour = datetime.datetime.now(wib).hour
    if 5 <= hour < 12: return "Pagi"
    if 12 <= hour < 15: return "Siang"
    if 15 <= hour < 18: return "Sore"
    return "Malam"

def is_bot_target(message):
    if message.chat.type == "private": return True
    if message.reply_to_message and message.reply_to_message.from_user.is_bot: return True
    if message.text and f"@{bot.get_me().username}" in message.text: return True
    return False

def broadcast_message(text):
    for uid in warga_database:
        try: bot.send_message(uid, f"📢 Pengumuman RT\n\n{text}")
        except: pass

# =========================================
# HANDLER UTAMA
# =========================================
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = {
        "name": message.from_user.first_name,
        "username": message.from_user.username
    }
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas")
    bot.reply_to(message, f"Selamat {get_greeting()} \n\nSmart RT siap bantu.", reply_markup=markup)

@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    role = get_role(uid)
    text = message.text or message.caption or ""

    # Redirect ke flow iuran jika user ada di state
    if uid in user_states:
        handle_iuran(message)
        return

    # Admin Features
    if role == "Pak RT":
        if text.startswith("/bc "):
            broadcast_message(text.replace("/bc ", ""))
            bot.reply_to(message, "✅ Broadcast terkirim.")
            return
        if text.startswith("/mute "):
            target = text.split(" ")[1].replace("@", "")
            muted_users.add(target)
            bot.reply_to(message, f"✅ @{target} dimute.")
            return

    # Anti Spam
    if uid in muted_users: return
    spam_counter[uid] = spam_counter.get(uid, 0) + 1
    if spam_counter[uid] > 10:
        muted_users.add(uid)
        bot.reply_to(message, "🚫 Lu kena mute gara gara spam")
        return

    # Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {"state": "WAITING_NAME"}
        bot.reply_to(message, "Masukin nama lengkap:")
        return
    elif text == "📋 Cek Kas":
        # Menampilkan rincian saldo per kategori secara spesifik
        detail_kas = (f"💰 Rincian Kas RT:\n"
                      f"--------------------------\n"
                      f"Kebersihan: Rp {kas_rt['Kebersihan']:,}\n"
                      f"Keamanan:   Rp {kas_rt['Keamanan']:,}\n"
                      f"Lain-lain:  Rp {kas_rt['Lain-lain']:,}\n"
                      f"--------------------------\n"
                      f"TOTAL:      Rp {kas_rt['total']:,}")
        bot.reply_to(message, detail_kas)
        return

    # Lapor Warga Bermasalah
    if "lapor" in text.lower() or "parkir" in text.lower():
        mentioned = re.findall(r'@(\w+)', text)
        for username in mentioned:
            target_uid = next((u for u, data in warga_database.items() if data.get("username", "").lower() == username.lower()), None)
            if target_uid:
                try:
                    bot.send_message(target_uid, f"⚠️ Ada laporan warga terkait lu:\n\n{text}")
                    bot.reply_to(message, f"✅ Laporan ke @{username} sudah dikirim.")
                except:
                    bot.reply_to(message, f"❌ Gagal kirim ke @{username}.")
            else:
                bot.reply_to(message, f"❌ User @{username} tidak ditemukan.")

    # AI Chat
    if is_bot_target(message):
        chat_history.setdefault(uid, []).append({"role": "user", "content": text})
        system_prompt = f"""Lu adalah asisten bot Smart RT.
Tugas lu: jawab pertanyaan warga/Pak RT dengan tegas, faktual, dan singkat.
Aturan:
- JANGAN flirty, JANGAN sok asik, JANGAN basa-basi.
- Kalau diajak ngobrol santai, balas singkat kayak teman tongkrongan.
- Kalau user adalah ADMIN_ID (Pak RT), perlakukan sebagai Pak RT.
- Tidak perlu nanya 'ada lagi yang dibantu?'.
- Gunakan emoji seperlunya (🙏, 😂, 😭, 😡, 😞, ⚠️, ❌, 🆘).
- Jika info ilmiah, berikan jawaban singkat + referensi.
- Jaga jarak profesional (bukan CS).

User: {warga_database.get(uid, {}).get('name', 'Warga')} ({role})
Kas RT: Rp {kas_rt['total']:,}"""
        max_tokens = 250 if "coding" in text.lower() else (200 if "jelaskan" in text.lower() else (150 if len(text) > 100 else 80))
        try:
            res = client.chat.completions.create(model="llama-3.1-8b-instant", temperature=0.7, max_tokens=max_tokens, messages=[{"role": "system", "content": system_prompt}, *chat_history[uid]])
            ans = res.choices[0].message.content
            chat_history[uid].append({"role": "assistant", "content": ans})
            bot.reply_to(message, ans)
        except Exception as e:
            bot.reply_to(message, f"Error: {str(e)}")

# =========================================
# FLOW IURAN (DIPERBAIKI)
# =========================================
def handle_iuran(message):
    uid = str(message.from_user.id)
    state_data = user_states[uid]
    state = state_data["state"]

    if state == "WAITING_NAME":
        state_data["nama"] = message.text
        state_data["state"] = "WAITING_CATEGORY"
        bot.reply_to(message, "Pilih kategori:\n1. Kebersihan\n2. Keamanan\n3. Lain-lain")
    elif state == "WAITING_CATEGORY":
        cat_map = {"1": "Kebersihan", "2": "Keamanan", "3": "Lain-lain"}
        if message.text in cat_map:
            state_data["kategori"] = cat_map[message.text]
            state_data["state"] = "WAITING_DESC" if message.text == "3" else "WAITING_AMOUNT"
            bot.reply_to(message, "Masukin keterangan:" if message.text == "3" else "Masukin nominal:")
        else: bot.reply_to(message, "Pilih 1, 2, atau 3.")
    elif state == "WAITING_DESC":
        state_data["keterangan"] = message.text
        state_data["state"] = "WAITING_AMOUNT"
        bot.reply_to(message, "Masukin nominal iuran:")
    elif state == "WAITING_AMOUNT":
        raw = re.sub(r'\D', '', message.text)
        if raw.isdigit() and int(raw) >= 10000:
            state_data["jumlah"] = int(raw)
            state_data["state"] = "WAITING_PHOTO"
            bot.reply_to(message, "Kirim foto bukti transfer:")
        else: bot.reply_to(message, "⚠️ Minimal Rp10.000")
    elif state == "WAITING_PHOTO":
        if message.photo:
            pending_approvals[uid] = state_data
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"),
                       types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
            ket = f"\nKet: {state_data.get('keterangan', '-')}"
            bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💰 Laporan Iuran\nNama: {state_data['nama']}\nNominal: Rp {state_data['jumlah']:,}{ket}", reply_markup=markup)
            bot.reply_to(message, "✅ Laporan terkirim ke Pak RT.")
            del user_states[uid]
        else: bot.reply_to(message, "Kirim foto bukti transfer.")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    parts = call.data.split("_")
    action, uid = parts[0], parts[1]
    
    if uid in pending_approvals:
        data = pending_approvals[uid]
        nama = data.get("nama")
        kategori = data.get("kategori")
        jumlah = data.get("jumlah")
        
        if action == "approve":
            # Update saldo spesifik kategori & total
            kas_rt[kategori] += jumlah
            kas_rt["total"] += jumlah
            
            bot.send_message(uid, f"✅ Iuran disetujui, terimakasih {nama} atas pembayaran {kategori} sebesar Rp {jumlah:,}")
            bot.edit_message_caption(
                caption=f"✅ Iuran disetujui.\nKategori: {kategori}\nJumlah: Rp {jumlah:,}\n\nTotal Kas RT: Rp {kas_rt['total']:,}", 
                chat_id=call.message.chat.id, message_id=call.message.message_id
            )
        else:
            bot.send_message(uid, "❌ Iuran ditolak.")
            bot.edit_message_caption(caption="❌ Iuran ditolak", chat_id=call.message.chat.id, message_id=call.message.message_id)
        
        del pending_approvals[uid]
print("Bot Smart RT nyala...")
bot.infinity_polling()
