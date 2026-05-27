import os
import telebot
from groq import Groq

# 1. Konfigurasi
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID") # Pastikan ini ID Telegram lu (angka)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# 2. Data RT (State sementara)
data = {
    "kas": "Rp 0",
    "parkir": "🟢 Buka"
}

# 3. Handler Command
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, f"🏠 *Smart RT Dashboard*\n\n"
                          f"💰 Kas RT: {data['kas']}\n"
                          f"🅿️ Status Parkir: {data['parkir']}\n\n"
                          f"Tag gue kalau mau tanya-tanya!", parse_mode='Markdown')

# 4. Handler Utama (Logic Admin vs Warga)
@bot.message_handler(func=lambda message: True)
def reply(message):
    text = message.text.lower()
    user_id = str(message.from_user.id)
    is_admin = (user_id == str(ADMIN_ID))

    # --- A. FITUR ADMIN (Update Data) ---
    if is_admin:
        if text.startswith("set kas"):
            data['kas'] = text.replace("set kas", "").strip()
            bot.reply_to(message, f"✅ Kas berhasil diupdate jadi {data['kas']}")
            return
        if text.startswith("set parkir"):
            data['parkir'] = text.replace("set parkir", "").strip()
            bot.reply_to(message, f"✅ Status parkir diupdate jadi {data['parkir']}")
            return

    # --- B. FITUR LAPORAN (Warga) ---
    if "lapor" in text or "aduan" in text:
        laporan = f"🚨 *Laporan Warga*\nDari: {message.from_user.first_name}\nIsi: {message.text}"
        bot.send_message(ADMIN_ID, laporan, parse_mode='Markdown')
        bot.reply_to(message, "✅ Laporan udah dikirim ke Pak RT ya!")
        return

    # --- C. FILTER GRUP (Anti-Spam) ---
    if message.chat.type in ['group', 'supergroup']:
        is_mentioned = f"@{bot.get_me().username}" in message.text
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id
        if not (is_mentioned or is_reply): return

    # --- D. LOGIKA AI (Savage & Membedakan User) ---
    try:
        role_desc = "Anda adalah Pak RT (Admin)." if is_admin else "Anda adalah asisten RT yang melayani warga."
        
        system_prompt = (
            f"{role_desc} Data RT: Kas {data['kas']}, Status Parkir {data['parkir']}. "
            f"Gaya bicara: Luwes, santai, ala pos ronda. "
            f"Jika warga bertanya tentang kas atau parkir, jawab berdasarkan data tersebut."
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message.text}
            ],
            model="llama-3.3-70b-versatile",
        )
        bot.reply_to(message, chat_completion.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"Error nih: {str(e)}")

print("Bot Smart RT Siap Tempur! 😹")
bot.infinity_polling()
