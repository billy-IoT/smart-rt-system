import os
import logging
import requests
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

# Ganti 'v1beta' ke 'v1' biar lebih stabil
API_KEY = os.getenv('AI_TOKEN')
MODEL = "gemini-1.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL}:generateContent?key={API_KEY}"

async def ai_handler(update, context):
    try:
        # Kirim prompt ke Google Gemini via HTTP Request
        payload = {"contents": [{"parts": [{"text": update.message.text}]}]}
        response = requests.post(URL, json=payload).json()
        
        # Ambil jawaban AI dengan aman
        answer = response['candidates'][0]['content']['parts'][0]['text']
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Error AI: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Smart RT Dashboard siap! Silakan tanya.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_TOKEN')).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Bot sudah standby...")
    app.run_polling()
