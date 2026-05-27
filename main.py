import os
import logging
from datetime import datetime
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          MessageHandler, filters, ContextTypes, ConversationHandler)

# 1. Setup & Config
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)
client = genai.Client(api_key=os.getenv("AI_TOKEN"))

# 2. State & Data (In-Memory for now)
INPUT_NOMINAL, INPUT_KATEGORI, UPLOAD_BUKTI, GARANSI_DESC = range(4)
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Buka"
KATEGORI_KAS = ["Iuran Bulanan", "Dana Sosial", "Dana Kebersihan", "Lain-lain"]

# --- BACKGROUND MONITORING (Job Queue) ---
async def check_ai_status(context: ContextTypes.DEFAULT_TYPE):
    global PARKIR_STATUS
    # Di masa depan, ganti logic ini dengan request ke ESP32
    PARKIR_STATUS = "🔴 Tutup" if datetime.now().second % 20 > 10 else "🟢 Buka"

# --- AI INTERACTIVE ASSISTANT ---
async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    system_prompt = f"Anda adalah asisten Smart RT. Saldo Kas: Rp {KAS_RT:,}. Status Parkir: {PARKIR_STATUS}."
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=system_prompt + "\nUser: " + user_text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text("Maaf, otak AI sedang sibuk.")

# --- KAS RT LOGIC (Categorized & Approval) ---
async def lapor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Masukkan nominal (angka saja):")
    return INPUT_NOMINAL

async def input_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nominal'] = update.message.text
    kb = [[InlineKeyboardButton(k, callback_data=k)] for k in KATEGORI_KAS]
    await update.message.reply_text("Pilih kategori:", reply_markup=InlineKeyboardMarkup(kb))
    return INPUT_KATEGORI

async def input_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['kategori'] = update.callback_query.data
    await update.callback_query.message.reply_text("Kirim bukti foto transfer:")
    return UPLOAD_BUKTI

async def upload_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nom = context.user_data['nominal']
    kat = context.user_data['kategori']
    kb = [[InlineKeyboardButton("✅ Approve", callback_data='app_yes'), InlineKeyboardButton("❌ Reject", callback_data='app_no')]]
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, 
                                 caption=f"💰 Laporan: {kat}\nNominal: Rp {nom}\nUser: {update.message.from_user.first_name}",
                                 reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("Laporan terkirim ke Pak RT.")
    return ConversationHandler.END

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("💰 Lapor Kas", callback_data='lapor'), InlineKeyboardButton("📊 Cek Kas", callback_data='kas')],
          [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir'), InlineKeyboardButton("🛠 Garansi", callback_data='garansi')]]
    await update.message.reply_text("🏠 Smart RT Dashboard", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.run_repeating(check_ai_status, interval=10, first=5)
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lapor_start, pattern='lapor'), CallbackQueryHandler(start, pattern='garansi')],
        states={
            INPUT_NOMINAL: [MessageHandler(filters.TEXT, input_nominal)],
            INPUT_KATEGORI: [CallbackQueryHandler(input_kategori)],
            UPLOAD_BUKTI: [MessageHandler(filters.PHOTO, upload_bukti)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()
