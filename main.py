import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Ambil token dari Railway Variables
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID') or 0)

# Fungsi untuk menu utama
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Cek Kas RT", callback_data='kas')],
        [InlineKeyboardButton("🅿️ Info Parkir", callback_data='parkir')],
        [InlineKeyboardButton("ℹ️ Tentang Sistem", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Halo! Selamat datang di Smart RT Dashboard. Silakan pilih menu di bawah:", reply_markup=reply_markup)

# Fungsi untuk menangani klik tombol
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Menghapus menu setelah diklik
    await query.edit_message_reply_markup(reply_markup=None)

    # Jawaban sesuai menu
    if query.data == 'kas':
        await query.edit_message_text("📊 **Info Kas RT:**\nSaldo saat ini: Rp 5.000.000,- (Data diperbarui real-time).")
    elif query.data == 'parkir':
        await query.edit_message_text("🅿️ **Info Parkir:**\nArea parkir saat ini terpantau aman dan tertib.")
    elif query.data == 'info':
        await query.edit_message_text("ℹ️ **Smart RT System**\nSistem monitoring berbasis AI untuk lingkungan lebih aman.")

if __name__ == '__main__':
    print("Bot sedang berjalan...")
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    
    app.run_polling()
