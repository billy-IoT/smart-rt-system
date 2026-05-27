import os
import telebot
from telebot import types
from groq import Groq

# 1. KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

data = {"kas": 5000000, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}

def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

# 2. START MENU
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga! Ada yang bisa dibantu?", parse_mode='Markdown', reply_markup=markup)

# 3. HANDLER UTAMA & AI SMART
@bot.message_handler(content_types=['text', 'photo', 'document'])
def main_handler(message):
    uid = str(message.from_user.id)
    
    if uid in user_states:
        handle_lapor_steps(message)
        return

    text = message.text if message.text else ""
    
    # Filter Menu
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Siap! Masukkan nama lengkap Anda:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: *{data['kas']}*\n🅿️ Parkir: *{data['parkir']}*", parse_mode='Markdown')
        return

    # AI RESPONSE (Prompt yang lebih stabil)
    try:
        persona = "Pak RT" if is_admin(uid) else "Warga"
        system_prompt = f"""
        Anda adalah asisten cerdas Smart RT.
        Gaya bahasa: Ramah, santai, gaul, namun profesional.
        Tugas: 
        1. Menjawab pertanyaan warga seputar lingkungan.
        2. Jika ada keluhan (parkir, sampah, dll), berikan empati & konfirmasi bahwa laporan akan diteruskan ke Pak RT.
        3. JANGAN melakukan asumsi halu seperti kebakaran/darurat medis kecuali warga secara eksplisit mengatakannya.
        4. JANGAN forward pesan ke diri sendiri. Cukup jawab warga dengan sopan.
        """
        
        res = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], 
            model="llama-3.3-70b-versatile"
        )
        jawaban = res.choices[0].message.content
        bot.reply_to(message, jawaban)

        # OTOMATIS FORWARD KE PAK RT JIKA TERDETEKSI KELUHAN
        keywords = ["parkir", "ganggu", "lapor", "masalah", "tolong"]
        if any(key in text.lower() for key in keywords) and not is_admin(uid):
            bot.send_message(ADMIN_ID, f"🚨 *Laporan Warga*:\nDari: {message.from_user.first_name} (ID: {uid})\nIsi: {text}")
    except: 
        pass

# 4. STATE MACHINE (Lapor Iuran)
def handle_lapor_steps(message):
    uid = str(message.from_user.id)
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Mantap! Sekarang masukkan nominalnya (angka saja):")
    elif state == "WAITING_AMOUNT":
        try:
            jumlah = int(message.text)
            user_states[uid] = {'state': 'WAITING_CATEGORY', 'nama': user_states[uid]['nama'], 'jumlah': jumlah}
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.row("Iuran Bulanan", "Dana Kematian", "Dana Kebersihan")
            bot.reply_to(message, "Pilih kategori iurannya:", reply_markup=markup)
        except: bot.reply_to(message, "Input harus angka!")
    elif state == "WAITING_CATEGORY":
        user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 
                            'jumlah': user_states[uid]['jumlah'], 'kategori': message.text}
        bot.reply_to(message, "Terakhir, kirim foto bukti transfernya:", reply_markup=types.ReplyKeyboardRemove())
    elif state == "WAITING_PHOTO":
        photo_id = message.photo[-1].file_id if message.photo else (message.document.file_id if message.document else None)
        if not photo_id:
            bot.reply_to(message, "Woi, kirim fotonya dulu!")
            return
        
        pending_approvals[uid] = {
            'nama': user_states[uid]['nama'], 'jumlah': user_states[uid]['jumlah'],
            'kategori': user_states[uid]['kategori'], 'photo': photo_id
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}"))
        
        bot.send_photo(ADMIN_ID, photo_id, caption=f"🚨 *Laporan Iuran Baru*\nID: {uid}\nNama: {pending_approvals[uid]['nama']}\nKategori: {pending_approvals[uid]['kategori']}\nJumlah: Rp {pending_approvals[uid]['jumlah']}", reply_markup=markup, parse_mode='Markdown')
        bot.reply_to(message, "Laporan iuran terkirim. Ditunggu Pak RT ya!")
        del user_states[uid]

# 5. APPROVAL
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if not is_admin(call.from_user.id): return
    action, uid = call.data.split("_")
    if uid in pending_approvals:
        item = pending_approvals.pop(uid)
        if action == "approve":
            data['kas'] += item['jumlah']
            bot.send_message(uid, f"✅ *Lunas!* Iuran {item['nama']} ({item['kategori']}) Rp {item['jumlah']} sudah diterima.")
            bot.edit_message_caption(f"✅ Disetujui! {item['nama']} ({item['kategori']})", call.message.chat.id, call.message.message_id)
        else:
            bot.send_message(uid, f"❌ Maaf {item['nama']}, laporan ditolak Pak RT.")
            bot.edit_message_caption(f"❌ Ditolak! {item['nama']} ({item['kategori']})", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
