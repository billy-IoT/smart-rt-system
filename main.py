import os
import logging
from datetime import datetime
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          MessageHandler, filters, ContextTypes, ConversationHandler)

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Konfigurasi API
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)
genai.configure(api_key=os.getenv("AI_TOKEN"))
model = genai.GenerativeModel('gemini-1.5-flash')

# State & Data
INPUT_NOMINAL, UPLOAD_BUKTI = range(2)
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Aman (Kosong)"

# --- 1. BACKGROUND MONITORING (Job Queue) ---
async def check_ai_status(context: ContextTypes.DEFAULT_TYPE):
    global PARKIR_STATUS
    # Simulasi status dari sensor
    if datetime.now().second % 20 < 10:
        PARKIR_STATUS = "🟢 Aman (Kosong)"
    else:
        PARKIR_STATUS = "🔴 Menghalangi Jalan!"

# --- 2. AI INTERACTIVE HANDLER ---
async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    system_prompt = f"""
    Kamu adalah asisten virtual Smart RT yang ramah. 
    Gunakan data ini untuk menjawab: 
    - Saldo Kas RT saat ini: Rp {KAS_RT:,}
    - Status Parkir terkini: {PARKIR_STATUS}
    Berikan jawaban yang sopan dan informatif.
    """
    response = model.generate_content(system_prompt + "\nUser: " + user_text)
    await update.message.reply_text(response.text)

# --- 3. START & GREETING (Smart Context) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jam = datetime.now().hour
    greeting = "Selamat Pagi" if 5 <= jam < 12 else "Selamat Siang" if 12 <= jam < 15 else "Selamat Sore" if 15 <= jam < 18 else "Selamat Malam"
    chat_type = update.message.chat.type
    
    if chat_type == 'private':
        welcome_text = f"🏠 **Smart RT Dashboard (Private)**\n{greeting} warga! Silakan pilih layanan:"
        keyboard = [
            [InlineKeyboardButton("💰 Lapor Kas", callback_data='lapor'), InlineKeyboardButton("📊 Cek Kas", callback_data='kas')],
            [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')]
        ]
    else:
        welcome_text = f"🏠 **Smart RT Dashboard (Group)**\n{greeting} semuanya! Berikut menu akses publik:"
        keyboard = [
            [InlineKeyboardButton("📊 Cek Kas RT", callback_data='kas')],
            [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')]
        ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

# --- 4. KAS RT LOGIC (Anti-Korupsi) ---
async def lapor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Masukkan nominal pembayaran (angka saja):")
    return INPUT_NOMINAL

async def input_nominal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("Mohon masukkan angka saja!")
        return INPUT_NOMINAL
    context.user_data['nominal'] = int(update.message.text)
    await update.message.reply_text("Sekarang, kirim foto bukti transfernya:")
    return UPLOAD_BUKTI

async def upload_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = update.message.photo[-1].file_id
    nominal = context.user_data.get('nominal', 0)
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data='app_yes'), InlineKeyboardButton("❌ Reject", callback_data='app_no')]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file, 
                                 caption=f"⚠️ **Laporan Kas Baru!**\nNominal: Rp {nominal:,}\nUser: {update.message.from_user.first_name}\n\nApprove?",
                                 reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("Laporan terkirim ke Pak RT.")
    return ConversationHandler.END

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global KAS_RT
    query = update.callback_query
    await query.answer()
    try: nominal = int(query.message.caption.split("Nominal: Rp ")[1].split("\n")[0].replace(",", ""))
    except: nominal = 0
    if query.data == 'app_yes':
        KAS_RT += nominal
        await query.edit_message_caption(caption=f"✅ Approved!\nTotal Kas: Rp {KAS_RT:,}")
    else: await query.edit_message_caption(caption="❌ Laporan ditolak.")

# --- 5. MAIN EXECUTION ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.job_queue.run_repeating(check_ai_status, interval=10, first=5)
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lapor_start, pattern='lapor')],
        states={INPUT_NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_nominal)],
                UPLOAD_BUKTI: [MessageHandler(filters.PHOTO, upload_bukti)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_approval, pattern='app_'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"🅿️ *Status:* {PARKIR_STATUS}"), pattern='parkir'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"📊 Saldo: Rp {KAS_RT:,}"), pattern='kas'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    
    app.run_polling()
