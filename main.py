import os
import logging
import google.generativeai as genai
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          MessageHandler, filters, ContextTypes, ConversationHandler)

# 1. Setup Logging & API
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)

# Konfigurasi AI
genai.configure(api_key=os.getenv("AI_TOKEN"))
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. State & Data
INPUT_NOMINAL, INPUT_KATEGORI, UPLOAD_BUKTI, GARANSI_DESC = range(4)
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Buka"
KATEGORI_KAS = ["Iuran Bulanan", "Dana Sosial", "Dana Kebersihan", "Lain-lain"]

# --- BACKGROUND MONITORING ---
async def check_ai_status(context: ContextTypes.DEFAULT_TYPE):
    global PARKIR_STATUS
    PARKIR_STATUS = "🔴 Tutup" if datetime.now().second % 20 > 10 else "🟢 Buka"

# --- AI INTERACTIVE ASSISTANT ---
async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    system_prompt = f"Anda asisten Smart RT. Data saat ini: Saldo Kas Rp {KAS_RT:,}, Status Parkir: {PARKIR_STATUS}. Jawab dengan sopan."
    try:
        response = model.generate_content(system_prompt + "\nUser: " + user_text)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text("Maaf, sistem AI sedang gangguan.")

# --- KAS RT LOGIC ---
async def lapor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Masukkan nominal (angka saja):")
    return INPUT_NOMINAL

async def input_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nominal'] = update.message.text
    kb = [[InlineKeyboardButton(k, callback_data=k)] for k in KATEGORI_KAS]
    await update.message.reply_text("Pilih kategori:", reply_markup=InlineKeyboardMarkup(kb))
    return INPUT_KATEGORI

async def input_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['kategori'] = query.data
    await query.message.reply_text("Kirim bukti foto transfer:")
    return UPLOAD_BUKTI

async def upload_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nom = context.user_data.get('nominal')
    kat = context.user_data.get('kategori')
    kb = [[InlineKeyboardButton("✅ Approve", callback_data='app_yes'), InlineKeyboardButton("❌ Reject", callback_data='app_no')]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, 
                                 caption=f"💰 Laporan: {kat}\nNominal: Rp {nom}\nUser: {update.message.from_user.first_name}",
                                 reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("Laporan terkirim ke Pak RT.")
    return ConversationHandler.END

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global KAS_RT
    query = update.callback_query
    if query.data == 'app_yes':
        KAS_RT += 50000 
        await query.edit_message_caption(caption=f"✅ Approved! Saldo: Rp {KAS_RT:,}")
    else: await query.edit_message_caption(caption="❌ Ditolak.")

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("💰 Lapor Kas", callback_data='lapor'), InlineKeyboardButton("📊 Cek Kas", callback_data='kas')],
          [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir'), InlineKeyboardButton("🛠 Garansi", callback_data='garansi')]]
    await update.message.reply_text("🏠 *Smart RT Dashboard*", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.run_repeating(check_ai_status, interval=10, first=5)
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lapor_start, pattern='lapor')],
        states={
            INPUT_NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_nominal)],
            INPUT_KATEGORI: [CallbackQueryHandler(input_kategori)],
            UPLOAD_BUKTI: [MessageHandler(filters.PHOTO, upload_bukti)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_approval, pattern='app_'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"🅿️ {PARKIR_STATUS}"), pattern='parkir'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"📊 Saldo: Rp {KAS_RT:,}"), pattern='kas'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()        await update.message.reply_text(response.text)
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
