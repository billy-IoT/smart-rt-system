import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template

app = Flask(__name__)

# Ambil dari env var Railway — tidak ada hardcode kredensial di sini
DB_URL = os.getenv("DB_URL", "")
if not DB_URL:
    raise RuntimeError("DB_URL belum di-set di environment variables!")

def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_conn()
    with conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    telegram_id TEXT UNIQUE,
                    full_name TEXT,
                    username TEXT,
                    created_at TIMESTAMPTZ
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS kas_transactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    nama TEXT,
                    kategori TEXT,
                    nominal INTEGER,
                    created_at TIMESTAMPTZ
                )
            """)
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
                    created_at TIMESTAMPTZ
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS citizen_reports (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    reporter_name TEXT,
                    content TEXT,
                    created_at TIMESTAMPTZ
                )
            """)
    conn.close()

init_db()

@app.route('/')
def dashboard():
    conn = get_conn()
    with conn.cursor() as c:
        c.execute("""
            SELECT nama, kategori, nominal, created_at
            FROM kas_transactions
            ORDER BY created_at DESC LIMIT 10
        """)
        kas = c.fetchall()

        c.execute("""
            SELECT reporter_name, content, created_at
            FROM citizen_reports
            ORDER BY created_at DESC LIMIT 10
        """)
        reports = c.fetchall()

        c.execute("SELECT SUM(nominal) AS total FROM kas_transactions")
        row = c.fetchone()
        total_kas = row["total"] if row["total"] else 0

        c.execute("""
            SELECT nama, kategori, nominal, created_at
            FROM pending_iuran
            WHERE status = 'PENDING'
            ORDER BY created_at DESC
        """)
        pending = c.fetchall()

    conn.close()
    return render_template('index.html',
                           kas=kas,
                           reports=reports,
                           total_kas=total_kas,
                           pending=pending)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
