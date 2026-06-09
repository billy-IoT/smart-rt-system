from __future__ import annotations
import os, time, uuid, threading, datetime, re, logging, telebot, signal, sys, json, queue
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from groq import Groq

# --- 1. ENTERPRISE LOGGING & CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | [%(name)s] | %(message)s')
logger = logging.getLogger("SATRIA_ENTERPRISE_PRO")

class Config:
    def __init__(self):
        self.token = os.getenv("BOT_TOKEN", "")
        self.key = os.getenv("GROQ_API_KEY", "")
        self.admin = str(os.getenv("ADMIN_ID", ""))
        self.group = str(os.getenv("CHAT_ID_GRUP", ""))
        if not self.token or not self.key: raise EnvironmentError("ENV VARS MISSING")

config = Config()

# --- 2. DATA TRANSFER OBJECTS (DTOs) ---
@dataclass(slots=True)
class UserDTO:
    tid: str; name: str; username: str

@dataclass(slots=True)
class ReportDTO:
    user_id: str; content: str; type: str

# --- 3. MODELS & ENUMS ---
class SessionState(str, Enum): 
    NONE = "NONE"; WAITING_NAME = "WAITING_NAME"; 
    WAITING_CATEGORY = "WAITING_CATEGORY"; WAITING_AMOUNT = "WAITING_AMOUNT"; WAITING_PHOTO = "WAITING_PHOTO"

@dataclass(slots=True)
class User:
    id: str; telegram_id: str; full_name: str; username: str; role: str; created_at: datetime.datetime

# --- 4. REPOSITORIES (Data Access Layer) ---
class UserRepository:
    def __init__(self):
        self._db: Dict[str, User] = {}
        self._lock = threading.RLock()
    def save(self, user: User):
        with self._lock: self._db[user.id] = user
    def find_by_tid(self, tid: str):
        with self._lock:
            for u in self._db.values():
                if u.telegram_id == str(tid): return u
        return None
    def find_by_uname(self, uname: str):
        with self._lock:
            for u in self._db.values():
                if u.username and u.username.lower() == uname.lower(): return u
        return None

# --- 5. SERVICES (Business Logic Layer) ---
class AIOrchestrator:
    def __init__(self, key: str): 
        self.client = Groq(api_key=key)
        logger.info("AI Service Initialized.")
    def generate(self, prompt: str) -> str:
        try:
            res = self.client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "user", "content": prompt}])
            return res.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Service Error: {e}")
            return "AI Error"

class StateMachine:
    def __init__(self): self._states: Dict[str, dict] = {}; self._lock = threading.RLock()
    def set(self, uid: str, k: str, v: Any):
        with self._lock:
            if uid not in self._states: self._states[uid] = {}
            self._states[uid][k] = v
            logger.info(f"State stored: {uid} -> {k}")
    def get(self, uid: str, k: str):
        with self._lock: return self._states.get(uid, {}).get(k)
    def reset(self, uid: str):
        with self._lock: self._states.pop(uid, None)

# --- 6. HANDLERS (Traffic Controller) ---
class IuranHandler:
    def __init__(self, bot, sm): self.bot = bot; self.sm = sm
    def initiate(self, uid: str, m):
        self.sm.set(uid, "stage", SessionState.WAITING_NAME)
        self.bot.reply_to(m, "📝 Masukkan Nama Penyetor:")
    def handle(self, uid: str, m) -> bool:
        stage = self.sm.get(uid, "stage")
        if not stage: return False
        
        if stage == SessionState.WAITING_NAME:
            self.sm.set(uid, "stage", SessionState.WAITING_CATEGORY)
            self.bot.reply_to(m, "Pilih Kategori (Kebersihan/Keamanan):")
        elif stage == SessionState.WAITING_CATEGORY:
            self.sm.set(uid, "stage", SessionState.WAITING_AMOUNT)
            self.bot.reply_to(m, "Masukkan Nominal:")
        elif stage == SessionState.WAITING_AMOUNT:
            self.sm.set(uid, "stage", SessionState.WAITING_PHOTO)
            self.bot.reply_to(m, "Kirim foto bukti transfer:")
        elif stage == SessionState.WAITING_PHOTO:
            if m.photo: self.sm.reset(uid); self.bot.reply_to(m, "✅ Iuran tercatat.")
            else: self.bot.reply_to(m, "Kirim foto!")
        return True

# --- 7. BOOTSTRAPPER (The Application Factory) ---
class SATRIAApp:
    def __init__(self):
        self.bot = telebot.TeleBot(config.token)
        self.user_repo = UserRepository()
        self.sm = StateMachine()
        self.iuran = IuranHandler(self.bot, self.sm)
        self.ai = AIOrchestrator(config.key)
        self.queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        while True:
            task = self.queue.get()
            try: task()
            finally: self.queue.task_done()

    def setup_routes(self):
        @self.bot.message_handler(commands=['start'])
        def start(m):
            user = User(str(uuid.uuid4()), str(m.from_user.id), m.from_user.first_name, m.username or "", "WARGA", datetime.datetime.now())
            self.user_repo.save(user)
            kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add("💰 Lapor Iuran", "📋 Lapor Masalah")
            self.bot.reply_to(m, "SATRIA Enterprise v4.0 Active.", reply_markup=kb)

        @self.bot.message_handler(content_types=['text', 'photo'])
        def main_router(m):
            tid = str(m.from_user.id)
            if self.iuran.handle(tid, m): return
            
            text = m.text or m.caption or ""
            if text == "💰 Lapor Iuran": self.iuran.initiate(tid, m); return
            
            # AI Mention Logic
            if "@" in text:
                for uname in re.findall(r"@(\w+)", text):
                    target = self.user_repo.find_by_uname(uname)
                    if target:
                        draft = self.ai.generate(f"Buat notif buat @{uname} terkait laporan: {text}")
                        self.bot.send_message(target.telegram_id, f"🔔 {draft}")
                        if config.group: self.bot.send_message(config.group, f"📩 Notif @{uname}: {draft}")
            
            # AI Chatbot
            if (self.bot.get_me().username in text) or m.chat.type == "private":
                self.queue.put(lambda: self.bot.reply_to(m, self.ai.generate(text)))

    def run(self):
        logger.info("SATRIA Enterprise V4.0 Online.")
        self.bot.infinity_polling()

if __name__ == "__main__":
    app = SATRIAApp()
    app.setup_routes()
    app.run()
