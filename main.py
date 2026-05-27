import os
import telebot
from telebot import types
from groq import Groq

# 1. KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # Masukkan ID angka lu di sini (contoh: 123456789)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# DATA SEMENTARA (In-Memory)
data = {"kas": 0, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}

def is_admin(user_id): return str(user_id) == str(ADMIN_ID)

# 2. START MENU
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 *Smart RT Dashboard* - Halo Warga!", parse_mode='Markdown', reply_markup=markup)

# 3. HANDLER UTAMA
@bot.message_handler(content_types=['text', 'photo', 'document'])
def main_handler(message):
    uid = str(message.from_user.id)
    
    # A. CEK STATE (Lagi lapor?)
    if uid in user_states:
        handle_lapor_steps(message)
        return

    # B. MENU UTAMA
    text = message.text if message.text else ""
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Siap! Masukkan nama lengkap Anda:")
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: *{data['kas']}*\n🅿️ Parkir: *{data['parkir']}*", parse_mode='Markdown')
    else:
        # C. AI RESPONSE (Kalau bukan lapor & bukan menu)
        try:
            persona = "Pak RT" if is_admin(uid) else "Warga"
            res = client.chat.completions.create(messages=[{"role": "system", "content": f"Anda asisten RT. Bicara dengan {persona}. Kas: {data['kas']}."}, {"role": "user", "content": text}], model="llama-3.3-70b-versatile")
            bot.reply_to(message, res.choices[0].message.content)
        except: pass

# 4. ALUR LAPOR (STATE MACHINE)
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
        bot.reply_to(message, "Terakhir, kirim foto/dokumen bukti transfernya:", reply_markup=types.ReplyKeyboardRemove())
        
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
        
        bot.send_photo(ADMIN_ID, photo_id, 
                       caption=f"🚨 *Laporan Baru*\nID: {uid}\nNama: {pending_approvals[uid]['nama']}\nKategori: {pending_approvals[uid]['kategori']}\nJumlah: Rp {pending_approvals[uid]['jumlah']}", 
                       reply_markup=markup, parse_mode='Markdown')
        
        bot.reply_to(message, "Laporan terkirim. Ditunggu Pak RT ya!")
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
