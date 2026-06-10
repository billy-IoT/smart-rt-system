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
import sqlite3
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
        self.groq_key  = os.getenv("GROQ_API_KEY", "")
        self.admin_id  = str(os.getenv("ADMIN_ID", ""))
        self.group_id  = str(os.getenv("CHAT_ID_GRUP", ""))

        if os.path.exists("/app/data"):
            self.db_name = "/app/data/satria_rt.db"
            logger.info("Railway Volume detected. Using /app/data/satria_rt.db")
        else:
            self.db_name = "satria_rt.db"
            logger.info("Local environment detected. Using local satria_rt.db")

        if not self.bot_token or not self.groq_key:
            logger.critical("BOT_TOKEN atau GROQ_API_KEY belum di-set di env!")
            sys.exit(1)

config = ConfigurationManager()

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

# Model baru: pending iuran menunggu approval admin
@dataclass(slots=True)
class PendingIuran:
    id: str           # UUID, dipakai sebagai callback_data
    user_id: str      # UUID user di DB kita
    telegram_id: str  # Telegram ID warga, untuk notifikasi balik
    nama: str
    kategori: str
    nominal: int
    photo_file_id: str
    status: str       # PENDING | APPROVED | REJECTED
    created_at: datetime.datetime

@dataclass(slots=True)
class CitizenReport:
    id: str
    user_id: str
    reporter_name: str
    content: str
    created_at: datetime.datetime

# =====================================================================
# 3. DATABASE INITIALIZER
# =====================================================================
def init_database():
    conn = sqlite3.connect(config.db_name)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            telegram_id TEXT UNIQUE,
            full_name TEXT,
            username TEXT,
            created_at TEXT
        )
    """)

    # Tabel kas hanya berisi transaksi yang SUDAH diapprove
    c.execute("""
        CREATE TABLE IF NOT EXISTS kas_transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            nama TEXT,
            kategori TEXT,
            nominal INTEGER,
            created_at TEXT
        )
    """)

    # Tabel antrian approval
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_iuran (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            telegram_id TEXT,
            nama TEXT,
            kategori TEXT,
            nominal INTEGER,
            photo_file_id TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS citizen_reports (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            reporter_name TEXT,
            content TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    logger.info("SQLite Database initialized successfully.")

init_database()

# =====================================================================
# 4. REPOSITORIES
# =====================================================================
class UserRepository:
    def __init__(self):
        self._lock = threading.RLock()

    def save(self, user: User):
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            conn.execute("""
                INSERT INTO users (id, telegram_id, full_name, username, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    username=excluded.username
            """, (user.id, user.telegram_id, user.full_name, user.username, user.created_at.isoformat()))
            conn.commit(); conn.close()

    def find_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            row = conn.execute(
                "SELECT id,telegram_id,full_name,username,created_at FROM users WHERE telegram_id=?",
                (str(telegram_id),)
            ).fetchone()
            conn.close()
            return User(*row[:4], datetime.datetime.fromisoformat(row[4])) if row else None

    def find_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            row = conn.execute(
                "SELECT id,telegram_id,full_name,username,created_at FROM users WHERE LOWER(username)=LOWER(?)",
                (username,)
            ).fetchone()
            conn.close()
            return User(*row[:4], datetime.datetime.fromisoformat(row[4])) if row else None


class KasRepository:
    def __init__(self):
        self._lock = threading.RLock()

    def save(self, trx: KasTransaction):
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            conn.execute("""
                INSERT INTO kas_transactions (id,user_id,nama,kategori,nominal,created_at)
                VALUES (?,?,?,?,?,?)
            """, (trx.id, trx.user_id, trx.nama, trx.kategori, trx.nominal, trx.created_at.isoformat()))
            conn.commit(); conn.close()

    def get_summary(self) -> str:
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            rows = conn.execute(
                "SELECT kategori, SUM(nominal) FROM kas_transactions GROUP BY kategori"
            ).fetchall()
            grand = conn.execute("SELECT SUM(nominal) FROM kas_transactions").fetchone()[0] or 0
            conn.close()

            if not rows:
                return "📉 Data Kas masih kosong."
            res = "📊 *Laporan Total Kas RT*\n\n"
            for cat, amt in rows:
                res += f"🔹 {cat.capitalize()}: Rp {amt:,}\n"
            res += f"\n💰 *Total Seluruh Kas: Rp {grand:,}*"
            return res


class PendingIuranRepository:
    def __init__(self):
        self._lock = threading.RLock()

    def save(self, p: PendingIuran):
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            conn.execute("""
                INSERT INTO pending_iuran
                    (id,user_id,telegram_id,nama,kategori,nominal,photo_file_id,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (p.id, p.user_id, p.telegram_id, p.nama, p.kategori,
                  p.nominal, p.photo_file_id, p.status, p.created_at.isoformat()))
            conn.commit(); conn.close()

    def find_by_id(self, pid: str) -> Optional[PendingIuran]:
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            row = conn.execute(
                "SELECT id,user_id,telegram_id,nama,kategori,nominal,photo_file_id,status,created_at "
                "FROM pending_iuran WHERE id=?", (pid,)
            ).fetchone()
            conn.close()
            if not row: return None
            return PendingIuran(row[0], row[1], row[2], row[3], row[4],
                                row[5], row[6], row[7],
                                datetime.datetime.fromisoformat(row[8]))

    def update_status(self, pid: str, status: str):
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            conn.execute("UPDATE pending_iuran SET status=? WHERE id=?", (status, pid))
            conn.commit(); conn.close()


class ReportRepository:
    def __init__(self):
        self._lock = threading.RLock()

    def save(self, report: CitizenReport):
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            conn.execute("""
                INSERT INTO citizen_reports (id,user_id,reporter_name,content,created_at)
                VALUES (?,?,?,?,?)
            """, (report.id, report.user_id, report.reporter_name,
                  report.content, report.created_at.isoformat()))
            conn.commit(); conn.close()

    def get_all(self) -> List[CitizenReport]:
        with self._lock:
            conn = sqlite3.connect(config.db_name)
            rows = conn.execute(
                "SELECT id,user_id,reporter_name,content,created_at "
                "FROM citizen_reports ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            return [CitizenReport(r[0], r[1], r[2], r[3],
                                  datetime.datetime.fromisoformat(r[4])) for r in rows]

