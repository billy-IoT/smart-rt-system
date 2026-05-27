import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Welcome Text
    welcome_text = (
        "🏠 **Selamat Datang di Smart RT Dashboard!**\n\n"
        "Halo warga! Sistem ini membantu pemantauan kas RT "
        "dan ketertiban parkir secara real-time.\n"
        "Silakan pilih menu di bawah untuk mulai:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 Lapor Uang Masuk", callback_data='lapor')],
        [InlineKeyboardButton("📊 Cek Kas RT", callback_data='kas')],
        [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')]
    ]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def lapor_uang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data='app_yes'),
         InlineKeyboardButton("❌ Reject", callback_data='app_no')]
    ]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text="⚠️ Laporan Uang Masuk Baru!\nJumlah: Rp 50.000\nApprove sekarang?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await query.edit_message_text("Laporan sudah dikirim ke Pak RT.")

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("Maaf, hanya Pak RT!", show_alert=True)
        return
    status = "di-approve" if query.data == 'app_yes' else "ditolak"
    await query.edit_message_text(f"✅ Laporan {status}.")

async def menu_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'kas':
        await query.edit_message_text("📊 Saldo Kas RT: Rp 5.000.000")
    elif query.data == 'parkir':
        await query.edit_message_text("🅿️ Parkir: Aman.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(lapor_uang, pattern='lapor'))
    app.add_handler(CallbackQueryHandler(handle_approval, pattern='app_'))
    app.add_handler(CallbackQueryHandler(menu_info, pattern='kas|parkir'))
    app.run_polling()
