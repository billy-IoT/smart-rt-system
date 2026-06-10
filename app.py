import os
import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

# Fungsi koneksi database yang aman untuk Railway & Lokal
def get_db_connection():
    db_path = "/app/data/satria_rt.db" if os.path.exists("/app/data") else "satria_rt.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    try:
        conn = get_db_connection()
        # Ambil 10 data terbaru
        kas = conn.execute('SELECT * FROM kas_transactions ORDER BY created_at DESC LIMIT 10').fetchall()
        reports = conn.execute('SELECT * FROM citizen_reports ORDER BY created_at DESC LIMIT 10').fetchall()
        # Hitung total kas
        total_kas_row = conn.execute('SELECT SUM(nominal) FROM kas_transactions').fetchone()
        total_kas = total_kas_row[0] if total_kas_row[0] else 0
        conn.close()
        
        return render_template('index.html', kas=kas, reports=reports, total_kas=total_kas)
    except Exception as e:
        return f"Database Error: {str(e)}", 500

if __name__ == '__main__':
    # Railway kasih port via env, default ke 8080 kalau gak ada
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)    app.run(host='0.0.0.0', port=port)
