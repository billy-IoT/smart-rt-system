import os
import telebot
from telebot import types
from groq import Groq
import re
import datetime
import pytz

# =========================
# KONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

client = Groq(
    api_key=GROQ_API_KEY
)

# =========================
# DATABASE SEMENTARA
# =========================
kas_rt = {"total": 0}

warga_database = {}

user_states = {}

pending_approvals = {}

chat_history = {}

muted_users = set()

spam_counter = {}

# =========================
# HELPER
# =========================
def get_role(uid):
    return "Pak RT" if str(uid) == ADMIN_ID else "Warga"

def get_greeting():
    wib = pytz.timezone('Asia/Jakarta')
    hour = datetime.datetime.now(wib).hour

    if 5 <= hour < 12:
        return "Pagi"
    elif 12 <= hour < 15:
        return "Siang"
    elif 15 <= hour < 19:
        return "Sore"
    else:
        return "Malam"

def is_bot_target(message):
    uid = str(message.from_user.id)

    if get_role(uid) == "Pak RT":
        return True

    if message.chat.type == "private":
        return True

    if message.reply_to_message:
        if message.reply_to_message.from_user.is_bot:
            return True

    if message.text:
        username_bot = bot.get_me().username
        if f"@{username_bot}" in message.text:
            return True

    return False

def broadcast_message(text):
    for uid in warga_database:
        try:
            bot.send_message(
                uid,
                f"📢 Pengumuman RT\n\n{text}"
            )
        except:
            pass

# =========================
# START
# =========================
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)

    warga_database[uid] = {
        "name": message.from_user.first_name,
        "username": message.from_user.username
    }

    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    markup.row(
        "💰 Lapor Iuran",
        "📋 Cek Kas"
    )

    bot.reply_to(
        message,
        f"Selamat {get_greeting()} \n\nSmart RT siap bantu. Pilih menu di bawah.",
        reply_markup=markup
    )

# =========================
# HANDLER UTAMA
# =========================
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):

    uid = str(message.from_user.id)

    text = (
        message.text
        or message.caption
        or ""
    )

    role = get_role(uid)

    # =====================
    # USER STATE
    # =====================
    if uid in user_states:
        handle_lapor_steps(message)
        return

    # =====================
    # ADMIN COMMAND
    # =====================
    if role == "Pak RT":

        if text.startswith("/bc "):

            isi = text.replace("/bc ", "")

            broadcast_message(isi)

            bot.reply_to(
                message,
                "✅ Broadcast terkirim."
            )

            return

        if text.startswith("/mute "):

            target = text.split(" ")[1].replace("@", "")

            muted_users.add(target)

            bot.reply_to(
                message,
                f"✅ @{target} dimute."
            )

            return

    # =====================
    # ANTI SPAM
    # =====================
    if uid in muted_users:
        return

    spam_counter[uid] = spam_counter.get(uid, 0) + 1

    if spam_counter[uid] > 10:

        muted_users.add(uid)

        bot.reply_to(
            message,
            "🚫 Lu kena mute gara gara spam 😭"
        )

        return

    # =====================
    # LAPORAN
    # =====================
    if "lapor" in text.lower() or "parkir" in text.lower():

        mentioned = re.findall(r'@(\w+)', text)

        for username in mentioned:

            target_uid = next(
                (
                    u for u, data
                    in warga_database.items()
                    if data.get('username') == username
                ),
                None
            )

            if target_uid:

                try:

                    bot.send_message(
                        target_uid,
                        f"⚠️ Ada laporan terkait lu:\n\n{text}"
                    )

                    bot.reply_to(
                        message,
                        f"✅ Laporan ke @{username} udh dikirim."
                    )

                except:

                    bot.reply_to(
                        message,
                        f"❌ Gagal kirim ke @{username}"
                    )

    # =====================
    # MENU
    # =====================
    if text == "💰 Lapor Iuran":

        user_states[uid] = {
            "state": "WAITING_NAME"
        }

        bot.reply_to(
            message,
            "Masukin nama lengkap lu:"
        )

        return

    elif text == "📋 Cek Kas":

        bot.reply_to(
            message,
            f"💰 Kas RT sekarang:\nRp {kas_rt['total']:,}"
        )

        return

    # =====================
    # AI CHAT
    # =====================
    if is_bot_target(message):

        if uid not in chat_history:
            chat_history[uid] = []

        chat_history[uid].append({
            "role": "user",
            "content": text
        })

        system_prompt = f"""
Lu adalah bot AI grup RT Gen Z.

Cara ngobrol:
- santai
- natural
- singkat
- jangan formal
- jangan terlalu panjang
- jangan pake poin poin kecuali diminta
- jangan ngomong kayak customer service
- jangan ngulang jawaban
- jangan nutup jawaban dengan pertanyaan aneh
- respon kayak manusia biasa chat

Boleh lucu dikit 
Boleh roasting tipis tapi tetep sopan.

Info user:
Nama: {warga_database.get(uid, {}).get('name', 'Warga')}
Role: {role}

Kas RT sekarang:
Rp {kas_rt['total']:,}
"""

        try:

            res = client.chat.completions.create(

                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    *chat_history[uid][-6:]
                ],

                model="llama-3.1-8b-instant",

                temperature=0.8,

                max_tokens=120
            )

            answer = res.choices[0].message.content

            chat_history[uid].append({
                "role": "assistant",
                "content": answer
            })

            bot.reply_to(
                message,
                answer
            )

        except Exception as e:

            bot.reply_to(
                message,
                f"Error \n{str(e)}"
            )

