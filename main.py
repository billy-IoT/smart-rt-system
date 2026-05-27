import os
import logging
import google.generativeai as genai
from telegram.ext import ApplicationBuilder, CommandHandler

logging.basicConfig(level=logging.INFO)

# 1. Konfigurasi
API_KEY = os.getenv('AI_TOKEN')
genai.configure(api_key=API_KEY)

# 2. Fungsi Detektif
def print_available_models():
    print("--- DAFTAR MODEL YANG TERSEDIA UNTUK API KEY INI ---")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_methods:
                print(f"Model: {m.name}")
    except Exception as e:
        print(f"Gagal akses API: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Cek log Railway untuk melihat daftar model!")

if __name__ == '__main__':
    # Jalankan detektif sebelum bot jalan
    print_available_models()
    
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_TOKEN')).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()
