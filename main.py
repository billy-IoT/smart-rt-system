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
import psycopg2
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass

import telebot
from groq import Groq

# =====================================================================
# 1. CONFIGURATION & LOGGING
# =====================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("SATRIA_ENTERPRISE")

class ConfigurationManager:
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "")
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.admin_id = str(os.getenv("ADMIN_ID", ""))
        self.group_id = str(os.getenv("CHAT_ID_GRUP", ""))
        
        # POSTGRESQL SATU ENV SAJA (DATABASE_URL)
        self.db_url = os.getenv("DATABASE_URL", "")
        
        if not self.bot_token or not self.groq_key or not self.db_url:
            logger.critical("Pastikan BOT_TOKEN, GROQ_API_KEY, dan DATABASE_URL sudah di-set di env!")
            sys.exit(1)

config = ConfigurationManager()

def get_db_connection():
    return psycopg2.connect(config.db_url)

# =====================================================================
# 2. DATA MODELS
# =====================================================================
@dataclass(slots=True)
class User:
    id: str
    telegram_id: str
    full_name: str
    username: str
    created_at: datetime.datetime

@dataclass(slots=True)
class KasTransaction:
    id: str
    user_id: str
    nama: str
    kategori: str
    nominal: int
    created_at: datetime.datetime
    status: str = "Pending"

@dataclass(slots=True)
class CitizenReport:
    id: str
    user_id: str
    reporter_name: str
    content: str
    created_at: datetime.datetime

