from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import signal
import sys
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import asyncpg
from aiohttp import web
from groq import Groq
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =====================================================================
# 1. LOGGING
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("SATRIA")


# =====================================================================
# 2. CONFIGURATION
# =====================================================================
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    groq_key:  str = os.getenv("GROQ_API_KEY", "")
    admin_id:  str = str(os.getenv("ADMIN_ID", ""))
    group_id:  str = str(os.getenv("CHAT_ID_GRUP", ""))
    db_url:    str = os.getenv("DB_URL", "")
    port:      int = int(os.getenv("PORT", "8080"))

    @classmethod
    def validate(cls):
        missing = [k for k in ("bot_token", "groq_key", "db_url") if not getattr(cls, k)]
        if missing:
            logger.critical(f"Env var belum di-set: {', '.join(missing).upper()}")
            sys.exit(1)


Config.validate()


# =====================================================================
# 3. DATA MODELS
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
class PendingIuran:
    id: str
    user_id: str
    telegram_id: str
    nama: str
    kategori: str
    nominal: int
    photo_file_id: str
    status: str
    created_at: datetime.datetime


@dataclass(slots=True)
class CitizenReport:
    id: str
    user_id: str
    reporter_name: str
    content: str
    created_at: datetime.datetime


# =====================================================================
# 4. DATABASE  (asyncpg)
# =====================================================================
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(Config.db_url, min_size=2, max_size=10)
    return _pool


async def init_database():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                telegram_id TEXT UNIQUE,
                full_name TEXT,
                username TEXT,
                created_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kas_transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                nama TEXT,
                kategori TEXT,
                nominal INTEGER,
                created_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_iuran (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                telegram_id TEXT,
                nama TEXT,
                kategori TEXT,
                nominal INTEGER,
                photo_file_id TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS citizen_reports (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                reporter_name TEXT,
                content TEXT,
                created_at TIMESTAMPTZ
            )
        """)
    logger.info("PostgreSQL initialized.")


# =====================================================================
# 5. REPOSITORIES  (async)
# =====================================================================
class UserRepository:
    async def save(self, user: User):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (id, telegram_id, full_name, username, created_at)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    username  = EXCLUDED.username
            """, user.id, user.telegram_id, user.full_name, user.username, user.created_at)

    async def find_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", str(telegram_id)
            )
        if not row:
            return None
        return User(row["id"], row["telegram_id"], row["full_name"],
                    row["username"], row["created_at"])

    async def find_by_username(self, username: str) -> Optional[User]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE LOWER(username) = LOWER($1)", username
            )
        if not row:
            return None
        return User(row["id"], row["telegram_id"], row["full_name"],
                    row["username"], row["created_at"])


class KasRepository:
    async def save(self, trx: KasTransaction):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO kas_transactions (id, user_id, nama, kategori, nominal, created_at)
                VALUES ($1,$2,$3,$4,$5,$6)
            """, trx.id, trx.user_id, trx.nama, trx.kategori, trx.nominal, trx.created_at)

    async def get_summary(self) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows  = await conn.fetch(
                "SELECT kategori, SUM(nominal) AS total FROM kas_transactions GROUP BY kategori"
            )
            grand = await conn.fetchval("SELECT COALESCE(SUM(nominal),0) FROM kas_transactions")
        if not rows:
            return "📉 Data Kas masih kosong."
        res = "📊 *Laporan Total Kas RT*\n\n"
        for row in rows:
            res += f"🔹 {row['kategori'].capitalize()}: Rp {row['total']:,}\n"
        res += f"\n💰 *Total Seluruh Kas: Rp {grand:,}*"
        return res


class PendingIuranRepository:
    async def save(self, p: PendingIuran):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO pending_iuran
                    (id, user_id, telegram_id, nama, kategori,
                     nominal, photo_file_id, status, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """, p.id, p.user_id, p.telegram_id, p.nama, p.kategori,
                p.nominal, p.photo_file_id, p.status, p.created_at)

    async def find_by_id(self, pid: str) -> Optional[PendingIuran]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM pending_iuran WHERE id = $1", pid)
        if not row:
            return None
        return PendingIuran(row["id"], row["user_id"], row["telegram_id"],
                            row["nama"], row["kategori"], row["nominal"],
                            row["photo_file_id"], row["status"], row["created_at"])

    async def update_status(self, pid: str, status: str):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE pending_iuran SET status=$1 WHERE id=$2", status, pid
            )


