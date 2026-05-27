import os
import logging
from datetime import datetime
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          MessageHandler, filters, ContextTypes, ConversationHandler)

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Konfigurasi
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)
client = genai.Client(api_key=os.getenv("AI_TOKEN"))

# Data
INPUT_NOMINAL, INPUT_KATEGORI, UPLOAD_BUKTI = range(3)
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Aman (Kosong)"
KATEGORI_KAS = ["Iuran Bulanan", "Dana Sosial", "Dana Kebersihan", "Lain-lain"]

# --- 1. MONITORING (Job Queue) ---
async def check_ai_status(context: ContextTypes.DEFAULT_TYPE):
    global PARKIR_STATUS
    PARKIR_STATUS = "🔴 Menghalangi Jalan!" if datetime.now().second % 20 > 10 else "🟢 Aman (Kosong)"

# --- 2. AI INTERACTIVE ---
async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    system_prompt = f"Anda asisten Smart RT. Data Kas: Rp {KAS_RT:,}. Status Parkir: {PARKIR_STATUS}. Jawab dengan sopan."
    response = client.models.generate_content(model='gemini-2.0-flash', contents=system_prompt + "\nUser: " + user_text)
    await update.message.reply_text(response.text)

# --- 3. KAS RT (Kategoris) ---
async def lapor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Masukkan nominal:")
    return INPUT_NOMINAL

async def input_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nominal'] = update.message.text
    kb = [[InlineKeyboardButton(k, callback_data=k)] for k in KATEGORI_KAS]
    await update.message.reply_text("Pilih kategori:", reply_markup=InlineKeyboardMarkup(kb))
    return INPUT_KATEGORI

async def input_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['kategori'] = query.data
    await query.message.reply_text("Kirim bukti foto:")
    return UPLOAD_BUKTI

async def upload_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nominal = context.user_data['nominal']
    kat = context.user_data['kategori']
    kb = [[InlineKeyboardButton("✅ Approve", callback_data='app_yes'), InlineKeyboardButton("❌ Reject", callback_data='app_no')]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, 
                                 caption=f"💰 Laporan: {kat}\nNominal: Rp {nominal}\nUser: {update.message.from_user.first_name}",
                                 reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("Laporan dikirim.")
    return ConversationHandler.END

# --- 4. MAIN ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.run_repeating(check_ai_status, interval=10, first=5)
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lapor_start, pattern='lapor')],
        states={
            INPUT_NOMINAL: [MessageHandler(filters.TEXT, input_nominal)],
            INPUT_KATEGORI: [CallbackQueryHandler(input_kategori)],
            UPLOAD_BUKTI: [MessageHandler(filters.PHOTO, upload_bukti)]
        },
        fallbacks=[CommandHandler("start", lambda u, c: u.message.reply_text("Reset. Ketik /start"))]
    )
    
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()
