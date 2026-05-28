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
bot_name = "SATRIA (Sistem Tanggap RT Ih Asique)"

# =========================================
# DATABASE
# =========================================
kas_rt = {"total": 0, "Kebersihan": 0, "Keamanan": 0, "Lain-lain": 0}
warga_database = {}
user_states = {}
pending_approvals = {}
chat_history = {}
spam_counter = {}
laporan_warga = []
# =========================================
# HELPER
# =========================================
def get_role(uid):
    return "Pak RT" if str(uid) == ADMIN_ID else "Warga"

def get_greeting():
    hour = datetime.datetime.now(pytz.timezone("Asia/Jakarta")).hour
    if 5 <= hour < 12: return "Pagi"
    if 12 <= hour < 15: return "Siang"
    if 15 <= hour < 18: return "Sore"
    return "Malam"

def is_bot_target(message):
    # Kalau di private, selalu balas
    if message.chat.type == "private": return True
    
    # Kalau di grup, HANYA BALAS JIKA DI-REPLY ke bot ATAU di-tag @botname
    if message.reply_to_message and message.reply_to_message.from_user.is_bot: return True
    if message.text and f"@{bot.get_me().username}" in message.text: return True
    
    return False # Sisanya abaikan (biar tidak nyerocos)

def limit_history(uid):
    if uid in chat_history:
        chat_history[uid] = chat_history[uid][-6:]

def broadcast_message(text, is_emergency=False):
    users = list(warga_database.keys())
    if is_emergency:
        announcement = f"🚨 DARURAT 🚨\n\n{text}\n\nMohon perhatian seluruh warga."
    else:
        announcement = f"📢 Pengumuman RT\n\n{text}"
    
    for uid in users:
        try: bot.send_message(uid, announcement)
        except: pass

def get_ai_response(uid, text, role):
    nama = warga_database.get(uid, {}).get("name", "Warga")
    system_prompt = f"""kenalkan diri {bot_name}.
User: Nama: {nama}, Role: {role}
Aturan: ngobrol natural, santai, singkat, jangan formal, jangan halu, jangan typo, jangan ngulang pertanyaan, jangan kaya CS, jangan kepanjangan, flow manusia chat biasa, emoji seperlunya 😹😭🙏.
Kalau role user Pak RT: hormati sebagai admin, jangan panggil warga.
Kas RT: Rp {kas_rt['total']:,}"""

    max_tokens = 80
    if len(text) > 100: max_tokens = 150
    if "jelaskan" in text.lower(): max_tokens = 200
    if "coding" in text.lower(): max_tokens = 250

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            top_p=0.7,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system_prompt}, *chat_history[uid]]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error AI\n{str(e)}"

# =========================================
# START
# =========================================
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    warga_database[uid] = {"name": message.from_user.first_name, "username": message.from_user.username}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas")
    
    role = get_role(uid)
    greet = f"Selamat {get_greeting()} {'Pak RT' if role == 'Pak RT' else ''}\n\n{bot_name} siap bantu."
    bot.reply_to(message, greet, reply_markup=markup)

