import os
import logging
import google.generativeai as genai
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Setup
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv('TELEGRAM_TOKEN')
API_KEY = os.getenv('AI_TOKEN')

# Konfigurasi AI
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Data Statis
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Buka"

# Fungsi Monitoring
async def check_ai_status(context):
    global PARKIR_STATUS
    PARKIR_STATUS = "🔴 Tutup" if datetime.now().second % 20 > 10 else "🟢 Buka"

# Fungsi AI Handler (dengan Debug)
async def ai_handler(update, context):
    try:
        user_input = update.message.text
        prompt = f"Saldo Kas: {KAS_RT}. Parkir: {PARKIR_STATUS}. Jawab asisten Smart RT: {user_input}"
        response = model.generate_content(prompt)
        await update.message.reply_text(response.text)
    except Exception as e:
        # Ini akan memberitahu error aslinya kalau API Key salah
        await update.message.reply_text(f"Error AI: {str(e)}")

# Fungsi Start
async def start(update, context):
    kb = [
        [InlineKeyboardButton("💰 Cek Kas", callback_data='kas'), InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')]
    ]
    await update.message.reply_text("🏠 *Smart RT Dashboard*\nSilakan pilih menu:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# Main
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Job Queue
    app.job_queue.run_repeating(check_ai_status, interval=10, first=5)
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"📊 Saldo: Rp {KAS_RT:,}"), pattern='kas'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"🅿️ {PARKIR_STATUS}"), pattern='parkir'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    print("Bot sedang berjalan...")
    app.run_polling()
