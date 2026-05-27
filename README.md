# Smart RT Monitoring System 🏠

Sistem terintegrasi untuk pemantauan ketertiban parkir RT dan transparansi keuangan menggunakan AI (YOLOv8) dan Telegram Bot.

## 🚀 Fitur Utama
- **IoT Monitoring:** Deteksi kendaraan menggunakan ESP32-CAM & AI (YOLOv8).
- **Automation:** Notifikasi otomatis ke Telegram warga jika terjadi pelanggaran.
- **Finance Transparency:** Integrasi Google Sheets untuk pelaporan kas RT.
- **Security:** *Environment-based configuration* untuk melindungi API Key.

## 🛠️ Tech Stack
- **Language:** Python
- **Framework:** python-telegram-bot, Flask
- **IoT:** ESP32-CAM, YOLOv8 (Inference)
- **Deployment:** Railway / Render
- **Database:** Google Sheets API

## 📋 Cara Menjalankan (Development)

1. Clone repositori ini:
   `git clone https://github.com/username/smart-rt-system.git`

2. Instal dependencies:
   `pip install -r requirements.txt`

3. Buat file `.env` di direktori utama dan isi dengan:
   ```text
   TELEGRAM_TOKEN=your_token_here
   ADMIN_ID=your_id_here
   GOOGLE_SHEET_ID=your_sheet_id_here