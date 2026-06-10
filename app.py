import os
import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

# Fungsi buat konek ke database
def get_db_connection():
    # Cek folder /app/data (Railway Volume) atau pakai folder lokal
    db_path = "/app/data/satria_rt.db" if os.path.exists("/app/data") else "satria_rt.db"
    
    # check_same_thread=False penting biar gak error pas dipake bareng bot
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    try:
        conn = get_db_connection()
        # Ambil data iuran terbaru
        kas = conn.execute('SELECT * FROM kas_transactions ORDER BY created_at DESC LIMIT 10').fetchall()
        # Ambil laporan warga
        reports = conn.execute('SELECT * FROM citizen_reports ORDER BY created_at DESC LIMIT 10').fetchall()
        # Hitung total kas
        total_kas_row = conn.execute('SELECT SUM(nominal) FROM kas_transactions').fetchone()
        total_kas = total_kas_row[0] if total_kas_row[0] else 0
        conn.close()
        
        return render_template('index.html', kas=kas, reports=reports, total_kas=total_kas)
    except Exception as e:
        return f"Error Database: {str(e)}"

if __name__ == '__main__':
    # Railway nentuin port lewat variable, kalau gak ada kita pake 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
