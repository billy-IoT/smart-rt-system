import os
import telebot
from groq import Groq

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # Masukkan ID Telegram kamu di sini
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# Data RT
KAS_RT = "Rp 0"
PARKIR_STATUS = "🟢 Buka"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Halo! Asisten Smart RT siap membantu. Laporkan masalah warga ke sini ya!")

@bot.message_handler(func=lambda message: True)
def reply(message):
    text = message.text.lower()
    
    # 1. LOGIKA PELAPORAN (Japri atau Grup)
    if "lapor" in text or "aduan" in text:
        laporan = f"🚨 *Laporan Baru*\nDari: {message.from_user.first_name}\nIsi: {message.text}"
        # Kirim laporan ke kamu (Pa Rete)
        bot.send_message(ADMIN_ID, laporan, parse_mode='Markdown')
        bot.reply_to(message, "✅ Laporan sudah diterima, Pa Rete akan segera menindaklanjuti.")
        return

    # 2. LOGIKA GROUP VS JAPRI
    if message.chat.type == 'group' or message.chat.type == 'supergroup':
        # Jika di grup, bot cuma bales kalau di-reply atau di-mention (opsional)
        # Atau langsung bales aja biar rame
        process_ai(message)
    else:
        # Jika Japri, langsung bales
        process_ai(message)

def process_ai(message):
    try:
        system_prompt = f"Anda adalah asisten Smart RT. Kas: {KAS_RT}. Parkir: {PARKIR_STATUS}. Jawab dengan santun."
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message.text}],
            model="llama-3.3-70b-versatile",
        )
        bot.reply_to(message, chat_completion.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

print("Bot Smart RT Siap Tempur!")
bot.infinity_polling()
