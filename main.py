from __future__ import annotations
import os
import uuid
import threading
import datetime
import re
import logging
import signal
import sys
import queue
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass

import telebot
from groq import Groq

# =====================================================================
# 1. CONFIGURATION & LOGGING
# =====================================================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger("SATRIA_ENTERPRISE")

class ConfigurationManager:
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "")
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.admin_id = str(os.getenv("ADMIN_ID", ""))
        self.group_id = str(os.getenv("CHAT_ID_GRUP", ""))
        
        if not self.bot_token or not self.groq_key:
            logger.critical("BOT_TOKEN atau GROQ_API_KEY belum di-set di Environment Variable!")
            sys.exit(1)

config = ConfigurationManager()

# =====================================================================
# 2. MODELS
# =====================================================================
@dataclass(slots=True)
class User:
    id: str
    telegram_id: str
    full_name: str
    username: str
    created_at: datetime.datetime

# =====================================================================
# 3. REPOSITORIES (Database Sementara / In-Memory)
# =====================================================================
class UserRepository:
    def __init__(self):
        self._db: Dict[str, User] = {}
        self._lock = threading.RLock()

    def save(self, user: User) -> None:
        with self._lock:
            self._db[user.id] = user

    def find_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        with self._lock:
            for u in self._db.values():
                if u.telegram_id == str(telegram_id): return u
        return None

    def find_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            for u in self._db.values():
                if u.username and u.username.lower() == username.lower(): return u
        return None

# =====================================================================
# 4. SERVICES (Logika Utama)
# =====================================================================
class AIOrchestrator:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "Anda adalah SATRIA, asisten RT digital. Jawab dengan ringkas dan sopan."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return "Mohon maaf, sistem AI sedang gangguan."

class StateMachine:
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def set_state(self, tid: str, key: str, value: Any) -> None:
        with self._lock:
            if tid not in self._states: self._states[tid] = {}
            self._states[tid][key] = value

    def get_state(self, tid: str, key: str) -> Any:
        with self._lock:
            return self._states.get(tid, {}).get(key)

    def clear_state(self, tid: str) -> None:
        with self._lock:
            self._states.pop(tid, None)

class BackgroundQueueWorker:
    def __init__(self):
        self.queue = queue.Queue()
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self) -> None:
        while True:
            task = self.queue.get()
            try: task()
            except Exception as e: logger.error(f"Task Failed: {e}")
            finally: self.queue.task_done()

    def submit(self, task: Callable) -> None:
        self.queue.put(task)

# =====================================================================
# 5. HANDLERS (Alur Fitur)
# =====================================================================
class IuranHandler:
    def __init__(self, bot: telebot.TeleBot, sm: StateMachine):
        self.bot = bot
        self.sm = sm

    def initiate(self, tid: str, message: telebot.types.Message) -> None:
        self.sm.set_state(tid, "flow", "IURAN")
        self.sm.set_state(tid, "step", "NAMA")
        self.bot.reply_to(message, "📝 Silahkan masukkan *Nama Lengkap Penyetor*:", parse_mode="Markdown")

    def process(self, tid: str, message: telebot.types.Message) -> bool:
        if self.sm.get_state(tid, "flow") != "IURAN": return False
        
        step = self.sm.get_state(tid, "step")
        
        if step == "NAMA":
            if not message.text:
                self.bot.reply_to(message, "Harap ketik nama Anda.")
                return True
            self.sm.set_state(tid, "nama", message.text)
            self.sm.set_state(tid, "step", "KATEGORI")
            self.bot.reply_to(message, "Pilih Kategori Iuran (Ketik: Kebersihan / Keamanan):")
            
        elif step == "KATEGORI":
            if not message.text:
                self.bot.reply_to(message, "Harap ketik kategori.")
                return True
            self.sm.set_state(tid, "kategori", message.text)
            self.sm.set_state(tid, "step", "NOMINAL")
            self.bot.reply_to(message, "Masukkan Nominal Transfer (Contoh: 50000):")
            
        elif step == "NOMINAL":
            if not message.text or not message.text.isdigit():
                self.bot.reply_to(message, "Nominal harus angka. Coba lagi:")
                return True
            self.sm.set_state(tid, "nominal", message.text)
            self.sm.set_state(tid, "step", "FOTO")
            self.bot.reply_to(message, "Kirimkan *Foto Bukti Transfer* 📸:", parse_mode="Markdown")
            
        elif step == "FOTO":
            if not message.photo:
                self.bot.reply_to(message, "Harap kirimkan gambar bukti transfer.")
                return True
            
            nama = self.sm.get_state(tid, "nama")
            nominal = self.sm.get_state(tid, "nominal")
            self.sm.clear_state(tid)
            self.bot.reply_to(message, f"✅ Data Iuran Tersimpan!\nNama: {nama}\nNominal: Rp{nominal}\nMenunggu verifikasi admin.")
            
        return True

