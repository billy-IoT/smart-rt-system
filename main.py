import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from dotenv import load_dotenv

# Load data rahasia dari .env
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

# Logging biar kamu bisa pantau error di console
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek Security Layer (Whitelist ID)
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Akses ditolak! Kamu bukan admin.")
        return

    # Menu yang muncul
    keyboard = [
        [InlineKeyboardButton("📊 Cek Kas RT", callback_data='cek_kas')],
        [InlineKeyboardButton("➕ Tambah Iuran", callback_data='tambah_iuran')],
        [InlineKeyboardButton("⚙️ Status Sistem", callback_data='status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Halo Pak RT! Selamat datang di Sistem Smart RT. Pilih menu:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Biar loading-nya ilang

    # Hapus pesan menu (dissapear menu)
    await query.delete_message()

    # Logika isi jawaban setelah ditekan
    if query.data == 'cek_kas':
        await query.message.reply_text("💰 Saldo Kas RT saat ini: Rp 5.000.000")
    elif query.data == 'tambah_iuran':
        await query.message.reply_text("Silakan masukkan jumlah iuran (Contoh: /input 50000)")
    elif query.data == 'status':
        await query.message.reply_text("✅ Sistem Monitoring: AKTIF\n✅ ESP32-CAM: TERKONEKSI")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot sedang berjalan...")
    app.run_polling()