# =========================================
# MAIN HANDLER
# =========================================
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    uid = str(message.from_user.id)
    role = get_role(uid)
    text = message.text or message.caption or ""
    warga_database.setdefault(uid, {"name": message.from_user.first_name, "username": message.from_user.username})

    if uid in user_states:
        handle_iuran(message)
        return

    if role == "Pak RT" and "laporan" in text.lower():
        if not laporan_warga:
            bot.reply_to(message, "Belum ada laporan dari warga.")
        else:
            bot.reply_to(message, "📋 Daftar laporan masuk:\n" + "\n".join(laporan_warga))
        return

    if role == "Pak RT":
        if text.startswith("/bc "):
            broadcast_message(text.replace("/bc ", ""))
            bot.reply_to(message, "✅ Broadcast terkirim.")
            return

        if text.startswith("/mute "):
            if message.chat.type == "private":
                bot.reply_to(message, "⚠️ Fitur mute cuma buat grup.")
                return
            
            target_username = text.split(" ")[1].replace("@", "")
            target_uid = next((u for u, data in warga_database.items() if data.get("username", "").lower() == target_username.lower()), None)
            
            if str(target_uid) == ADMIN_ID:
                bot.reply_to(message, "❌ Tidak bisa mute Pak RT.")
                return
            
            if target_uid:
                try:
                    until_date = datetime.datetime.now() + datetime.timedelta(minutes=5)
                    bot.restrict_chat_member(chat_id=message.chat.id, user_id=int(target_uid), until_date=until_date, permissions=types.ChatPermissions(can_send_messages=False))
                    bot.reply_to(message, f"🔇 @{target_username} dimute 5 menit")
                except Exception as e:
                    bot.reply_to(message, f"❌ Gagal mute\n{str(e)}")
            else:
                bot.reply_to(message, "❌ User tidak ditemukan.")
            return

    spam_counter[uid] = spam_counter.get(uid, 0) + 1
    if spam_counter[uid] > 10:
        if message.chat.type != "private":
            try:
                until_date = datetime.datetime.now() + datetime.timedelta(minutes=5)
                bot.restrict_chat_member(chat_id=message.chat.id, user_id=int(uid), until_date=until_date, permissions=types.ChatPermissions(can_send_messages=False))
                bot.reply_to(message, "🚫 Kena mute 5 menit gara gara spam AWOWKWOWK")
            except: pass
        return

    if text == "💰 Lapor Iuran":
        user_states[uid] = {"state": "WAITING_NAME"}
        bot.reply_to(message, "Masukin nama lengkap:")
        return
    elif text == "📋 Cek Kas":
        detail = f"💰 Rincian Kas RT\n\nKebersihan: Rp {kas_rt['Kebersihan']:,}\nKeamanan: Rp {kas_rt['Keamanan']:,}\nLain-lain: Rp {kas_rt['Lain-lain']:,}\n\nTOTAL: Rp {kas_rt['total']:,}"
        bot.reply_to(message, detail)
        return

    if text.lower().startswith("darurat "):
        if role == "Pak RT":
            broadcast_message(text.replace("darurat ", ""), is_emergency=True)
            bot.reply_to(message, "✅ Pesan darurat disebar.")
        else:
            bot.reply_to(message, "❌ Hanya Pak RT.")
        return

    if any(k in text.lower() for k in ["lapor", "parkir", "bermasalah"]):
        # 1. Simpan laporan ke database
        laporan_warga.append(f"{message.from_user.first_name} melapor: {text}")
        
        # 2. Buat pesan teguran AI
        try:
            system_prompt_lapor = f"kenalkan diri {bot_name}. Buat teguran buat warga: {text}. Aturan: tegas, sopan, langsung ke inti. Akhiri dengan: - {bot_name}"
            res = client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": system_prompt_lapor}])
            pesan_ai = res.choices[0].message.content
        except:
            pesan_ai = f"⚠️ Teguran terkait: {text}\n\n- {bot_name}"

        # 3. KIRIM DI GRUP (Pasti jalan karena di luar looping target)
        bot.send_message(message.chat.id, f"📢 TEGURAN TERBUKA\n\n{pesan_ai}")
        
        # 4. KIRIM JAPRI (Hanya jika ketemu usernya)
        mentions = re.findall(r'@(\w+)', text)
        for username in mentions:
            target_uid = next((u for u, data in warga_database.items() if data.get("username", "").lower() == username.lower()), None)
            if target_uid:
                try:
                    bot.send_message(target_uid, f"📢 Teguran RT (Japri)\n\n{pesan_ai}")
                except:
                    pass 
        
        return # Agar tidak diproses AI chat

    if is_bot_target(message):
        chat_history.setdefault(uid, [])
        chat_history[uid].append({"role": "user", "content": text})
        limit_history(uid)
        ans = get_ai_response(uid, text, role)
        chat_history[uid].append({"role": "assistant", "content": ans})
        limit_history(uid)
        bot.reply_to(message, ans)

# =========================================
# FLOW IURAN
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
            if message.text == "3":
                state_data["state"] = "WAITING_DESC"
                bot.reply_to(message, "Masukin keterangan:")
            else:
                state_data["state"] = "WAITING_AMOUNT"
                bot.reply_to(message, "Masukin nominal:")
        else: bot.reply_to(message, "Pilih 1, 2, atau 3.")
    elif state == "WAITING_DESC":
        state_data["keterangan"] = message.text
        state_data["state"] = "WAITING_AMOUNT"
        bot.reply_to(message, "Masukin nominal:")
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
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
            ket = f"\nKet: {state_data.get('keterangan', '-')}"
            bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💰 Laporan Iuran\nNama: {state_data['nama']}\nKategori: {state_data['kategori']}\nNominal: Rp {state_data['jumlah']:,}{ket}", reply_markup=markup)
            bot.reply_to(message, "✅ Laporan terkirim ke Pak RT.")
            del user_states[uid]
        else: bot.reply_to(message, "Kirim foto bukti transfer.")

# =========================================
# CALLBACK
# =========================================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    parts = call.data.split("_")
    action, uid = parts[0], parts[1]
    if uid not in pending_approvals: return
    
    data = pending_approvals[uid]
    if action == "approve":
        kas_rt[data['kategori']] += data['jumlah']
        kas_rt["total"] += data['jumlah']
        bot.send_message(uid, f"✅ Iuran disetujui\n\n{data['kategori']}: Rp {data['jumlah']:,}\nTerima kasih {data['nama']} 🙏")
        bot.edit_message_caption(caption=f"✅ DISETUJUI\n\nNama: {data['nama']}\nKategori: {data['kategori']}\nJumlah: Rp {data['jumlah']:,}\n\nTotal Kas: Rp {kas_rt['total']:,}", chat_id=call.message.chat.id, message_id=call.message.message_id)
    else:
        bot.send_message(uid, "❌ Iuran ditolak.")
        bot.edit_message_caption(caption="❌ Iuran ditolak.", chat_id=call.message.chat.id, message_id=call.message.message_id)
    del pending_approvals[uid]

print("Bot Smart RT nyala")
bot.infinity_polling()