# =====================================================================
# 3. DATABASE INITIALIZER (PostgreSQL)
# =====================================================================
def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR PRIMARY KEY,
            telegram_id VARCHAR UNIQUE,
            full_name VARCHAR,
            username VARCHAR,
            created_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kas_transactions (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            nama VARCHAR,
            kategori VARCHAR,
            nominal INTEGER,
            created_at TIMESTAMP,
            status VARCHAR
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS citizen_reports (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            reporter_name VARCHAR,
            content TEXT,
            created_at TIMESTAMP
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("PostgreSQL Database initialized successfully.")

init_database()

# =====================================================================
# 4. REPOSITORIES (PostgreSQL Read/Write Layer)
# =====================================================================
class UserRepository:
    def save(self, user: User):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (id, telegram_id, full_name, username, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username
        """, (user.id, user.telegram_id, user.full_name, user.username, user.created_at))
        conn.commit()
        cursor.close()
        conn.close()

    def find_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, telegram_id, full_name, username, created_at FROM users WHERE telegram_id = %s", (str(telegram_id),))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row: return User(*row)
        return None

    def find_by_username(self, username: str) -> Optional[User]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, telegram_id, full_name, username, created_at FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row: return User(*row)
        return None

class KasRepository:
    def save(self, trx: KasTransaction):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO kas_transactions (id, user_id, nama, kategori, nominal, created_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (trx.id, trx.user_id, trx.nama, trx.kategori, trx.nominal, trx.created_at, trx.status))
        conn.commit()
        cursor.close()
        conn.close()

    def get_summary(self) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kategori, SUM(nominal) FROM kas_transactions WHERE status = 'Approved' GROUP BY kategori")
        rows = cursor.fetchall()
        
        cursor.execute("SELECT SUM(nominal) FROM kas_transactions WHERE status = 'Approved'")
        grand_total_row = cursor.fetchone()
        grand_total = grand_total_row[0] if grand_total_row and grand_total_row[0] else 0
        
        cursor.close()
        conn.close()
        
        if not rows: return "📉 Data Kas (Approved) masih kosong."
            
        res = "📊 *Laporan Total Kas RT (Approved)*\n\n"
        for row in rows:
            res += f"🔹 {row[0].capitalize()}: Rp {row[1]:,}\n"
        res += f"\n💰 *Total Seluruh Kas: Rp {grand_total:,}*"
        return res

class ReportRepository:
    def save(self, report: CitizenReport):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO citizen_reports (id, user_id, reporter_name, content, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (report.id, report.user_id, report.reporter_name, report.content, report.created_at))
        conn.commit()
        cursor.close()
        conn.close()

    def get_all(self) -> List[CitizenReport]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, reporter_name, content, created_at FROM citizen_reports ORDER BY created_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [CitizenReport(*row) for row in rows]

# =====================================================================
# 5. CORE SERVICES
# =====================================================================
class AIOrchestrator:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "Anda adalah SATRIA, asisten RT digital yang tegas, tertib, dan solutif."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq AI Error: {e}")
            return "Mohon maaf, sistem AI pengolah pesan sedang offline."

class StateMachine:
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def set_state(self, tid: str, key: str, value: Any):
        with self._lock:
            if tid not in self._states: self._states[tid] = {}
            self._states[tid][key] = value

    def get_state(self, tid: str, key: str) -> Any:
        with self._lock: return self._states.get(tid, {}).get(key)

    def clear_state(self, tid: str):
        with self._lock: self._states.pop(tid, None)

class BackgroundQueueWorker:
    def __init__(self):
        self.queue = queue.Queue()
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        while True:
            task = self.queue.get()
            try: task()
            except Exception as e: logger.error(f"Task Thread Error: {e}")
            finally: self.queue.task_done()

    def submit(self, task: Callable): self.queue.put(task)

def get_main_menu():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 Lapor Iuran", "📋 Lapor Masalah")
    kb.add("📊 Cek Kas RT", "📋 Cek Laporan")
    return kb

# =====================================================================
# 6. HANDLERS
# =====================================================================
class ApprovalHandler:
    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot

    def send_approval_request(self, trx_id: str, nama: str, nominal: int):
        if not config.admin_id: return
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(
            telebot.types.InlineKeyboardButton("✅ Setuju", callback_data=f"appr_ok_{trx_id}"),
            telebot.types.InlineKeyboardButton("❌ Tolak", callback_data=f"appr_no_{trx_id}")
        )
        self.bot.send_message(
            config.admin_id, 
            f"🔔 *Verifikasi Iuran Baru*\n\nNama: {nama}\nNominal: Rp{nominal:,}\nID: `{trx_id}`", 
            parse_mode="Markdown", reply_markup=markup
        )

class IuranHandler:
    def __init__(self, bot: telebot.TeleBot, sm: StateMachine, kas_repo: KasRepository):
        self.bot = bot
        self.sm = sm
        self.kas_repo = kas_repo
        self.approval = ApprovalHandler(bot)

    def initiate(self, tid: str, message: telebot.types.Message):
        self.sm.set_state(tid, "flow", "IURAN")
        self.sm.set_state(tid, "step", "NAMA")
        self.bot.reply_to(message, "📝 Silahkan masukkan *Nama Lengkap Penyetor*:", parse_mode="Markdown", reply_markup=telebot.types.ReplyKeyboardRemove())

    def process(self, tid: str, message: telebot.types.Message, user: User) -> bool:
        if self.sm.get_state(tid, "flow") != "IURAN": return False
        step = self.sm.get_state(tid, "step")
        
        if step == "NAMA":
            if not message.text: return True
            self.sm.set_state(tid, "nama", message.text)
            self.sm.set_state(tid, "step", "KATEGORI")
            kb_kategori = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb_kategori.add("Kebersihan", "Keamanan", "Sosial")
            self.bot.reply_to(message, "Pilih Kategori Iuran:", reply_markup=kb_kategori)
            
        elif step == "KATEGORI":
            if not message.text: return True
            self.sm.set_state(tid, "kategori", message.text)
            self.sm.set_state(tid, "step", "NOMINAL")
            
            kb_nominal = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb_nominal.add("Rp 10.000", "Rp 20.000")
            kb_nominal.add("Rp 50.000", "Rp 100.000")
            kb_nominal.add("Input Manual")
            self.bot.reply_to(message, "Pilih nominal iuran di bawah atau pilih 'Input Manual' (Minimal Rp10.000):", reply_markup=kb_nominal)
            
        elif step == "NOMINAL":
            if not message.text: return True
            
            if message.text == "Input Manual":
                self.bot.reply_to(message, "Silahkan ketik angka nominal iuran saja (Minimal Rp10.000, contoh: 15000):", reply_markup=telebot.types.ReplyKeyboardRemove())
                return True
            
            clean_nominal = re.sub(r'\D', '', message.text)
            if not clean_nominal or not clean_nominal.isdigit():
                self.bot.reply_to(message, "❌ Format salah. Harap pilih tombol nominal yang tersedia atau ketik angka saja:")
                return True
                
            nominal_value = int(clean_nominal)
            
            if nominal_value < 10000:
                self.bot.reply_to(message, "❌ *Nominal Terlalu Kecil!* Minimal iuran kas warga adalah *Rp10.000*. Silahkan masukkan nominal yang valid:", parse_mode="Markdown")
                return True
                
            self.sm.set_state(tid, "nominal", nominal_value)
            self.sm.set_state(tid, "step", "FOTO")
            self.bot.reply_to(message, "Kirimkan *Foto Bukti Transfer* 📸:", parse_mode="Markdown", reply_markup=telebot.types.ReplyKeyboardRemove())
            
        elif step == "FOTO":
            if not message.photo:
                self.bot.reply_to(message, "Harap kirimkan gambar bukti transfer.")
                return True
            nama = self.sm.get_state(tid, "nama")
            kategori = self.sm.get_state(tid, "kategori")
            nominal = self.sm.get_state(tid, "nominal")
            
            trx_id = str(uuid.uuid4())
            trx = KasTransaction(trx_id, user.id, nama, kategori, nominal, datetime.datetime.now(), "Pending")
            self.kas_repo.save(trx)
            self.sm.clear_state(tid)
            
            # TRIGGER APPROVAL ADMIN
            self.approval.send_approval_request(trx_id, nama, nominal)
            
            self.bot.reply_to(message, f"✅ Data Iuran Tersimpan!\n\nNama: {nama}\nKategori: {kategori}\nNominal: Rp{nominal:,}\n\nMenunggu verifikasi admin.", reply_markup=get_main_menu())
        return True

class MentionHandler:
    def __init__(self, ai: AIOrchestrator, bot: telebot.TeleBot, user_repo: UserRepository):
        self.ai = ai; self.bot = bot; self.user_repo = user_repo

    def process_mentions(self, text: str, sender_name: str):
        usernames = re.findall(r"@(\w+)", text)
        for uname in usernames:
            prompt = (
                f"Anda adalah SATRIA, asisten RT. Warga bernama {sender_name} baru saja melaporkan masalah. "
                f"Dia sengaja mengetag @{uname} sebagai pihak pembuat masalah. "
                f"Isi laporannya: '{text}'. "
                f"Buatlah satu pesan teguran yang tegas, logis, dan menyadarkan untuk @{uname}. "
                f"Gunakan bahasa Indonesia yang profesional namun menohok agar dia segera memperbaiki kesalahannya."
            )
            ai_msg = self.ai.generate_response(prompt)
            
            if config.group_id:
                try: 
                    self.bot.send_message(config.group_id, f"⚠️ *Teguran Terbuka untuk @{uname}:*\n\n{ai_msg}", parse_mode="Markdown")
                except Exception as e: 
                    logger.error(f"Gagal kirim teguran ke grup: {e}")

            target = self.user_repo.find_by_username(uname)
            if target:
                try: 
                    self.bot.send_message(target.telegram_id, f"🚨 *Peringatan Keamanan Lingkungan RT*\n\n{ai_msg}", parse_mode="Markdown")
                except Exception as e: pass

# =====================================================================
# 7. APPLICATION FACTORY
# =====================================================================
class SATRIAApp:
    def __init__(self):
        self.bot = telebot.TeleBot(config.bot_token)
        self.user_repo = UserRepository()
        self.kas_repo = KasRepository()
        self.report_repo = ReportRepository()
        self.ai = AIOrchestrator(config.groq_key)
        self.sm = StateMachine()
        self.worker = BackgroundQueueWorker()
        
        self.iuran_handler = IuranHandler(self.bot, self.sm, self.kas_repo)
        self.mention_handler = MentionHandler(self.ai, self.bot, self.user_repo)

    def setup_routes(self):
        
        # HANDLER UNTUK TOMBOL APPROVAL ADMIN
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("appr_"))
        def handle_approval(call):
            action = call.data.split("_")[1]
            trx_id = call.data.split("_")[2]
            status = 'Approved' if action == 'ok' else 'Rejected'
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE kas_transactions SET status = %s WHERE id = %s", (status, trx_id))
            conn.commit()
            cursor.close()
            conn.close()
            
            pesan = "✅ Iuran Disetujui" if action == 'ok' else "❌ Iuran Ditolak"
            self.bot.edit_message_text(pesan, call.message.chat.id, call.message.message_id)

        @self.bot.message_handler(commands=['start'])
        def handle_start(message: telebot.types.Message):
            tid = str(message.from_user.id)
            user = self.user_repo.find_by_telegram_id(tid)
            if not user:
                user = User(
                    id=str(uuid.uuid4()), telegram_id=tid,
                    full_name=message.from_user.first_name or "Warga",
                    username=message.from_user.username or "",
                    created_at=datetime.datetime.now()
                )
                self.user_repo.save(user)
            self.bot.reply_to(message, "Sistem SATRIA RT Enterprise PostgreSQL Aktif.", reply_markup=get_main_menu())

        @self.bot.message_handler(content_types=['text', 'photo'])
        def handle_all(message: telebot.types.Message):
            tid = str(message.from_user.id)
            user = self.user_repo.find_by_telegram_id(tid)
            if not user:
                user = User(id=str(uuid.uuid4()), telegram_id=tid, full_name=message.from_user.first_name or "Warga", username=message.from_user.username or "", created_at=datetime.datetime.now())
                self.user_repo.save(user)

            if self.iuran_handler.process(tid, message, user): return

            text = message.text or message.caption or ""

            if text == "💰 Lapor Iuran":
                self.iuran_handler.initiate(tid, message)
                return
                
            elif text == "📊 Cek Kas RT":
                self.bot.reply_to(message, self.kas_repo.get_summary(), parse_mode="Markdown")
                return

            elif text == "📋 Cek Laporan":
                reports = self.report_repo.get_all()
                if not reports:
                    self.bot.reply_to(message, "📭 Lingkungan aman terkendali. Belum ada laporan warga masuk.")
                else:
                    res = "📋 *Daftar Keluhan & Laporan Warga RT*\n\n"
                    for idx, r in enumerate(reports, 1):
                        res += f"{idx}. *Pelapor:* {r.reporter_name}\n📝 *Keluhan:* {r.content}\n🕒 *Tanggal:* {r.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
                    self.bot.reply_to(message, res, parse_mode="Markdown")
                return

            elif text == "📋 Lapor Masalah":
                self.bot.reply_to(message, "Silahkan ketik laporan/keluhan Anda. Sertakan tag `@username` warga yang bersangkutan jika ada masalah spesifik agar ditegur sistem.")
                return
                
            elif "lapor" in text.lower() or "masalah" in text.lower() or "keluhan" in text.lower():
                report = CitizenReport(str(uuid.uuid4()), user.id, user.full_name, text, datetime.datetime.now())
                self.report_repo.save(report)
                self.bot.reply_to(message, "✅ Laporan Anda berhasil dicatat ke sistem dan masuk menu 'Cek Laporan'.")
                
                if config.group_id:
                    try: self.bot.send_message(config.group_id, f"📢 *Laporan Warga Masuk*\n*Dari:* {user.full_name}\n*Isi:* {text}")
                    except: pass
                
                def trigger_mention_ai():
                    self.mention_handler.process_mentions(text, user.full_name)
                self.worker.submit(trigger_mention_ai)
                return

            bot_me = self.bot.get_me().username
            if (bot_me and f"@{bot_me}" in text) or message.chat.type == "private":
                def ai_task():
                    response = self.ai.generate_response(f"Sebagai asisten RT, jawab keluhan/pertanyaan warga: {text}")
                    self.bot.reply_to(message, response)
                self.worker.submit(ai_task)

    def run(self):
        logger.info("SATRIA Enterprise Engine is polling messages...")
        def shutdown(sig, frame):
            self.bot.stop_polling()
            sys.exit(0)
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
        self.bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    app = SATRIAApp()
    app.setup_routes()
    app.run()
