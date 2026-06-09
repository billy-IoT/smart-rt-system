from __future__ import annotations
import os
import time
import uuid
import threading
import datetime
import re
import logging
import signal
import sys
import queue
import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

import telebot
from groq import Groq

# =====================================================================
# 1. ENTERPRISE LOGGING & CONFIGURATION
# =====================================================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s | %(levelname)s | [%(name)s] | %(message)s'
)
logger = logging.getLogger("SATRIA_ENTERPRISE_SYSTEM")

class ConfigurationManager:
    """Manages all environment variables securely."""
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "")
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.admin_id = str(os.getenv("ADMIN_ID", ""))
        self.group_id = str(os.getenv("CHAT_ID_GRUP", ""))
        self.validate()

    def validate(self) -> None:
        if not self.bot_token:
            logger.critical("CRITICAL: BOT_TOKEN is missing from environment.")
            raise ValueError("BOT_TOKEN is required.")
        if not self.groq_key:
            logger.critical("CRITICAL: GROQ_API_KEY is missing from environment.")
            raise ValueError("GROQ_API_KEY is required.")
        logger.info("System Configuration successfully loaded and validated.")

config = ConfigurationManager()

# =====================================================================
# 2. DATA MODELS & ENUMS
# =====================================================================
class UserRole(str, Enum):
    WARGA = "WARGA"
    ADMIN = "ADMIN"

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class SessionState(str, Enum):
    NONE = "NONE"
    WAITING_NAME = "WAITING_NAME"
    WAITING_CATEGORY = "WAITING_CATEGORY"
    WAITING_AMOUNT = "WAITING_AMOUNT"
    WAITING_PHOTO = "WAITING_PHOTO"

@dataclass(slots=True)
class User:
    id: str
    telegram_id: str
    full_name: str
    username: str
    role: UserRole
    created_at: datetime.datetime

@dataclass(slots=True)
class CitizenReport:
    id: str
    user_id: str
    content: str
    status: ApprovalStatus
    created_at: datetime.datetime

@dataclass(slots=True)
class KasTransaction:
    id: str
    user_id: str
    full_name: str
    category: str
    amount: int
    status: ApprovalStatus
    created_at: datetime.datetime

# =====================================================================
# 3. REPOSITORY LAYER (Thread-Safe Data Access)
# =====================================================================
class UserRepository:
    def __init__(self):
        self._db: Dict[str, User] = {}
        self._lock = threading.RLock()

    def save(self, user: User) -> None:
        with self._lock:
            self._db[user.id] = user
            logger.info(f"UserRepository: Saved user {user.telegram_id}")

    def find_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        with self._lock:
            for u in self._db.values():
                if u.telegram_id == str(telegram_id):
                    return u
        return None

    def find_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            for u in self._db.values():
                if u.username and u.username.lower() == username.lower():
                    return u
        return None

    def get_all(self) -> List[User]:
        with self._lock:
            return list(self._db.values())

class ReportRepository:
    def __init__(self):
        self._db: Dict[str, CitizenReport] = {}
        self._lock = threading.RLock()

    def save(self, report: CitizenReport) -> None:
        with self._lock:
            self._db[report.id] = report
            logger.info(f"ReportRepository: Saved report {report.id}")

    def get_all(self) -> List[CitizenReport]:
        with self._lock:
            return list(self._db.values())

