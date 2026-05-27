import os
import logging
from google import genai
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

# Inisialisasi Client Library yang resmi
client = genai.Client(api_key=os.getenv('AI_TOKEN'))

async def ai_handler(update, context):
    try:
        # Panggilan menggunakan SDK client library
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=update.message.text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Error SDK: {str(e)}")

async def start(update, context):
    await update.message.reply_text("Smart RT siap membantu!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(os.getenv('TELEGRAM_TOKEN')).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    app.run_polling()
