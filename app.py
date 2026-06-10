import os
import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

def get_db_connection():
    db_path = "/app/data/satria_rt.db" if os.path.exists("/app/data") else "satria_rt.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Fungsi buat mastiin tabel udah ada
def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS kas_transactions 
                    (id INTEGER PRIMARY KEY, nama TEXT, kategori TEXT, nominal REAL, created_at TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS citizen_reports 
                    (id INTEGER PRIMARY KEY, reporter_name TEXT, content TEXT, created_at TIMESTAMP)''')
    conn.commit()
    conn.close()

@app.route('/')
def dashboard():
    init_db() # Kita panggil biar dia bikin tabel kalau belum ada
    conn = get_db_connection()
    kas = conn.execute('SELECT * FROM kas_transactions ORDER BY created_at DESC LIMIT 10').fetchall()
    reports = conn.execute('SELECT * FROM citizen_reports ORDER BY created_at DESC LIMIT 10').fetchall()
    row = conn.execute('SELECT SUM(nominal) FROM kas_transactions').fetchone()
    total_kas = row[0] if row[0] else 0
    conn.close()
    return render_template('index.html', kas=kas, reports=reports, total_kas=total_kas)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