# =====================================================================
# 5. CORE SERVICES
# =====================================================================
class AIOrchestrator:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def generate_response(self, prompt: str) -> str:
        try:
            res = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "Anda adalah SATRIA, asisten RT digital yang cerdas, tegas, dan solutif."},
                    {"role": "user",   "content": prompt}
                ]
            )
            return res.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq AI Error: {e}")
            return "Mohon maaf, sistem AI pengolah pesan sedang offline."


class StateMachine:
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def set_state(self, tid: str, key: str, value: Any):
        with self._lock:
            self._states.setdefault(tid, {})[key] = value

    def get_state(self, tid: str, key: str) -> Any:
        with self._lock:
            return self._states.get(tid, {}).get(key)

    def clear_state(self, tid: str):
        with self._lock:
            self._states.pop(tid, None)


class BackgroundQueueWorker:
    def __init__(self):
        self.queue = queue.Queue()
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        while True:
            task = self.queue.get()
            try:    task()
            except Exception as e: logger.error(f"Task Thread Error: {e}")
            finally: self.queue.task_done()

    def submit(self, task: Callable): self.queue.put(task)


def get_main_menu():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 Lapor Iuran", "📋 Lapor Masalah")
    kb.add("📊 Cek Kas RT",  "📋 Cek Laporan")
    return kb

