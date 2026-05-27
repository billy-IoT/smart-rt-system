import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Setup Logging agar kamu bisa cek error di Railway Logs
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)

# 1. Menu Utama (User)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Lapor Uang Masuk", callback_data='lapor')],
        [InlineKeyboardButton("📊 Cek Kas RT", callback_data='kas')],
        [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')]
    ]
    await update.message.reply_text("Halo Warga! Ada yang bisa dibantu hari ini?", reply_markup=InlineKeyboardMarkup(keyboard))

# 2. Logic: User Lapor Uang
async def lapor_uang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Kirim tombol approval ke Pak RT (ADMIN_ID)
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data='app_yes'),
         InlineKeyboardButton("❌ Reject", callback_data='app_no')]
    ]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text="⚠️ **Laporan Uang Masuk Baru!**\nUser: "+str(query.from_user.first_name)+"\nJumlah: Rp 50.000\n\nApprove sekarang?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await query.edit_message_text("Laporan sudah dikirim ke Pak RT. Sedang diverifikasi...")

# 3. Logic: Admin (Pak RT) Approve/Reject
async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Cek apakah yang klik benar Admin
    if query.from_user.id != ADMIN_ID:
        await query.answer("Maaf, hanya Pak RT yang bisa melakukan ini!", show_alert=True)
        return

    if query.data == 'app_yes':
        await query.edit_message_text("✅ Laporan di-approve. Dana masuk ke kas RT!")
    else:
        await query.edit_message_text("❌ Laporan ditolak.")

# 4. Logic: Cek Kas & Parkir
async def menu_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'kas':
        await query.edit_message_text("📊 Saldo Kas RT saat ini: Rp 5.000.000")
    elif query.data == 'parkir':
        await query.edit_message_text("🅿️ Kondisi Parkir: Aman & Terkendali.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(lapor_uang, pattern='lapor'))
    app.add_handler(CallbackQueryHandler(handle_approval, pattern='app_'))
    app.add_handler(CallbackQueryHandler(menu_info, pattern='kas|parkir'))
    
    app.run_polling()        await query.edit_message_text("ℹ️ **Smart RT System**\nSistem monitoring berbasis AI untuk lingkungan lebih aman.")

if __name__ == '__main__':
    print("Bot sedang berjalan...")
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    
    app.run_polling()