class ReportRepository:
    async def save(self, report: CitizenReport):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO citizen_reports (id, user_id, reporter_name, content, created_at)
                VALUES ($1,$2,$3,$4,$5)
            """, report.id, report.user_id, report.reporter_name,
                report.content, report.created_at)

    async def get_all(self) -> list[CitizenReport]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM citizen_reports ORDER BY created_at DESC"
            )
        return [CitizenReport(r["id"], r["user_id"], r["reporter_name"],
                              r["content"], r["created_at"]) for r in rows]


# =====================================================================
# 6. AI ORCHESTRATOR  (sync Groq dibungkus executor)
# =====================================================================
class AIOrchestrator:
    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)

    def _call_groq(self, prompt: str) -> str:
        try:
            res = self._client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content":
                        "Anda adalah SATRIA, asisten RT digital yang cerdas, tegas, dan solutif."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
            )
            return res.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq error: {e}")
            return "Mohon maaf, sistem AI sedang offline."

    async def generate_response(self, prompt: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._call_groq, prompt)


# =====================================================================
# 7. STATE MACHINE
# =====================================================================
class StateMachine:
    def __init__(self):
        self._states: dict[str, dict[str, Any]] = {}

    def set(self, tid: str, key: str, value: Any):
        self._states.setdefault(tid, {})[key] = value

    def get(self, tid: str, key: str) -> Any:
        return self._states.get(tid, {}).get(key)

    def clear(self, tid: str):
        self._states.pop(tid, None)


# =====================================================================
# 8. KEYBOARDS
# =====================================================================
def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.keyboard = [
        ["💰 Lapor Iuran", "📋 Lapor Masalah"],
        ["📊 Cek Kas RT",  "📋 Cek Laporan"],
    ]
    return kb


# =====================================================================
# 9. TELEGRAM HANDLERS
# =====================================================================
class BotHandlers:
    def __init__(self):
        self.user_repo    = UserRepository()
        self.kas_repo     = KasRepository()
        self.pending_repo = PendingIuranRepository()
        self.report_repo  = ReportRepository()
        self.ai           = AIOrchestrator(Config.groq_key)
        self.sm           = StateMachine()

    async def _get_or_create_user(self, from_user) -> User:
        tid  = str(from_user.id)
        user = await self.user_repo.find_by_telegram_id(tid)
        if not user:
            user = User(
                id          = str(uuid.uuid4()),
                telegram_id = tid,
                full_name   = from_user.first_name or "Warga",
                username    = from_user.username or "",
                created_at  = datetime.datetime.now(),
            )
            await self.user_repo.save(user)
        return user

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await self._get_or_create_user(update.effective_user)
        await update.message.reply_text(
            "🤖 Sistem *SATRIA RT Enterprise v10* Aktif.\n\nSelamat datang!",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )

    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        call = update.callback_query
        await call.answer()
        data = call.data or ""

        if not (data.startswith("APPROVE:") or data.startswith("REJECT:")):
            return

        if str(call.from_user.id) != Config.admin_id:
            await call.answer("⛔ Hanya admin yang bisa melakukan ini.", show_alert=True)
            return

        action, pending_id = data.split(":", 1)
        pending = await self.pending_repo.find_by_id(pending_id)

        if not pending:
            await call.answer("❌ Data tidak ditemukan.", show_alert=True)
            return

        if pending.status != "PENDING":
            await call.answer(f"⚠️ Sudah diproses ({pending.status}).", show_alert=True)
            return

        if action == "APPROVE":
            trx = KasTransaction(
                id         = str(uuid.uuid4()),
                user_id    = pending.user_id,
                nama       = pending.nama,
                kategori   = pending.kategori,
                nominal    = pending.nominal,
                created_at = datetime.datetime.now(),
            )
            await self.kas_repo.save(trx)
            await self.pending_repo.update_status(pending_id, "APPROVED")
            suffix    = "\n\n✅ *DISETUJUI*"
            warga_msg = (
                f"🎉 *Iuran Anda Telah Diverifikasi!*\n\n"
                f"📋 Nama     : {pending.nama}\n"
                f"📂 Kategori : {pending.kategori}\n"
                f"💵 Nominal  : Rp {pending.nominal:,}\n\n"
                f"Dana Anda telah resmi masuk ke Kas RT. Terima kasih! 🙏"
            )
        else:
            await self.pending_repo.update_status(pending_id, "REJECTED")
            suffix    = "\n\n❌ *DITOLAK*"
            warga_msg = (
                f"❌ *Iuran Anda Ditolak oleh Admin*\n\n"
                f"📋 Nama     : {pending.nama}\n"
                f"📂 Kategori : {pending.kategori}\n"
                f"💵 Nominal  : Rp {pending.nominal:,}\n\n"
                f"Silahkan hubungi pengurus RT untuk informasi lebih lanjut."
            )

        try:
            await call.edit_message_caption(
                caption    = (call.message.caption or "") + suffix,
                parse_mode = "Markdown",
            )
        except Exception:
            pass

        try:
            await ctx.bot.send_message(pending.telegram_id, warga_msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Gagal beritahu warga: {e}")

        logger.info(f"Approval selesai: id={pending_id}, action={action}")

    async def _iuran_initiate(self, tid: str, update: Update):
        self.sm.set(tid, "flow", "IURAN")
        self.sm.set(tid, "step", "NAMA")
        await update.message.reply_text(
            "📝 Silahkan masukkan *Nama Lengkap Penyetor*:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def _iuran_process(self, tid: str, update: Update, user: User) -> bool:
        if self.sm.get(tid, "flow") != "IURAN":
            return False

        step    = self.sm.get(tid, "step")
        message = update.message

        if step == "NAMA":
            if not message.text:
                return True
            self.sm.set(tid, "nama", message.text)
            self.sm.set(tid, "step", "KATEGORI")
            kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.keyboard = [["Kebersihan", "Keamanan", "Sosial"]]
            await message.reply_text("Pilih Kategori Iuran:", reply_markup=kb)

        elif step == "KATEGORI":
            if not message.text:
                return True
            self.sm.set(tid, "kategori", message.text)
            self.sm.set(tid, "step", "NOMINAL")
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.keyboard = [
                ["Rp 10.000", "Rp 20.000"],
                ["Rp 50.000", "Rp 100.000"],
                ["Input Manual"],
            ]
            await message.reply_text("Pilih nominal iuran (Minimal Rp 10.000):", reply_markup=kb)

        elif step == "NOMINAL":
            if not message.text:
                return True
            if message.text == "Input Manual":
                await message.reply_text(
                    "Ketik angka nominal saja (contoh: 15000):",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return True
            clean = re.sub(r"\D", "", message.text)
            if not clean:
                await message.reply_text("❌ Format salah. Pilih tombol atau ketik angka:")
                return True
            nominal_value = int(clean)
            if nominal_value < 10_000:
                await message.reply_text(
                    "❌ *Minimal Rp10.000.* Silahkan masukkan nominal yang valid:",
                    parse_mode="Markdown",
                )
                return True
            self.sm.set(tid, "nominal", nominal_value)
            self.sm.set(tid, "step", "FOTO")
            await message.reply_text(
                "Kirimkan *Foto Bukti Transfer* 📸:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove(),
            )

        elif step == "FOTO":
            if not message.photo:
                await message.reply_text("Harap kirimkan gambar bukti transfer.")
                return True
            nama     = self.sm.get(tid, "nama")
            kategori = self.sm.get(tid, "kategori")
            nominal  = self.sm.get(tid, "nominal")
            photo_id = message.photo[-1].file_id

            pending = PendingIuran(
                id            = str(uuid.uuid4()),
                user_id       = user.id,
                telegram_id   = tid,
                nama          = nama,
                kategori      = kategori,
                nominal       = nominal,
                photo_file_id = photo_id,
                status        = "PENDING",
                created_at    = datetime.datetime.now(),
            )
            await self.pending_repo.save(pending)
            self.sm.clear(tid)

            await message.reply_text(
                f"✅ *Iuran Terkirim & Menunggu Verifikasi Admin*\n\n"
                f"📋 Nama     : {nama}\n"
                f"📂 Kategori : {kategori}\n"
                f"💵 Nominal  : Rp {nominal:,}\n\n"
                f"Anda akan mendapat notifikasi setelah admin memverifikasi.",
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
            asyncio.create_task(self._notify_admin(pending, update))

        return True

    async def _notify_admin(self, p: PendingIuran, update: Update):
        if not Config.admin_id:
            logger.warning("ADMIN_ID belum di-set.")
            return
        caption = (
            f"🔔 *Permohonan Verifikasi Iuran*\n\n"
            f"👤 Nama     : {p.nama}\n"
            f"📂 Kategori : {p.kategori}\n"
            f"💵 Nominal  : Rp {p.nominal:,}\n"
            f"🕒 Waktu    : {p.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"ID: `{p.id}`"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Setujui", callback_data=f"APPROVE:{p.id}"),
            InlineKeyboardButton("❌ Tolak",   callback_data=f"REJECT:{p.id}"),
        ]])
        try:
            await update.get_bot().send_photo(
                Config.admin_id, p.photo_file_id,
                caption=caption, parse_mode="Markdown", reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"Gagal kirim notif admin: {e}")

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        tid  = str(update.effective_user.id)
        user = await self._get_or_create_user(update.effective_user)

        if await self._iuran_process(tid, update, user):
            return

        text = update.message.text or update.message.caption or ""

        if text == "💰 Lapor Iuran":
            await self._iuran_initiate(tid, update)

        elif text == "📊 Cek Kas RT":
            await update.message.reply_text(
                await self.kas_repo.get_summary(), parse_mode="Markdown"
            )

        elif text == "📋 Cek Laporan":
            reports = await self.report_repo.get_all()
            if not reports:
                await update.message.reply_text("📭 Belum ada laporan warga masuk.")
            else:
                res = "📋 *Daftar Keluhan & Laporan Warga RT*\n\n"
                for idx, r in enumerate(reports, 1):
                    res += (
                        f"{idx}. *Pelapor:* {r.reporter_name}\n"
                        f"📝 *Keluhan:* {r.content}\n"
                        f"🕒 *Tanggal:* {r.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
                    )
                await update.message.reply_text(res, parse_mode="Markdown")

        elif text == "📋 Lapor Masalah":
            await update.message.reply_text(
                "Silahkan ketik laporan/keluhan Anda. "
                "Sertakan `@username` jika ada warga yang terlibat.",
                parse_mode="Markdown",
            )

        elif any(kw in text.lower() for kw in ("lapor", "masalah", "keluhan")):
            report = CitizenReport(
                str(uuid.uuid4()), user.id, user.full_name, text, datetime.datetime.now()
            )
            await self.report_repo.save(report)
            await update.message.reply_text("✅ Laporan berhasil dicatat ke sistem.")

            if Config.group_id:
                try:
                    await ctx.bot.send_message(
                        Config.group_id,
                        f"📢 *Laporan Warga Masuk*\n*Dari:* {user.full_name}\n*Isi:* {text}",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            asyncio.create_task(
                self._process_mentions(text, user.full_name, update)
            )

        else:
            bot_user = await ctx.bot.get_me()
            if (bot_user.username and f"@{bot_user.username}" in text) \
                    or update.message.chat.type == "private":
                asyncio.create_task(self._ai_reply(text, update))

    async def _ai_reply(self, text: str, update: Update):
        response = await self.ai.generate_response(f"Sebagai asisten RT, jawab: {text}")
        try:
            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Gagal kirim AI reply: {e}")

    async def _process_mentions(self, text: str, sender_name: str, update: Update):
        for uname in re.findall(r"@(\w+)", text):
            prompt = (
                f"Anda adalah SATRIA, asisten RT. Warga bernama {sender_name} melaporkan masalah. "
                f"Dia mengetag @{uname} sebagai pihak yang bermasalah. "
                f"Isi laporan: '{text}'. "
                f"Buat teguran tegas, logis, dan profesional dalam bahasa Indonesia untuk @{uname}."
            )
            ai_msg = await self.ai.generate_response(prompt)

            if Config.group_id:
                try:
                    await update.get_bot().send_message(
                        Config.group_id,
                        f"⚠️ *Teguran Terbuka untuk @{uname}:*\n\n{ai_msg}",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.error(f"Gagal kirim teguran ke grup: {e}")

            target = await self.user_repo.find_by_username(uname)
            if target:
                try:
                    await update.get_bot().send_message(
                        target.telegram_id,
                        f"🚨 *Peringatan Keamanan Lingkungan RT*\n\n{ai_msg}",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.error(f"Gagal japri target: {e}")


# =====================================================================
# 10. WEB DASHBOARD  (aiohttp)
# =====================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SATRIA RT — Dashboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0f172a; color: #e2e8f0;
      min-height: 100vh; padding: 2rem 1rem;
    }}
    header {{ text-align: center; margin-bottom: 2rem; }}
    header h1 {{ font-size: 2rem; color: #38bdf8; letter-spacing: .05em; }}
    header p  {{ color: #94a3b8; margin-top: .25rem; }}
    .stats {{
      display: flex; gap: 1rem; flex-wrap: wrap;
      justify-content: center; margin-bottom: 2rem;
    }}
    .stat-card {{
      background: #1e293b; border-radius: 12px;
      padding: 1.25rem 2rem; text-align: center; flex: 1; min-width: 160px;
    }}
    .stat-card .label {{ font-size: .75rem; color: #64748b; text-transform: uppercase; }}
    .stat-card .value {{ font-size: 1.75rem; font-weight: 700; color: #38bdf8; }}
    .grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.5rem; max-width: 1200px; margin: 0 auto;
    }}
    section {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; }}
    section h2 {{
      font-size: 1rem; font-weight: 600; color: #7dd3fc;
      border-bottom: 1px solid #334155; padding-bottom: .75rem; margin-bottom: 1rem;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: .875rem; }}
    th {{ color: #64748b; text-align: left; padding: .5rem .75rem; font-weight: 500; }}
    td {{ padding: .5rem .75rem; border-top: 1px solid #1e293b; }}
    tr:nth-child(even) td {{ background: rgba(15,23,42,.2); }}
    .badge {{
      display: inline-block; padding: .2rem .55rem; border-radius: 9999px;
      font-size: .7rem; font-weight: 600;
    }}
    .badge-pending  {{ background: #78350f; color: #fcd34d; }}
    .badge-approved {{ background: #14532d; color: #86efac; }}
    .badge-rejected {{ background: #7f1d1d; color: #fca5a5; }}
    .empty {{ color: #64748b; text-align: center; padding: 1.5rem; }}
  </style>
</head>
<body>
  <header>
    <h1>🏘️ SATRIA RT Dashboard</h1>
    <p>Sistem Administrasi Terpadu RT Digital</p>
  </header>
  <div class="stats">
    <div class="stat-card">
      <div class="label">Total Kas</div>
      <div class="value">Rp {total_kas:,}</div>
    </div>
    <div class="stat-card">
      <div class="label">Transaksi</div>
      <div class="value">{jumlah_trx}</div>
    </div>
    <div class="stat-card">
      <div class="label">Laporan</div>
      <div class="value">{jumlah_laporan}</div>
    </div>
    <div class="stat-card">
      <div class="label">Pending</div>
      <div class="value">{jumlah_pending}</div>
    </div>
  </div>
  <div class="grid">
    <section>
      <h2>💰 Transaksi Kas Terbaru</h2>
      {tabel_kas}
    </section>
    <section>
      <h2>📋 Laporan Warga Terbaru</h2>
      {tabel_laporan}
    </section>
    <section>
      <h2>⏳ Iuran Pending Verifikasi</h2>
      {tabel_pending}
    </section>
  </div>
</body>
</html>"""


