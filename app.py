import os
import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

# Logika pinter nyari database (Local vs Railway)
def get_db_connection():
    db_path = "/app/data/satria_rt.db" if os.path.exists("/app/data") else "satria_rt.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # Biar gampang narik data by nama kolom
    return conn

@app.route('/')
def dashboard():
    conn = get_db_connection()
    
    # Ambil data Iuran
    kas_data = conn.execute('SELECT * FROM kas_transactions ORDER BY created_at DESC LIMIT 10').fetchall()
    
    # Ambil data Laporan
    reports_data = conn.execute('SELECT * FROM citizen_reports ORDER BY created_at DESC LIMIT 10').fetchall()
    
    # Hitung Total Kas
    total_kas_row = conn.execute('SELECT SUM(nominal) FROM kas_transactions').fetchone()
    total_kas = total_kas_row[0] if total_kas_row[0] else 0
    
    conn.close()
    
    return render_template('index.html', kas=kas_data, reports=reports_data, total_kas=total_kas)

if __name__ == '__main__':
    # Jalanin server di port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
