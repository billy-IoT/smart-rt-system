import os
import logging
import requests
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv('AI_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# Gunakan URL API resmi Google (v1beta)
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

async def ai_handler(update, context):
    try:
        # Kirim request manual ke API Google tanpa library Google
        payload = {"contents": [{"parts": [{"text": update.message.text}]}]}
        response = requests.post(URL, json=payload).json()
        
        # Ambil teks dari response
        answer = response['candidates'][0]['content']['parts'][0]['text']
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Gagal chat AI: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Smart RT (Manual API) siap!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()