def _rows_to_kas_table(rows) -> str:
    if not rows:
        return '<p class="empty">Belum ada transaksi.</p>'
    out = "<table><thead><tr><th>Nama</th><th>Kategori</th><th>Nominal</th><th>Tanggal</th></tr></thead><tbody>"
    for r in rows:
        tgl = r["created_at"].strftime("%d/%m/%Y") if r["created_at"] else "-"
        out += f"<tr><td>{r['nama']}</td><td>{r['kategori']}</td><td>Rp {r['nominal']:,}</td><td>{tgl}</td></tr>"
    out += "</tbody></table>"
    return out


def _rows_to_report_table(rows) -> str:
    if not rows:
        return '<p class="empty">Belum ada laporan.</p>'
    out = "<table><thead><tr><th>Pelapor</th><th>Isi</th><th>Tanggal</th></tr></thead><tbody>"
    for r in rows:
        tgl     = r["created_at"].strftime("%d/%m/%Y") if r["created_at"] else "-"
        content = str(r["content"])[:60] + ("…" if len(str(r["content"])) > 60 else "")
        out += f"<tr><td>{r['reporter_name']}</td><td>{content}</td><td>{tgl}</td></tr>"
    out += "</tbody></table>"
    return out


def _rows_to_pending_table(rows) -> str:
    if not rows:
        return '<p class="empty">Tidak ada iuran pending.</p>'
    out = "<table><thead><tr><th>Nama</th><th>Kategori</th><th>Nominal</th><th>Status</th></tr></thead><tbody>"
    for r in rows:
        st  = r["status"].upper()
        cls = {"PENDING": "badge-pending", "APPROVED": "badge-approved",
               "REJECTED": "badge-rejected"}.get(st, "badge-pending")
        out += (f"<tr><td>{r['nama']}</td><td>{r['kategori']}</td>"
                f"<td>Rp {r['nominal']:,}</td>"
                f'<td><span class="badge {cls}">{st}</span></td></tr>')
    out += "</tbody></table>"
    return out


