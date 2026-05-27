import os
import logging
import google.generativeai as genai
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

# 1. Konfigurasi Client dengan eksplisit API Key
API_KEY = os.getenv('AI_TOKEN')
genai.configure(api_key=API_KEY)

# 2. Kita pakai 'gemini-1.5-flash' tapi dengan cara panggil yang benar
# Kalau 1.5-flash error, ganti ke 'gemini-1.0-pro'
model = genai.GenerativeModel('gemini-1.5-flash')

async def ai_handler(update, context):
    try:
        # Kita pakai generate_content langsung dari objek model
        response = model.generate_content(update.message.text)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Error AI: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Smart RT Aktif. Silakan tanya apa saja!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_TOKEN')).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Bot standby...")
    app.run_polling()
