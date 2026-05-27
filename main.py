import os
import logging
import google.generativeai as genai
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          MessageHandler, filters, ContextTypes, ConversationHandler)

# Setup
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)
genai.configure(api_key=os.getenv("AI_TOKEN"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Data
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Buka"
INPUT_NOMINAL, INPUT_KATEGORI, UPLOAD_BUKTI = range(3)

# Background
async def check_ai_status(context):
    global PARKIR_STATUS
    PARKIR_STATUS = "🔴 Tutup" if datetime.now().second % 20 > 10 else "🟢 Buka"

# AI Handler
async def ai_handler(update, context):
    try:
        response = model.generate_content(f"Saldo Kas: {KAS_RT}. Parkir: {PARKIR_STATUS}. User: {update.message.text}")
        await update.message.reply_text(response.text)
    except:
        await update.message.reply_text("Maaf, AI sedang gangguan.")

# Start
async def start(update, context):
    kb = [[InlineKeyboardButton("💰 Lapor Kas", callback_data='lapor'), InlineKeyboardButton("📊 Cek Kas", callback_data='kas')],
          [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')]]
    await update.message.reply_text("🏠 *Smart RT Dashboard*", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

# Main
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.run_repeating(check_ai_status, interval=10, first=5)
    
    # Simple handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"📊 Saldo: Rp {KAS_RT:,}"), pattern='kas'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"🅿️ {PARKIR_STATUS}"), pattern='parkir'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    app.run_polling()