async def web_dashboard(request: web.Request) -> web.Response:
    pool = await get_pool()
    async with pool.acquire() as conn:
        kas     = await conn.fetch(
            "SELECT nama, kategori, nominal, created_at FROM kas_transactions ORDER BY created_at DESC LIMIT 10"
        )
        reports = await conn.fetch(
            "SELECT reporter_name, content, created_at FROM citizen_reports ORDER BY created_at DESC LIMIT 10"
        )
        total   = await conn.fetchval("SELECT COALESCE(SUM(nominal),0) FROM kas_transactions")
        pending = await conn.fetch(
            "SELECT nama, kategori, nominal, status, created_at FROM pending_iuran ORDER BY created_at DESC LIMIT 20"
        )

    html = HTML_TEMPLATE.format(
        total_kas      = total or 0,
        jumlah_trx     = len(kas),
        jumlah_laporan = len(reports),
        jumlah_pending = sum(1 for r in pending if r["status"] == "PENDING"),
        tabel_kas      = _rows_to_kas_table(kas),
        tabel_laporan  = _rows_to_report_table(reports),
        tabel_pending  = _rows_to_pending_table(pending),
    )
    return web.Response(text=html, content_type="text/html")


# =====================================================================
# 11. ENTRYPOINT
# =====================================================================
async def main():
    await init_database()

    handlers = BotHandlers()
    tg_app = (
        Application.builder()
        .token(Config.bot_token)
        .build()
    )
    tg_app.add_handler(CommandHandler("start", handlers.cmd_start))
    tg_app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    tg_app.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO, handlers.handle_message)
    )

    web_app = web.Application()
    web_app.router.add_get("/", web_dashboard)
    runner  = web.AppRunner(web_app)
    await runner.setup()
    site    = web.TCPSite(runner, "0.0.0.0", Config.port)
    await site.start()
    logger.info(f"Dashboard berjalan di http://0.0.0.0:{Config.port}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async with tg_app:
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("SATRIA polling dimulai. Ctrl+C untuk berhenti.")
        await stop_event.wait()
        logger.info("Shutdown...")
        await tg_app.updater.stop()
        await tg_app.stop()

    await runner.cleanup()
    if _pool:
        await _pool.close()
    logger.info("SATRIA berhenti dengan bersih.")


if __name__ == "__main__":
    asyncio.run(main())
