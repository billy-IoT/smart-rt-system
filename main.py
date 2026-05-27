import os
import telebot
from groq import Groq

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

client = Groq(
    api_key=GROQ_API_KEY
)

@bot.message_handler(func=lambda message: True)
def reply(message):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": message.text,
                }
            ],
            model="llama-3.3-70b-versatile",
        )

        answer = chat_completion.choices[0].message.content

        bot.reply_to(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Error 😭\n{str(e)}")

print("Bot nyala 😹")

bot.infinity_polling()