# =====================================================================
# 6. HANDLERS
# =====================================================================
class IuranHandler:
    """
    Alur: NAMA → KATEGORI → NOMINAL → FOTO
    Setelah foto diterima, data masuk ke pending_iuran (status=PENDING).
    Admin mendapat notifikasi + InlineKeyboard Setujui/Tolak.
    """
    def __init__(self, bot: telebot.TeleBot, sm: StateMachine,
                 kas_repo: KasRepository, pending_repo: PendingIuranRepository):
        self.bot          = bot
        self.sm           = sm
        self.kas_repo     = kas_repo
        self.pending_repo = pending_repo

    def initiate(self, tid: str, message: telebot.types.Message):
        self.sm.set_state(tid, "flow", "IURAN")
        self.sm.set_state(tid, "step", "NAMA")
        self.bot.reply_to(
            message,
            "📝 Silahkan masukkan *Nama Lengkap Penyetor*:",
            parse_mode="Markdown",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )

    def process(self, tid: str, message: telebot.types.Message, user: User) -> bool:
        if self.sm.get_state(tid, "flow") != "IURAN":
            return False
        step = self.sm.get_state(tid, "step")

        if step == "NAMA":
            if not message.text: return True
            self.sm.set_state(tid, "nama", message.text)
            self.sm.set_state(tid, "step", "KATEGORI")
            kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.add("Kebersihan", "Keamanan", "Sosial")
            self.bot.reply_to(message, "Pilih Kategori Iuran:", reply_markup=kb)

        elif step == "KATEGORI":
            if not message.text: return True
            self.sm.set_state(tid, "kategori", message.text)
            self.sm.set_state(tid, "step", "NOMINAL")
            kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add("Rp 10.000", "Rp 20.000")
            kb.add("Rp 50.000", "Rp 100.000")
            kb.add("Input Manual")
            self.bot.reply_to(message, "Pilih nominal iuran (Minimal Rp10.000):", reply_markup=kb)

        elif step == "NOMINAL":
            if not message.text: return True
            if message.text == "Input Manual":
                self.bot.reply_to(
                    message,
                    "Ketik angka nominal saja (contoh: 15000):",
                    reply_markup=telebot.types.ReplyKeyboardRemove()
                )
                return True

            clean = re.sub(r'\D', '', message.text)
            if not clean:
                self.bot.reply_to(message, "❌ Format salah. Pilih tombol atau ketik angka:")
                return True

            nominal_value = int(clean)
            if nominal_value < 10000:
                self.bot.reply_to(
                    message,
                    "❌ *Minimal Rp10.000.* Silahkan masukkan nominal yang valid:",
                    parse_mode="Markdown"
                )
                return True

            self.sm.set_state(tid, "nominal", nominal_value)
            self.sm.set_state(tid, "step", "FOTO")
            self.bot.reply_to(
                message,
                "Kirimkan *Foto Bukti Transfer* 📸:",
                parse_mode="Markdown",
                reply_markup=telebot.types.ReplyKeyboardRemove()
            )

        elif step == "FOTO":
            if not message.photo:
                self.bot.reply_to(message, "Harap kirimkan gambar bukti transfer.")
                return True

            nama     = self.sm.get_state(tid, "nama")
            kategori = self.sm.get_state(tid, "kategori")
            nominal  = self.sm.get_state(tid, "nominal")
            photo_id = message.photo[-1].file_id   # resolusi tertinggi

            # Simpan ke pending, BELUM masuk kas
            pending = PendingIuran(
                id            = str(uuid.uuid4()),
                user_id       = user.id,
                telegram_id   = tid,
                nama          = nama,
                kategori      = kategori,
                nominal       = nominal,
                photo_file_id = photo_id,
                status        = "PENDING",
                created_at    = datetime.datetime.now()
            )
            self.pending_repo.save(pending)
            self.sm.clear_state(tid)

            # Beritahu warga bahwa iuran menunggu verifikasi
            self.bot.reply_to(
                message,
                f"✅ *Iuran Terkirim & Menunggu Verifikasi Admin*\n\n"
                f"📋 Nama     : {nama}\n"
                f"📂 Kategori : {kategori}\n"
                f"💵 Nominal  : Rp {nominal:,}\n\n"
                f"Anda akan mendapat notifikasi setelah admin memverifikasi.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )

            # Kirim notifikasi + bukti ke admin
            self._notify_admin(pending)

        return True

    def _notify_admin(self, p: PendingIuran):
        """Kirim foto bukti + tombol Setujui/Tolak ke admin."""
        if not config.admin_id:
            logger.warning("ADMIN_ID belum di-set, approval tidak bisa dikirim.")
            return

        caption = (
            f"🔔 *Permohonan Verifikasi Iuran*\n\n"
            f"👤 Nama     : {p.nama}\n"
            f"📂 Kategori : {p.kategori}\n"
            f"💵 Nominal  : Rp {p.nominal:,}\n"
            f"🕒 Waktu    : {p.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"ID Transaksi: `{p.id}`"
        )

        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(
            telebot.types.InlineKeyboardButton(
                "✅ Setujui", callback_data=f"APPROVE:{p.id}"
            ),
            telebot.types.InlineKeyboardButton(
                "❌ Tolak",   callback_data=f"REJECT:{p.id}"
            )
        )

        try:
            self.bot.send_photo(
                config.admin_id,
                p.photo_file_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=kb
            )
            logger.info(f"Notifikasi approval dikirim ke admin untuk pending_id={p.id}")
        except Exception as e:
            logger.error(f"Gagal kirim notifikasi ke admin: {e}")


class ApprovalHandler:
    """
    Menangani callback_data dari InlineKeyboard admin:
      APPROVE:<pending_id>  →  pindahkan ke kas_transactions, beritahu warga
      REJECT:<pending_id>   →  update status REJECTED, beritahu warga
    """
    def __init__(self, bot: telebot.TeleBot,
                 pending_repo: PendingIuranRepository,
                 kas_repo: KasRepository):
        self.bot          = bot
        self.pending_repo = pending_repo
        self.kas_repo     = kas_repo

    def handle(self, call: telebot.types.CallbackQuery):
        data = call.data  # "APPROVE:uuid" atau "REJECT:uuid"

        if not (data.startswith("APPROVE:") or data.startswith("REJECT:")):
            return

        # Hanya admin yang boleh menekan tombol ini
        caller_id = str(call.from_user.id)
        if caller_id != config.admin_id:
            self.bot.answer_callback_query(call.id, "⛔ Hanya admin yang bisa melakukan ini.")
            return

        action, pending_id = data.split(":", 1)
        pending = self.pending_repo.find_by_id(pending_id)

        if not pending:
            self.bot.answer_callback_query(call.id, "❌ Data tidak ditemukan.")
            return

        if pending.status != "PENDING":
            self.bot.answer_callback_query(
                call.id,
                f"⚠️ Iuran ini sudah diproses sebelumnya ({pending.status})."
            )
            return

        if action == "APPROVE":
            # Pindahkan ke kas resmi
            trx = KasTransaction(
                id         = str(uuid.uuid4()),
                user_id    = pending.user_id,
                nama       = pending.nama,
                kategori   = pending.kategori,
                nominal    = pending.nominal,
                created_at = datetime.datetime.now()
            )
            self.kas_repo.save(trx)
            self.pending_repo.update_status(pending_id, "APPROVED")

            # Edit pesan admin — hapus tombol, tambah keterangan
            try:
                self.bot.edit_message_caption(
                    chat_id    = call.message.chat.id,
                    message_id = call.message.message_id,
                    caption    = call.message.caption + "\n\n✅ *DISETUJUI*",
                    parse_mode = "Markdown"
                )
            except Exception: pass

            self.bot.answer_callback_query(call.id, "✅ Iuran berhasil disetujui dan masuk kas!")

            # Beritahu warga
            try:
                self.bot.send_message(
                    pending.telegram_id,
                    f"🎉 *Iuran Anda Telah Diverifikasi!*\n\n"
                    f"📋 Nama     : {pending.nama}\n"
                    f"📂 Kategori : {pending.kategori}\n"
                    f"💵 Nominal  : Rp {pending.nominal:,}\n\n"
                    f"Dana Anda telah resmi masuk ke Kas RT. Terima kasih! 🙏",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Gagal beritahu warga (approved): {e}")

        elif action == "REJECT":
            self.pending_repo.update_status(pending_id, "REJECTED")

            try:
                self.bot.edit_message_caption(
                    chat_id    = call.message.chat.id,
                    message_id = call.message.message_id,
                    caption    = call.message.caption + "\n\n❌ *DITOLAK*",
                    parse_mode = "Markdown"
                )
            except Exception: pass

            self.bot.answer_callback_query(call.id, "❌ Iuran ditolak.")

            # Beritahu warga
            try:
                self.bot.send_message(
                    pending.telegram_id,
                    f"❌ *Iuran Anda Ditolak oleh Admin*\n\n"
                    f"📋 Nama     : {pending.nama}\n"
                    f"📂 Kategori : {pending.kategori}\n"
                    f"💵 Nominal  : Rp {pending.nominal:,}\n\n"
                    f"Silahkan hubungi pengurus RT untuk informasi lebih lanjut.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Gagal beritahu warga (rejected): {e}")

        logger.info(f"Approval selesai: pending_id={pending_id}, action={action}")


class MentionHandler:
    def __init__(self, ai: AIOrchestrator, bot: telebot.TeleBot, user_repo: UserRepository):
        self.ai        = ai
        self.bot       = bot
        self.user_repo = user_repo

    def process_mentions(self, text: str, sender_name: str):
        for uname in re.findall(r"@(\w+)", text):
            prompt = (
                f"Anda adalah SATRIA, asisten RT. Warga bernama {sender_name} melaporkan masalah. "
                f"Dia mengetag @{uname} sebagai pihak yang bermasalah. "
                f"Isi laporan: '{text}'. "
                f"Buat teguran tegas, logis, dan profesional dalam bahasa Indonesia untuk @{uname}."
            )
            ai_msg = self.ai.generate_response(prompt)

            if config.group_id:
                try:
                    self.bot.send_message(
                        config.group_id,
                        f"⚠️ *Teguran Terbuka untuk @{uname}:*\n\n{ai_msg}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Gagal kirim teguran ke grup: {e}")

            target = self.user_repo.find_by_username(uname)
            if target:
                try:
                    self.bot.send_message(
                        target.telegram_id,
                        f"🚨 *Peringatan Keamanan Lingkungan RT*\n\n{ai_msg}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Gagal Japri target: {e}")

# =====================================================================
# 7. APPLICATION FACTORY
# =====================================================================
class SATRIAApp:
    def __init__(self):
        self.bot          = telebot.TeleBot(config.bot_token)
        self.user_repo    = UserRepository()
        self.kas_repo     = KasRepository()
        self.pending_repo = PendingIuranRepository()
        self.report_repo  = ReportRepository()
        self.ai           = AIOrchestrator(config.groq_key)
        self.sm           = StateMachine()
        self.worker       = BackgroundQueueWorker()

        self.iuran_handler    = IuranHandler(self.bot, self.sm, self.kas_repo, self.pending_repo)
        self.approval_handler = ApprovalHandler(self.bot, self.pending_repo, self.kas_repo)
        self.mention_handler  = MentionHandler(self.ai, self.bot, self.user_repo)

    def _get_or_create_user(self, from_user) -> User:
        tid  = str(from_user.id)
        user = self.user_repo.find_by_telegram_id(tid)
        if not user:
            user = User(
                id          = str(uuid.uuid4()),
                telegram_id = tid,
                full_name   = from_user.first_name or "Warga",
                username    = from_user.username or "",
                created_at  = datetime.datetime.now()
            )
            self.user_repo.save(user)
        return user

    def setup_routes(self):

        # ------------------------------------------------------------------
        # /start
        # ------------------------------------------------------------------
        @self.bot.message_handler(commands=['start'])
        def handle_start(message: telebot.types.Message):
            self._get_or_create_user(message.from_user)
            self.bot.reply_to(
                message,
                "🤖 Sistem *SATRIA RT Enterprise v9.2* Aktif.\n\nSelamat datang! Gunakan menu di bawah.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )

        # ------------------------------------------------------------------
        # Callback dari tombol Setujui / Tolak di pesan admin
        # ------------------------------------------------------------------
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback(call: telebot.types.CallbackQuery):
            self.approval_handler.handle(call)

        # ------------------------------------------------------------------
        # Semua pesan teks & foto
        # ------------------------------------------------------------------
        @self.bot.message_handler(content_types=['text', 'photo'])
        def handle_all(message: telebot.types.Message):
            tid  = str(message.from_user.id)
            user = self._get_or_create_user(message.from_user)

            # Alur multi-step iuran (state machine)
            if self.iuran_handler.process(tid, message, user):
                return

            text = message.text or message.caption or ""

            if text == "💰 Lapor Iuran":
                self.iuran_handler.initiate(tid, message)

            elif text == "📊 Cek Kas RT":
                self.bot.reply_to(message, self.kas_repo.get_summary(), parse_mode="Markdown")

            elif text == "📋 Cek Laporan":
                reports = self.report_repo.get_all()
                if not reports:
                    self.bot.reply_to(message, "📭 Belum ada laporan warga masuk.")
                else:
                    res = "📋 *Daftar Keluhan & Laporan Warga RT*\n\n"
                    for idx, r in enumerate(reports, 1):
                        res += (f"{idx}. *Pelapor:* {r.reporter_name}\n"
                                f"📝 *Keluhan:* {r.content}\n"
                                f"🕒 *Tanggal:* {r.created_at.strftime('%d/%m/%Y %H:%M')}\n\n")
                    self.bot.reply_to(message, res, parse_mode="Markdown")

            elif text == "📋 Lapor Masalah":
                self.bot.reply_to(
                    message,
                    "Silahkan ketik laporan/keluhan Anda. "
                    "Sertakan `@username` warga yang bersangkutan jika ada masalah spesifik."
                )

            elif any(kw in text.lower() for kw in ("lapor", "masalah", "keluhan")):
                report = CitizenReport(str(uuid.uuid4()), user.id, user.full_name, text, datetime.datetime.now())
                self.report_repo.save(report)
                self.bot.reply_to(message, "✅ Laporan berhasil dicatat ke sistem.")

                if config.group_id:
                    try:
                        self.bot.send_message(
                            config.group_id,
                            f"📢 *Laporan Warga Masuk*\n*Dari:* {user.full_name}\n*Isi:* {text}"
                        )
                    except Exception: pass

                self.worker.submit(
                    lambda t=text, n=user.full_name: self.mention_handler.process_mentions(t, n)
                )

            else:
                bot_me = self.bot.get_me().username
                if (bot_me and f"@{bot_me}" in text) or message.chat.type == "private":
                    self.worker.submit(
                        lambda t=text: self.bot.reply_to(
                            message,
                            self.ai.generate_response(f"Sebagai asisten RT, jawab: {t}")
                        )
                    )

    def run(self):
        logger.info("SATRIA Enterprise Engine is polling messages...")
        def shutdown(sig, frame):
            self.bot.stop_polling()
            sys.exit(0)
        signal.signal(signal.SIGINT,  shutdown)
        signal.signal(signal.SIGTERM, shutdown)
        self.bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    app = SATRIAApp()
    app.setup_routes()
    app.run()