# =====================================================================
# 4. CORE SERVICES (Business Logic)
# =====================================================================
class AIOrchestrator:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.1-8b-instant"
        logger.info("AIOrchestrator initialized with Groq backend.")

    def generate_response(self, context_prompt: str) -> str:
        try:
            logger.info("AIOrchestrator: Sending request to Groq API...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Anda adalah SATRIA, asisten RT digital yang profesional, tegas, dan sopan."},
                    {"role": "user", "content": context_prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AIOrchestrator Critical Failure: {e}")
            return "Mohon maaf, sistem AI sedang mengalami gangguan koneksi."

class MessageGateway:
    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot

    def send_direct(self, telegram_id: str, text: str) -> None:
        try:
            self.bot.send_message(telegram_id, text, parse_mode="Markdown")
            logger.info(f"MessageGateway: Sent direct message to {telegram_id}")
        except Exception as e:
            logger.error(f"MessageGateway: Failed to send direct message to {telegram_id}. Error: {e}")

    def send_group_broadcast(self, text: str) -> None:
        if config.group_id:
            try:
                self.bot.send_message(config.group_id, text, parse_mode="Markdown")
                logger.info("MessageGateway: Broadcast sent to official group.")
            except Exception as e:
                logger.error(f"MessageGateway: Failed group broadcast. Error: {e}")

class StateMachine:
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def set_state(self, telegram_id: str, key: str, value: Any) -> None:
        with self._lock:
            if telegram_id not in self._states:
                self._states[telegram_id] = {}
            self._states[telegram_id][key] = value
            logger.info(f"StateMachine: User {telegram_id} state '{key}' updated.")

    def get_state(self, telegram_id: str, key: str) -> Any:
        with self._lock:
            return self._states.get(telegram_id, {}).get(key)

    def clear_state(self, telegram_id: str) -> None:
        with self._lock:
            self._states.pop(telegram_id, None)
            logger.info(f"StateMachine: Cleared all states for {telegram_id}.")

class BackgroundQueueWorker:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()
        logger.info("BackgroundQueueWorker: Worker thread started.")

    def _process_queue(self) -> None:
        while True:
            task = self.queue.get()
            try:
                task()
            except Exception as e:
                logger.error(f"BackgroundQueueWorker: Task execution failed: {e}")
            finally:
                self.queue.task_done()

    def submit_task(self, task: Callable) -> None:
        self.queue.put(task)

# =====================================================================
# 5. HANDLERS (Domain Logic)
# =====================================================================
class IuranWorkflowHandler:
    def __init__(self, bot: telebot.TeleBot, state_machine: StateMachine):
        self.bot = bot
        self.sm = state_machine

    def initiate_flow(self, telegram_id: str, message: telebot.types.Message) -> None:
        logger.info(f"IuranWorkflow: Initiated by {telegram_id}")
        self.sm.set_state(telegram_id, "active_flow", "IURAN")
        self.sm.set_state(telegram_id, "step", SessionState.WAITING_NAME.value)
        self.bot.reply_to(message, "📝 *Pencatatan Iuran Warga*\nSilahkan masukkan *Nama Lengkap Penyetor*:", parse_mode="Markdown")

    def intercept(self, telegram_id: str, message: telebot.types.Message) -> bool:
        flow = self.sm.get_state(telegram_id, "active_flow")
        if flow != "IURAN":
            return False
            
        step = self.sm.get_state(telegram_id, "step")
        
        if step == SessionState.WAITING_NAME.value:
            if not message.text:
                self.bot.reply_to(message, "Harap masukkan teks nama.")
                return True
            self.sm.set_state(telegram_id, "data_name", message.text)
            self.sm.set_state(telegram_id, "step", SessionState.WAITING_CATEGORY.value)
            self.bot.reply_to(message, "Pilih Kategori Iuran:\n1. Kebersihan\n2. Keamanan\n*(Ketik nama kategorinya)*")
            return True

        elif step == SessionState.WAITING_CATEGORY.value:
            if not message.text:
                self.bot.reply_to(message, "Harap masukkan teks kategori.")
                return True
            self.sm.set_state(telegram_id, "data_category", message.text)
            self.sm.set_state(telegram_id, "step", SessionState.WAITING_AMOUNT.value)
            self.bot.reply_to(message, "Masukkan Nominal Transfer (contoh: 50000)\n*Angka saja:*")
            return True

        elif step == SessionState.WAITING_AMOUNT.value:
            if not message.text or not message.text.isdigit():
                self.bot.reply_to(message, "❌ Nominal tidak valid. Harap masukkan *angka saja*.")
                return True
            self.sm.set_state(telegram_id, "data_amount", int(message.text))
            self.sm.set_state(telegram_id, "step", SessionState.WAITING_PHOTO.value)
            self.bot.reply_to(message, "Terakhir, mohon kirimkan *Foto Bukti Transfer* 📸:")
            return True

        elif step == SessionState.WAITING_PHOTO.value:
            if not message.photo:
                self.bot.reply_to(message, "❌ Sistem memerlukan foto bukti transfer. Harap kirimkan gambar.")
                return True
            
            # --- FINALISASI DATA ---
            name = self.sm.get_state(telegram_id, "data_name")
            amt = self.sm.get_state(telegram_id, "data_amount")
            
            logger.info(f"IuranWorkflow: Completed for {telegram_id}. Name: {name}, Amount: {amt}")
            self.sm.clear_state(telegram_id)
            self.bot.reply_to(message, f"✅ *Data Iuran Berhasil Disimpan*\n\nNama: {name}\nNominal: Rp{amt}\n\n*Menunggu verifikasi admin.*", parse_mode="Markdown")
            return True

        return False

class MentionEngine:
    def __init__(self, ai: AIOrchestrator, gateway: MessageGateway, user_repo: UserRepository):
        self.ai = ai
        self.gateway = gateway
        self.user_repo = user_repo

    def process_mentions_in_text(self, text: str, sender_name: str) -> None:
        usernames_found = re.findall(r"@(\w+)", text)
        if not usernames_found:
            return

        logger.info(f"MentionEngine: Detected tags {usernames_found}")
        
        for uname in usernames_found:
            target_user = self.user_repo.find_by_username(uname)
            if target_user:
                logger.info(f"MentionEngine: Target @{uname} verified. Requesting AI draft.")
                prompt = f"Buatkan pesan notifikasi sangat sopan dan profesional untuk warga bernama {target_user.full_name}. Beritahu dia bahwa dia baru saja di-tag / di-mention di sebuah laporan oleh {sender_name}. Isi laporannya adalah: '{text}'"
                
                ai_draft = self.ai.generate_response(prompt)
                
                # 1. Send Direct Message to the tagged user
                self.gateway.send_direct(target_user.telegram_id, f"🔔 *Notifikasi Perhatian*\n\n{ai_draft}")
                
                # 2. Broadcast context to Group
                self.gateway.send_group_broadcast(f"📩 *Notifikasi Otomatis untuk @{uname}:*\n\n{ai_draft}")
            else:
                logger.warning(f"MentionEngine: User @{uname} is not registered in the database.")
                self.gateway.send_group_broadcast(f"⚠️ *Peringatan Sistem:* Pengguna @{uname} belum terdaftar di sistem SATRIA. Notifikasi jalur pribadi gagal dikirim.")

# =====================================================================
# 6. APPLICATION FACTORY (Main Orchestrator)
# =====================================================================
class SATRIAEnterpriseApplication:
    def __init__(self):
        logger.info("Bootstrapping SATRIA Enterprise Architecture...")
        
        # Core Library
        self.bot = telebot.TeleBot(config.bot_token)
        
        # Repositories
        self.user_repo = UserRepository()
        self.report_repo = ReportRepository()
        
        # Services
        self.ai = AIOrchestrator(config.groq_key)
        self.gateway = MessageGateway(self.bot)
        self.state_machine = StateMachine()
        self.worker = BackgroundQueueWorker()
        
        # Handlers
        self.iuran_handler = IuranWorkflowHandler(self.bot, self.state_machine)
        self.mention_engine = MentionEngine(self.ai, self.gateway, self.user_repo)

    def _build_keyboard_menu(self) -> telebot.types.ReplyKeyboardMarkup:
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            telebot.types.KeyboardButton("💰 Lapor Iuran"),
            telebot.types.KeyboardButton("📋 Lapor Masalah")
        )
        markup.add(telebot.types.KeyboardButton("📊 Statistik Sistem"))
        return markup

    def initialize_routing(self):
        logger.info("Registering Telebot Routing...")

        @self.bot.message_handler(commands=['start'])
        def handle_start(message: telebot.types.Message):
            tid = str(message.from_user.id)
            user = self.user_repo.find_by_telegram_id(tid)
            
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    telegram_id=tid,
                    full_name=message.from_user.first_name or "Warga",
                    username=message.from_user.username or "",
                    role=UserRole.WARGA,
                    created_at=datetime.datetime.now()
                )
                self.user_repo.save(user)
            
            welcome_text = (
                f"Selamat datang, {user.full_name}!\n\n"
                "Saya adalah *SATRIA*, Sistem Administrasi Terpadu RT. "
                "Silahkan gunakan menu di bawah untuk berinteraksi."
            )
            self.bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=self._build_keyboard_menu())

        @self.bot.message_handler(content_types=['text', 'photo'])
        def master_router(message: telebot.types.Message):
            tid = str(message.from_user.id)
            
            # Auto-register if user bypasses /start
            user = self.user_repo.find_by_telegram_id(tid)
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    telegram_id=tid,
                    full_name=message.from_user.first_name or "Warga",
                    username=message.from_user.username or "",
                    role=UserRole.WARGA,
                    created_at=datetime.datetime.now()
                )
                self.user_repo.save(user)

            # 1. State Machine Interceptor (Highest Priority)
            if self.iuran_handler.intercept(tid, message):
                return

            text = message.text or message.caption or ""
            text_lower = text.lower()

            # 2. Static Menu Routing
            if text == "💰 Lapor Iuran":
                self.iuran_handler.initiate_flow(tid, message)
                return
            
            elif text == "📋 Lapor Masalah":
                self.bot.reply_to(message, "Silahkan ketik laporan, keluhan, atau masalah Anda. Anda dapat melakukan *mention* (@username) warga lain jika berkaitan.")
                return

            elif text == "📊 Statistik Sistem":
                users_count = len(self.user_repo.get_all())
                reports_count = len(self.report_repo.get_all())
                self.bot.reply_to(message, f"📈 *Statistik SATRIA*\n- Warga Terdaftar: {users_count}\n- Total Laporan: {reports_count}", parse_mode="Markdown")
                return

            # 3. Dynamic Report Tracking
            if any(keyword in text_lower for keyword in ["lapor", "masalah", "keluhan", "darurat"]):
                # Save to memory DB
                report = CitizenReport(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    content=text,
                    status=ApprovalStatus.PENDING,
                    created_at=datetime.datetime.now()
                )
                self.report_repo.save(report)
                
                # Acknowledge user
                self.bot.reply_to(message, "✅ Laporan Anda telah dicatat ke dalam sistem.")
                
                # Broadcast to Official Group
                self.gateway.send_group_broadcast(f"📢 *Laporan Masuk dari {user.full_name}*\n\n{text}")
                
                # Trigger Mention Engine
                self.mention_engine.process_mentions_in_text(text, user.full_name)
                return

            # 4. Fallback: AI Chatbot Logic
            # Triggered if bot is explicitly mentioned, or if it's a private chat
            bot_username = self.bot.get_me().username
            is_bot_mentioned = bot_username and (f"@{bot_username}" in text)
            is_private_chat = message.chat.type == "private"

            if is_bot_mentioned or is_private_chat:
                logger.info(f"Routing to AI Assistant for user {user.full_name}")
                
                # Package task for Background Queue to prevent Telegram timeout
                def ai_task():
                    ai_response = self.ai.generate_response(f"Sebagai asisten RT, jawab pertanyaan dari warga bernama {user.full_name} ini: {text}")
                    self.bot.reply_to(message, ai_response)
                
                self.worker.submit_task(ai_task)
                return

    def execute(self):
        logger.info("Application successfully configured. Awaiting messages...")
        
        def graceful_shutdown(signum, frame):
            logger.info("SIGINT/SIGTERM received. Shutting down gracefully...")
            self.bot.stop_polling()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)
        
        try:
            self.bot.infinity_polling(skip_pending=True)
        except Exception as e:
            logger.critical(f"Fatal crash in infinity_polling: {e}")

# =====================================================================
# 7. BOOTSTRAP EXECUTION
# =====================================================================
if __name__ == "__main__":
    try:
        app = SATRIAEnterpriseApplication()
        app.initialize_routing()
        app.execute()
    except Exception as e:
        logger.critical(f"Failed to bootstrap application: {e}")
        sys.exit(1)
