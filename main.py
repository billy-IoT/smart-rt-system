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
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("SATRIA_ENTERPRISE")

class ConfigurationManager:
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN", "")
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.admin_id = str(os.getenv("ADMIN_ID", ""))
        self.group_id = str(os.getenv("CHAT_ID_GRUP", "")) # Pastikan ID Grup diawali tanda minus, contoh: -100123456789
        
        if not self.bot_token or not self.groq_key:
            logger.critical("BOT_TOKEN atau GROQ_API_KEY belum disetting!")
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

@dataclass(slots=True)
class CitizenReport:
    id: str
    user_id: str
    reporter_name: str
    content: str
    created_at: datetime.datetime

# =====================================================================
# 3. REPOSITORIES (Database Layer)
# =====================================================================
class UserRepository:
    def __init__(self):
        self._db: Dict[str, User] = {}
        self._lock = threading.RLock()

    def save(self, user: User):
        with self._lock: self._db[user.id] = user

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

class KasRepository:
    def __init__(self):
        self._db: List[KasTransaction] = []
        self._lock = threading.RLock()

    def save(self, trx: KasTransaction):
        with self._lock: self._db.append(trx)

    def get_summary(self) -> str:
        with self._lock:
            if not self._db: return "📉 Data Kas masih kosong."
            totals = {}
            grand_total = 0
            for t in self._db:
                cat = t.kategori.capitalize()
                totals[cat] = totals.get(cat, 0) + t.nominal
                grand_total += t.nominal
            res = "📊 *Laporan Total Kas RT*\n\n"
            for cat, amt in totals.items():
                res += f"🔹 {cat}: Rp {amt:,}\n"
            res += f"\n💰 *Total Seluruh Kas: Rp {grand_total:,}*"
            return res

class ReportRepository:
    def __init__(self):
        self._db: List[CitizenReport] = []
        self._lock = threading.RLock()

    def save(self, report: CitizenReport):
        with self._lock: self._db.append(report)

    def get_all(self) -> List[CitizenReport]:
        with self._lock: return list(self._db)

# =====================================================================
# 4. SERVICES
# =====================================================================
class AIOrchestrator:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "Anda adalah SATRIA, asisten RT digital yang cerdas, tertib, tegas, dan solutif."},
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
# 5. HANDLERS (LOGIKA FITUR)
# =====================================================================
class IuranHandler:
    def __init__(self, bot: telebot.TeleBot, sm: StateMachine, kas_repo: KasRepository):
        self.bot = bot
        self.sm = sm
        self.kas_repo = kas_repo

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
            
            # Tombol Kategori
            kb_kategori = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb_kategori.add("Kebersihan", "Keamanan", "Sosial")
            self.bot.reply_to(message, "Pilih Kategori Iuran:", reply_markup=kb_kategori)
            
        elif step == "KATEGORI":
            if not message.text: return True
            self.sm.set_state(tid, "kategori", message.text)
            self.sm.set_state(tid, "step", "NOMINAL")
            
            # Tombol Nominal Cepat
            kb_nominal = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb_nominal.add("Rp 10.000", "Rp 20.000")
            kb_nominal.add("Rp 50.000", "Rp 100.000")
            kb_nominal.add("Input Manual")
            self.bot.reply_to(message, "Pilih nominal iuran di bawah atau pilih 'Input Manual' jika berbeda:", reply_markup=kb_nominal)
            
        elif step == "NOMINAL":
            if not message.text: return True
            
            if message.text == "Input Manual":
                self.bot.reply_to(message, "Silahkan ketik angka nominal iuran saja (Minimal Rp10.000, contoh: 15000):", reply_markup=telebot.types.ReplyKeyboardRemove())
                return True
            
            # Sanitasi teks (Menghapus tulisan "Rp " atau ".")
            clean_nominal = re.sub(r'\D', '', message.text)
            if not clean_nominal or not clean_nominal.isdigit():
                self.bot.reply_to(message, "❌ Format salah. Harap pilih tombol nominal atau ketik angka saja:")
                return True
                
            nominal_value = int(clean_nominal)
            
            # Validasi Minimal 10.000
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
            
            trx = KasTransaction(str(uuid.uuid4()), user.id, nama, kategori, nominal, datetime.datetime.now())
            self.kas_repo.save(trx)
            self.sm.clear_state(tid)
            
            self.bot.reply_to(message, f"✅ *Data Iuran Tersimpan!*\n\nNama: {nama}\nKategori: {kategori}\nNominal: Rp{nominal:,}\n\nMenunggu verifikasi admin.", parse_mode="Markdown", reply_markup=get_main_menu())
        return True

