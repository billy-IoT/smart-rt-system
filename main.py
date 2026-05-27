import os
import telebot
from telebot import types
from groq import Groq

# 1. KONFIGURASI
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # Harus ID angka (Contoh: 123456789)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# DATA
data = {"kas": 0, "parkir": "🟢 Buka"}
user_states = {} 
pending_approvals = {}

def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 2. START MENU
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Lapor Iuran", "📋 Cek Kas & Info")
    bot.reply_to(message, "🏠 Smart RT Dashboard - Halo Warga! Gunakan menu di bawah:", 
                 parse_mode='Markdown', reply_markup=markup)

# 3. LOGIKA UTAMA (MENU & STATE & AI)
@bot.message_handler(content_types=['text', 'photo', 'document'])
def main_handler(message):
    uid = message.from_user.id
    
    # --- A. CEK APAKAH LAGI LAPOR (STATE) ---
    if uid in user_states:
        handle_lapor_steps(message)
        return

    # --- B. CEK MENU ---
    text = message.text if message.text else ""
    if text == "💰 Lapor Iuran":
        user_states[uid] = {'state': 'WAITING_NAME'}
        bot.reply_to(message, "Siap! Masukin nama lengkap kamu:")
        return
    elif text == "📋 Cek Kas & Info":
        bot.reply_to(message, f"💰 Kas RT: *{data['kas']}*\n🅿️ Parkir: *{data['parkir']}*", parse_mode='Markdown')
        return

    # --- C. AI RESPONSE (Kalau bukan state dan bukan menu) ---
    try:
        persona = "Pak RT" if is_admin(uid) else "Warga"
        prompt = f"Anda asisten Pak RT. Bicara dengan {persona}. Kas RT: {data['kas']}. Gaya bicara: gaul/santai/sopan tapi sesuai kan kalo warganya bapak bapak/ibu ibu lebih sopan ama formal aja, tapi kalo gen z atau remaja gaul asik ala tongkrongan tapi tetep sopan."
        res = client.chat.completions.create(messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}], model="llama-3.3-70b-versatile")
        bot.reply_to(message, res.choices[0].message.content)
    except: pass

# 4. FUNGSI LAPOR (STATE MACHINE)
def handle_lapor_steps(message):
    uid = message.from_user.id
    state = user_states[uid]['state']
    
    if state == "WAITING_NAME":
        user_states[uid] = {'state': 'WAITING_AMOUNT', 'nama': message.text}
        bot.reply_to(message, "Mantap! Sekarang masukkan nominalnya (angka saja):")
        
    elif state == "WAITING_AMOUNT":
        try:
            jumlah = int(message.text)
            user_states[uid] = {'state': 'WAITING_PHOTO', 'nama': user_states[uid]['nama'], 'jumlah': jumlah}
            bot.reply_to(message, "Terakhir, kirim foto/dokumen bukti transfernya:")
        except: bot.reply_to(message, "Eh, nominalnya harus angka ya! Ulangin lagi.")
        
    elif state == "WAITING_PHOTO":
        # Cek apakah itu foto atau dokumen
        photo_id = None
        if message.photo: photo_id = message.photo[-1].file_id
        elif message.document: photo_id = message.document.file_id
        
        if not photo_id:
            bot.reply_to(message, "Harus kirim foto bukti transfer ya!")
            return
            
        nama = user_states[uid]['nama']
        jumlah = user_states[uid]['jumlah']
        pending_approvals[str(uid)] = {'nama': nama, 'jumlah': jumlah, 'photo': photo_id}
        
        # Kirim ke Pak RT
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"))
        bot.send_photo(ADMIN_ID, photo_id, caption=f"🚨 *Laporan Baru*\nNama: {nama}\nJumlah: Rp {jumlah}", 
                       reply_markup=markup, parse_mode='Markdown')
        
        bot.reply_to(message, "Laporan udah dikirim ke Pak RT. Ditunggu ya!")
        del user_states[uid]

# 5. CALLBACK APPROVAL
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve_handler(call):
    if not is_admin(call.from_user.id): return
    uid = call.data.split("_")[1]
    
    if uid in pending_approvals:
        item = pending_approvals.pop(uid)
        data['kas'] += item['jumlah']
        bot.send_message(uid, f"✅ *Iuran Diterima!*\n\n{item['nama']}, iuran Rp {item['jumlah']} sudah lunas.", parse_mode='Markdown')
        bot.edit_message_caption(f"✅ Disetujui! {item['nama']} (Rp {item['jumlah']}) LUNAS.", 
                                 call.message.chat.id, call.message.message_id)

bot.infinity_polling()
