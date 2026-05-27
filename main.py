python
import os
import telebot
import google.generativeai as genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-2.0-flash")

@bot.message_handler(func=lambda message: True)
def reply(message):
    try:
        response = model.generate_content(message.text)

        bot.reply_to(message, response.text)

    except Exception as e:
        bot.reply_to(message, f"Error 😭\n{str(e)}")

print("Bot nyala 😹")

bot.infinity_polling()
```
