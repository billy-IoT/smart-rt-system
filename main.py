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

def broadcast_message(text, is_emergency=False):
    # Mengumpulkan semua user ID dari database
    users = list(warga_database.keys())
    
    if is_emergency:
        # Pesan darurat dengan mention semua orang (format Telegram)
        announcement = f"🚨🚨 DARURAT 🚨🚨\n\n{text}\n\nMohon perhatian seluruh warga!"
    else:
        announcement = f"📢 Pengumuman RT\n\n{text}"
        
    for uid in users:
        try: 
            bot.send_message(uid, announcement)
        except: 
            pass

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
            # 1. Pastikan hanya bisa mute jika di Group
            if message.chat.type == "private":
                bot.reply_to(message, "⚠️ Fitur mute hanya berlaku di grup.")
                return
            
            # 2. Ambil target
            target_username = text.split(" ")[1].replace("@", "")
            
            # 3. Cari target di database untuk mendapatkan UID
            target_uid = next((u for u, data in warga_database.items() if data.get("username", "").lower() == target_username.lower()), None)
            
            # 4. Pastikan Pak RT tidak bisa me-mute dirinya sendiri
            if str(target_uid) == ADMIN_ID:
                bot.reply_to(message, "❌ Tidak bisa me-mute diri sendiri.")
                return

            if target_uid:
                muted_users.add(target_uid) # Mute berdasarkan UID, bukan username
                bot.reply_to(message, f"✅ @{target_username} telah dimute di grup ini.")
            else:
                bot.reply_to(message, f"❌ User @{target_username} tidak ditemukan.")
            return

    # Anti Spam
    if uid in muted_users: return
    spam_counter[uid] = spam_counter.get(uid, 0) + 1
    if spam_counter[uid] > 10:
        muted_users.add(uid)
        bot.reply_to(message, "🚫 Lu kena mute gara gara spam kocak")
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

    # Di dalam main_handler:
    
    # Fitur Broadcast Darurat
    if text.lower().startswith("darurat "):
        if role == "Pak RT":
            msg = text.replace("darurat ", "")
            broadcast_message(msg, is_emergency=True)
            bot.reply_to(message, "✅ Pesan darurat telah disebar ke semua warga.")
        else:
            bot.reply_to(message, "❌ Hanya Pak RT yang bisa mengeluarkan perintah darurat.")
        return

    # Lapor Warga Bermasalah dengan AI
    if "lapor" in text.lower() or "parkir" in text.lower() or "bermasalah" in text.lower():
        mentioned = re.findall(r'@(\w+)', text)
        for username in mentioned:
            target_uid = next((u for u, data in warga_database.items() if data.get("username", "").lower() == username.lower()), None)
            if target_uid:
                # 1. Minta AI buatkan pesan teguran berdasarkan isi laporan (text)
                system_prompt_lapor = f"""Lu adalah asisten RT yang tegas. 
                Buatlah pesan teguran untuk warga yang dilaporkan karena: '{text}'.
                Aturan: Tegas, sopan tapi tidak basa-basi, jangan flirty. Langsung ke inti masalah."""
                
                try:
                    res = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[{"role": "system", "content": system_prompt_lapor}, {"role": "user", "content": text}]
                    )
                    pesan_ai = res.choices[0].message.content
                except:
                    pesan_ai = f"⚠️ Anda telah dilaporkan oleh warga terkait: {text}"

                # 2. Kirim pesan hasil olahan AI ke target
                try:
                    bot.send_message(target_uid, f"📢 Peringatan dari Smart RT:\n\n{pesan_ai}")
                    bot.reply_to(message, f"✅ Laporan ke @{username} sudah dikirim dengan teguran.")
                except:
                    bot.reply_to(message, f"❌ Gagal kirim ke @{username}.")
            else:
                bot.reply_to(message, f"❌ User @{username} tidak ditemukan di database.")
    # AI Chat
    if is_bot_target(message):
        chat_history.setdefault(uid, []).append({"role": "user", "content": text})
        bot_name = "SATRIA (Sistem Tanggap RT Ih Asique)"
        system_prompt = f"""perkenalkan diri lu {bot_name} dengan benar dan sopan tiap awal percakapan!.
Tugas lu: jawab pertanyaan warga/Pak RT dengan tegas, faktual, dan singkat.
Aturan:
- JANGAN flirty, JANGAN sok asik, JANGAN basa-basi.
- Kalau diajak ngobrol santai, balas singkat kayak teman tongkrongan. 
- Obrolan terlihat flow ngalir, ga kaku, ga halu, ga bingung
- Kalau user adalah ADMIN_ID (Pak RT), perlakukan sebagai Pak RT.
- Tidak perlu nanya 'ada lagi yang dibantu?'.
- Gunakan emoji seperlunya (🙏, 😂, 😭, 😡, 😞, ⚠️, ❌, 🆘).
- Jika info ilmiah, berikan jawaban singkat to the point yang langsung mengarah ke pertanyaan terkait + link referensi.
- Jaga jarak profesional (bukan CS).
- JANGAN TYPO
- JANGAN TERLIHAT SEPERTI AI, LOOKS NATURALLY AND FLOW LIKE HUMAN
- BISA SENTIMENT ANALYSIS TIAP {text} perhatikan {text} baik baik
- SELALU INGAT BAHWA {ADMIN_ID} adalah Pak RT, dan KALO UIDNYA BUKAN {ADMIN_ID} ITU ADALAH WARGA


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