class MentionHandler:
    def __init__(self, ai: AIOrchestrator, bot: telebot.TeleBot, user_repo: UserRepository):
        self.ai = ai
        self.bot = bot
        self.user_repo = user_repo

    def process_mentions(self, text: str, sender_name: str):
        usernames = re.findall(r"@(\w+)", text)
        for uname in usernames:
            target = self.user_repo.find_by_username(uname)
            if target:
                prompt = f"Buat notifikasi singkat buat {target.full_name} yang di-tag oleh {sender_name} di laporan ini: '{text}'"
                ai_msg = self.ai.generate_response(prompt)
                
                # Japri User
                try: self.bot.send_message(target.telegram_id, f"🔔 Notifikasi:\n{ai_msg}")
                except: pass
                
                # Tembus ke Grup
                if config.group_id:
                    try: self.bot.send_message(config.group_id, f"📩 Info untuk @{uname}:\n{ai_msg}")
                    except: pass

# =====================================================================
# 6. APPLICATION FACTORY (Pusat Bot)
# =====================================================================
class SATRIAApp:
    def __init__(self):
        self.bot = telebot.TeleBot(config.bot_token)
        self.user_repo = UserRepository()
        self.ai = AIOrchestrator(config.groq_key)
        self.sm = StateMachine()
        self.worker = BackgroundQueueWorker()
        
        self.iuran_handler = IuranHandler(self.bot, self.sm)
        self.mention_handler = MentionHandler(self.ai, self.bot, self.user_repo)

    def setup_routes(self):
        @self.bot.message_handler(commands=['start'])
        def handle_start(message: telebot.types.Message):
            tid = str(message.from_user.id)
            user = self.user_repo.find_by_telegram_id(tid)
            
            # FIXED: message.from_user.username instead of message.username
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    telegram_id=tid,
                    full_name=message.from_user.first_name or "Warga",
                    username=message.from_user.username or "",
                    created_at=datetime.datetime.now()
                )
                self.user_repo.save(user)
            
            kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add("💰 Lapor Iuran", "📋 Lapor Masalah")
            self.bot.reply_to(message, "SATRIA Enterprise Siap Digunakan.", reply_markup=kb)

        @self.bot.message_handler(content_types=['text', 'photo'])
        def handle_all(message: telebot.types.Message):
            tid = str(message.from_user.id)
            
            # FIXED: message.from_user.username
            user = self.user_repo.find_by_telegram_id(tid)
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    telegram_id=tid,
                    full_name=message.from_user.first_name or "Warga",
                    username=message.from_user.username or "",
                    created_at=datetime.datetime.now()
                )
                self.user_repo.save(user)

            # 1. Cek apakah user sedang dalam proses Iuran
            if self.iuran_handler.process(tid, message):
                return

            text = message.text or message.caption or ""
            
            # 2. Cek Menu Iuran
            if text == "💰 Lapor Iuran":
                self.iuran_handler.initiate(tid, message)
                return
                
            # 3. Cek Menu Laporan & Scan Mention
            elif "lapor" in text.lower() or "masalah" in text.lower() or "keluhan" in text.lower():
                self.bot.reply_to(message, "✅ Laporan Anda telah dicatat.")
                if config.group_id:
                    try: self.bot.send_message(config.group_id, f"📢 Laporan dari {user.full_name}:\n{text}")
                    except: pass
                self.mention_handler.process_mentions(text, user.full_name)
                return

            # 4. AI Chat (Jika Bot di-tag atau di Private Chat)
            bot_me = self.bot.get_me().username
            if (bot_me and f"@{bot_me}" in text) or message.chat.type == "private":
                def ai_task():
                    response = self.ai.generate_response(f"Bantu jawab: {text}")
                    self.bot.reply_to(message, response)
                self.worker.submit(ai_task)

    def run(self):
        logger.info("Bot is polling...")
        
        def shutdown(sig, frame):
            logger.info("Shutting down...")
            self.bot.stop_polling()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
        
        self.bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    app = SATRIAApp()
    app.setup_routes()
    app.run()