class MentionHandler:
    def __init__(self, ai: AIOrchestrator, bot: telebot.TeleBot, user_repo: UserRepository):
        self.ai = ai; self.bot = bot; self.user_repo = user_repo

    def process_mentions(self, text: str, sender_name: str):
        usernames = re.findall(r"@(\w+)", text)
        for uname in usernames:
            target = self.user_repo.find_by_username(uname)
            if target:
                prompt = (
                    f"Anda adalah SATRIA, asisten RT. Warga bernama {sender_name} baru saja melaporkan masalah/keluhan lingkungan "
                    f"dan sengaja menandai/mengetag @{uname} (Nama lengkap: {target.full_name}) sebagai pihak yang terkait atau bertanggung jawab. "
                    f"Isi laporannya adalah: '{text}'. "
                    f"Buatlah satu pesan teguran yang tegas, logis, namun tetap menggunakan bahasa yang sopan. "
                    f"Tujuannya agar {target.full_name} segera sadar akan ketidaknyamanan yang ditimbulkannya bagi warga sekitar, "
                    f"dan tergerak untuk segera mengklarifikasi atau membereskan masalah tersebut demi ketertiban bersama di RT."
                )
                ai_msg = self.ai.generate_response(prompt)
                
                # 1. Tembak Japri ke Pelaku
                try: self.bot.send_message(target.telegram_id, f"⚠️ *Pemberitahuan Teguran Lingkungan RT*\n\n{ai_msg}", parse_mode="Markdown")
                except Exception as e: logger.error(f"Gagal Japri target: {e}")
                
                # 2. Tembak Broadcast Teguran Terbuka ke Grup
                if config.group_id:
                    try: self.bot.send_message(config.group_id, f"📩 *Teguran Terbuka untuk @{uname}:*\n\n{ai_msg}", parse_mode="Markdown")
                    except Exception as e: logger.error(f"Gagal kirim teguran ke grup: {e}")

# =====================================================================
# 6. APPLICATION FACTORY (INTI BOT)
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
            self.bot.reply_to(message, "Sistem SATRIA RT Enterprise v8.0 Aktif.", reply_markup=get_main_menu())

        @self.bot.message_handler(content_types=['text', 'photo'])
        def handle_all(message: telebot.types.Message):
            tid = str(message.from_user.id)
            user = self.user_repo.find_by_telegram_id(tid)
            
            # Auto-register user jika belum terdata (untuk bypass start)
            if not user:
                user = User(id=str(uuid.uuid4()), telegram_id=tid, full_name=message.from_user.first_name or "Warga", username=message.from_user.username or "", created_at=datetime.datetime.now())
                self.user_repo.save(user)

            # --- ALUR IURAN (STATE MACHINE) ---
            if self.iuran_handler.process(tid, message, user): return

            text = message.text or message.caption or ""

            # --- ROUTING MENU UTAMA ---
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
                self.bot.reply_to(message, "Silahkan ketik laporan/keluhan Anda. Sertakan tag `@username` warga yang bersangkutan jika ada masalah spesifik agar diproses sistem.")
                return
                
            # --- DETEKSI LAPORAN OTOMATIS & BROADCAST GRUP ---
            elif "lapor" in text.lower() or "masalah" in text.lower() or "keluhan" in text.lower():
                # 1. Simpan ke database laporan
                report = CitizenReport(str(uuid.uuid4()), user.id, user.full_name, text, datetime.datetime.now())
                self.report_repo.save(report)
                
                self.bot.reply_to(message, "✅ Laporan Anda berhasil dicatat ke sistem dan masuk menu 'Cek Laporan'.")
                
                # 2. Broadcast Notifikasi ke Grup Resmi RT
                if config.group_id:
                    try: self.bot.send_message(config.group_id, f"📢 *Laporan Warga Masuk*\n*Dari:* {user.full_name}\n*Isi:* {text}", parse_mode="Markdown")
                    except Exception as e: logger.error(f"Gagal broadcast laporan ke grup: {e}")
                
                # 3. Jalankan Pemeriksa Tag / Mention
                self.mention_handler.process_mentions(text, user.full_name)
                return

            # --- FALLBACK: AI CHATBOT (Kalau Di-Tag / Chat Private) ---
            bot_me = self.bot.get_me().username
            if (bot_me and f"@{bot_me}" in text) or message.chat.type == "private":
                def ai_task():
                    response = self.ai.generate_response(f"Sebagai asisten RT, bantu tanggapi warga ini dengan sopan: {text}")
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
