import os
import logging
import requests
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

API_KEY = ('AIzaSyDBwamNE3ClY6c7xYh_ln6um8cppZF-Mtc')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

async def ai_handler(update, context):
    try:
        payload = {"contents": [{"parts": [{"text": update.message.text}]}]}
        response = requests.post(URL, json=payload).json()
        
        # Log response ke console Railway untuk debugging
        print(f"DEBUG RESPONSE: {response}")

        # Akses yang lebih aman
        if 'candidates' in response:
            answer = response['candidates'][0]['content']['parts'][0]['text']
            await update.message.reply_text(answer)
        else:
            # Jika ada error dari Google, tampilkan error aslinya
            error_msg = response.get('error', {}).get('message', 'Unknown error')
            await update.message.reply_text(f"Google API Error: {error_msg}")
            
    except Exception as e:
        await update.message.reply_text(f"Error teknis: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Smart RT siap. Silakan tanya!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()
