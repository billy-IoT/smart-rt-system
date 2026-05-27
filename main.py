import os
import logging
import google.generativeai as genai
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Setup
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv('TELEGRAM_TOKEN')
genai.configure(api_key=os.getenv('AI_TOKEN'))

# PENTING: Gunakan 'gemini-pro' (tanpa angka) ini model paling stabil
model = genai.GenerativeModel('gemini-pro')

async def ai_handler(update, context):
    try:
        response = model.generate_content(update.message.text)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Error AI: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Bot Smart RT Aktif! Silakan chat.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()
