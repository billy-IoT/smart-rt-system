import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          MessageHandler, filters, ContextTypes, ConversationHandler)

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)

# State & Global Data
INPUT_NOMINAL, UPLOAD_BUKTI, GARANSI_DESC = range(3)
KAS_RT = 5000000
PARKIR_STATUS = "🟢 Buka"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Logika Dynamic Greeting
    jam = datetime.now().hour
    if 5 <= jam < 12: greeting = "Selamat Pagi"
    elif 12 <= jam < 15: greeting = "Selamat Siang"
    elif 15 <= jam < 18: greeting = "Selamat Sore"
    else: greeting = "Selamat Malam"
        
    welcome_text = f"🏠 **Smart RT Dashboard**\n{greeting} warga! Silakan pilih menu:"
    
    keyboard = [
        [InlineKeyboardButton("💰 Lapor Bayar Kas", callback_data='lapor'), InlineKeyboardButton("📊 Cek Kas", callback_data='kas')],
        [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir'), InlineKeyboardButton("🛠 Garansi/Lapor", callback_data='garansi')],
        [InlineKeyboardButton("📷 Cek Kondisi AI", callback_data='cek_ai')]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

# --- KAS RT LOGIC ---
async def lapor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Masukkan nominal pembayaran (angka saja, contoh: 50000):")
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
    
    keyboard = [[InlineKeyboardButton("✅ Approve", callback_data='app_yes'),
                 InlineKeyboardButton("❌ Reject", callback_data='app_no')]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_file,
        caption=f"⚠️ **Laporan Kas Baru!**\nNominal: Rp {nominal:,}\nUser: {update.message.from_user.first_name}\n\nApprove?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Laporan dikirim ke Pak RT.")
    return ConversationHandler.END

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global KAS_RT
    query = update.callback_query
    await query.answer()
    
    if query.data == 'app_yes':
        KAS_RT += 50000 # Dummy increment
        await query.edit_message_caption(caption=f"✅ Laporan di-approve! Saldo Kas RT: Rp {KAS_RT:,}")
    else:
        await query.edit_message_caption(caption="❌ Laporan ditolak.")

# --- PARKIR, GARANSI & AI LOGIC ---
async def info_parkir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔄 Toggle Status", callback_data='toggle')]] if query.from_user.id == ADMIN_ID else []
    await query.edit_message_text(f"🅿️ *Status Parkir:* {PARKIR_STATUS}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def toggle_parkir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PARKIR_STATUS
    PARKIR_STATUS = "🔴 Tutup" if PARKIR_STATUS == "🟢 Buka" else "🟢 Buka"
    await update.callback_query.answer("Status diubah!")
    await info_parkir(update, context)

async def garansi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Tuliskan deskripsi kerusakan/garansi yang ingin dilaporkan:")
    return GARANSI_DESC

async def garansi_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    laporan = update.message.text
    await context.bot.send_message(ADMIN_ID, f"🛠 *Laporan Baru:*\n{laporan}", parse_mode='Markdown')
    await update.message.reply_text("Laporan diteruskan ke Pak RT!")
    return ConversationHandler.END

async def cek_ai_simulasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🤖 **Analisis AI Terakhir:**\nStatus: Aman.\nWaktu Scan: " + datetime.now().strftime("%d %b %Y, %H:%M WIB"))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lapor_start, pattern='lapor'), CallbackQueryHandler(garansi_start, pattern='garansi')],
        states={
            INPUT_NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_nominal)],
            UPLOAD_BUKTI: [MessageHandler(filters.PHOTO, upload_bukti)],
            GARANSI_DESC: [MessageHandler(filters.TEXT, garansi_input)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_approval, pattern='app_'))
    app.add_handler(CallbackQueryHandler(info_parkir, pattern='parkir'))
    app.add_handler(CallbackQueryHandler(toggle_parkir, pattern='toggle'))
    app.add_handler(CallbackQueryHandler(cek_ai_simulasi, pattern='cek_ai'))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text(f"📊 Saldo: Rp {KAS_RT:,}"), pattern='kas'))
    
    app.run_polling()
