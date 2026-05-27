import os
import telebot
from groq import Groq

# 1. Konfigurasi API
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# 2. Data RT (Update di sini kalau ada perubahan)
KAS_RT = "Rp 0"
PARKIR_STATUS = "🟢 Buka"

# 3. Handler Command /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🏠 *Smart RT Dashboard*\n\n"
                          "Woi warga! Ada yang bisa dibantu?\n"
                          "💰 Kas RT: " + KAS_RT + "\n"
                          "🅿️ Status Parkir: " + PARKIR_STATUS + "\n\n"
                          "Tag gue kalau mau tanya-tanya, atau ketik 'Lapor' kalau ada masalah!", parse_mode='Markdown')

# 4. Handler Utama (AI + Filter Grup)
@bot.message_handler(func=lambda message: True)
def reply(message):
    text = message.text.lower()
    
    # A. LOGIKA PELAPORAN (Japri atau Grup tetep jalan)
    if "lapor" in text or "aduan" in text:
        laporan = f"🚨 *Laporan Baru*\nDari: {message.from_user.first_name}\nIsi: {message.text}"
        bot.send_message(ADMIN_ID, laporan, parse_mode='Markdown')
        bot.reply_to(message, "✅ Siap, laporannya udah gue terusin ke Pak RT ya!")
        return

    # B. LOGIKA FILTER GRUP (Anti Spam)
    is_group = message.chat.type in ['group', 'supergroup']
    if is_group:
        is_mentioned = f"@{bot.get_me().username}" in message.text
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id
        
        if not (is_mentioned or is_reply):
            return # Bot diem aja kalau nggak di-tag/reply

    # C. LOGIKA AI (Bahasa Gaul)
    try:
        system_prompt = (
            f"Lu adalah asisten RT yang luwes, santai, dan gaya bicaranya kayak warga nongkrong di pos ronda. "
            f"Data RT: Kas {KAS_RT}, Status Parkir {PARKIR_STATUS}. "
            f"Jawab warga dengan gaya santai dan ramah. "
            f"Kalau ada warga yang nanya, jawab berdasarkan data RT di atas. "
            f"Jangan terlalu kaku, panggil warga dengan sebutan 'Warga' atau 'Pak/Bu'."
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message.text}
            ],
            model="llama-3.3-70b-versatile",
        )

        answer = chat_completion.choices[0].message.content
        bot.reply_to(message, answer)
    except Exception as e:
        bot.reply_to(message, f"Aduh, sistem lagi error nih: {str(e)}")

print("Bot Smart RT Siap Tempur! 😹")
bot.infinity_polling()