# =========================
# FLOW IURAN
# =========================
def handle_lapor_steps(message):

    uid = str(message.from_user.id)

    state = user_states[uid]["state"]

    # =====================
    # NAMA
    # =====================
    if state == "WAITING_NAME":

        warga_database[uid]["name"] = message.text

        user_states[uid] = {
            "state": "WAITING_CATEGORY",
            "nama": message.text
        }

        bot.reply_to(
            message,
            "Pilih kategori:\n1. Kebersihan\n2. Keamanan\n3. Lain-lain"
        )

    # =====================
    # KATEGORI
    # =====================
    elif state == "WAITING_CATEGORY":

        cat_map = {
            "1": "Kebersihan",
            "2": "Keamanan",
            "3": "Lain-lain"
        }

        if message.text in cat_map:

            user_states[uid]["kategori"] = cat_map[message.text]

            if message.text == "3":

                user_states[uid]["state"] = "WAITING_DESC"

                bot.reply_to(
                    message,
                    "Masukin keterangannya:"
                )

            else:

                user_states[uid]["state"] = "WAITING_AMOUNT"

                bot.reply_to(
                    message,
                    "Masukin nominal iuran:"
                )

        else:

            bot.reply_to(
                message,
                "Pilih 1, 2, atau 3"
            )

    # =====================
    # DESKRIPSI
    # =====================
    elif state == "WAITING_DESC":

        user_states[uid]["keterangan"] = message.text

        user_states[uid]["state"] = "WAITING_AMOUNT"

        bot.reply_to(
            message,
            "Masukin nominal iuran:"
        )

    # =====================
    # NOMINAL
    # =====================
    elif state == "WAITING_AMOUNT":

        raw = re.sub(r'\D', '', message.text)

        if raw.isdigit() and int(raw) >= 10000:

            user_states[uid]["jumlah"] = int(raw)

            user_states[uid]["state"] = "WAITING_PHOTO"

            bot.reply_to(
                message,
                "Kirim foto bukti transfer"
            )

        else:

            bot.reply_to(
                message,
                "Minimal Rp10.000"
            )

    # =====================
    # FOTO
    # =====================
    elif state == "WAITING_PHOTO":

        if message.photo:

            data = user_states[uid]

            pending_approvals[uid] = data

            markup = types.InlineKeyboardMarkup()

            markup.add(
                types.InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_{uid}"
                ),

                types.InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_{uid}"
                )
            )

            ket = ""

            if "keterangan" in data:
                ket = f"\nKeterangan: {data['keterangan']}"

            bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id,

                caption=(
                    f"💰 Laporan Iuran\n\n"
                    f"Nama: {data['nama']}\n"
                    f"Kategori: {data['kategori']}\n"
                    f"Nominal: Rp {data['jumlah']:,}"
                    f"{ket}"
                ),

                reply_markup=markup
            )

            bot.reply_to(
                message,
                "✅ Laporan terkirim ke Pak RT."
            )

            del user_states[uid]

        else:

            bot.reply_to(
                message,
                "Kirim foto bukti transfer"
            )

# =========================
# APPROVAL
# =========================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):

    action, uid = call.data.split("_")

    if uid not in pending_approvals:
        return

    data = pending_approvals[uid]

    if action == "approve":

        kas_rt["total"] += data["jumlah"]

        bot.send_message(
            uid,
            (
                f"✅ Iuran diterima.\n\n"
                f"Kas RT sekarang:\n"
                f"Rp {kas_rt['total']:,}"
            )
        )

        bot.edit_message_caption(
            caption="✅ Iuran disetujui",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    elif action == "reject":

        bot.send_message(
            uid,
            "❌ Iuran ditolak."
        )

        bot.edit_message_caption(
            caption="❌ Iuran ditolak",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    del pending_approvals[uid]

# =========================
# RUN
# =========================
print("Bot Smart RT nyala ")

bot.infinity_polling()
