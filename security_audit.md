# 🔐 Security Audit Report — IhsanTraccarDeviceSimulator

> **Tanggal Audit:** 2026-07-29  
> **Target:** `/Users/ihsan/DATA/PROJECT/IhsanTraccarDeviceSimulator`  
> **Deployment:** `https://simulator.misbahulihsan.com/` & `http://192.168.18.8:8083`  
> **Files Reviewed:** `simulator_server.py`, `database.py`, `login.html`, `.gitignore`

---

## 🚨 Ringkasan Temuan

| Severity | Jumlah |
|---|---|
| 🔴 CRITICAL | 3 |
| 🟠 HIGH | 4 |
| 🟡 MEDIUM | 2 |
| 🟢 LOW / INFO | 3 |

---

## 🔴 CRITICAL Vulnerabilities

### 1. Static Folder Serve Seluruh Direktori Project (`simulator_server.py` L.13)

```python
app = Flask(__name__, static_folder='.')  # ← SANGAT BERBAHAYA
```

**Dampak:** Dengan `static_folder='.'`, Flask secara otomatis mengekspose endpoint `/static/<filename>` yang me-mapping ke **seluruh root direktori project**. Artinya siapapun bisa mengakses:

```
GET /static/simulator.db       → Download database SQLite lengkap (semua device, settings)
GET /static/simulator.log      → Download log server lengkap
GET /static/config.json.bak    → Download backup config lama (berisi host tracking)
GET /static/placesubplace29june2026.json → Download data lokasi ~50KB
```

**Fix:**
```python
# Hapus static_folder='.' dari inisialisasi Flask
app = Flask(__name__)

# Dan buat static folder yang terisolasi, misal:
# app = Flask(__name__, static_folder='static_assets')
```

---

### 2. Hardcoded Credentials di Source Code (`simulator_server.py` L.1228)

```python
if username == "admin" and password == "ihsan456":
```

**Dampak:**
- Password plaintext langsung di source code
- Siapapun yang bisa akses repo / STB bisa login
- Tidak ada hashing (bcrypt, argon2, dll)
- Tidak ada rate limiting → **brute-force bebas**

**Fix:**
```python
import os, bcrypt

# Simpan di environment variable, bukan hardcode:
ADMIN_USERNAME = os.environ.get("APP_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH", "")  # bcrypt hash

def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode(), hashed.encode())
```

---

### 3. Hardcoded `secret_key` Flask yang Lemah (`simulator_server.py` L.14)

```python
app.secret_key = 'ihsan_traccar_secret_key_123'
```

**Dampak:**
- Secret key terekspose di source code (GitHub, STB filesystem)
- Jika diketahui attacker, **session cookie dapat dipalsukan** → bypass login tanpa password
- Nilai terlalu pendek dan mudah ditebak

**Fix:**
```python
import os, secrets
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
```
*Generate sekali:* `python -c "import secrets; print(secrets.token_hex(32))"`

---

## 🟠 HIGH Vulnerabilities

### 4. Tidak Ada Rate Limiting pada Login Endpoint

```python
@app.route('/api/login', methods=['POST'])
def login():
    # Tidak ada throttling sama sekali!
    if username == "admin" and password == "ihsan456":
```

**Dampak:** Attacker bisa melakukan ribuan percobaan login per detik (brute-force) karena tidak ada delay, lockout, atau CAPTCHA.

**Fix:** Install `flask-limiter` dan tambahkan:
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(app, key_func=get_remote_address)

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")  # Maks 5 percobaan per menit per IP
def login():
    ...
```

---

### 5. Kredensial WhatsApp Tersimpan sebagai Plaintext di Database (`simulator_server.py` L.1120-1122)

```python
api_key = database.get_setting("wa_api_key", "Aku123").strip()
number  = database.get_setting("wa_target_number", "+6285727255841")
api_url = database.get_setting("wa_api_url", "https://waha.misbahulihsan.com")
```

**Dampak:**
- Default API key `"Aku123"`, nomor HP, dan URL WAHA hardcoded di source code
- Siapapun yang bisa login ke simulator bisa melihat/ubah nomor HP dan API Key WhatsApp
- Jika DB file terekspose (lihat vuln #1), semua data ini langsung terbaca

**Fix:** Pindahkan ke environment variables, **jangan simpan di DB dalam plaintext** untuk data sensitif seperti API key.

---

### 6. CORS Terbuka untuk Semua Origin (`simulator_server.py` L.15)

```python
CORS(app)  # Izinkan semua domain → credentials rentan dibaca cross-origin
```

**Dampak:** Semua domain bisa membuat request ke API server ini. Jika session cookie tidak diamankan (`SameSite`, `HttpOnly`), ini membuka risiko CSRF.

**Fix:**
```python
CORS(app, origins=["https://simulator.misbahulihsan.com"], supports_credentials=True)
```

---

### 7. Potensi Path Traversal via `device_id` (`simulator_server.py` L.1361-1466)

```python
safe_name = device_id.lower().replace(" ", "_")  # Hanya replace spasi!
json_path = os.path.join(ROUTES_DIR, f"{safe_name}.json")
os.remove(path)  # Bisa hapus file di luar ROUTES_DIR!
```

**Dampak:** Jika attacker mengirim `device_id = "../simulator"`, maka:
- `safe_name = "../simulator"`
- `path = "routes/../simulator.json"` = `"simulator.json"` → bisa hapus file penting

**Fix:**
```python
import re
def sanitize_device_id(device_id: str) -> str:
    # Hanya izinkan alfanumerik, dash, underscore
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', device_id)
    return clean[:64]  # Batasi panjang

safe_name = sanitize_device_id(device_id).lower()
```

---

## 🟡 MEDIUM Issues

### 8. Tidak Ada Cookie Security Flags

Session cookie Flask tidak dikonfigurasi dengan flag keamanan. Di lingkungan HTTPS:
```python
# Tambahkan di konfigurasi Flask:
app.config['SESSION_COOKIE_HTTPONLY'] = True   # Cegah akses JavaScript ke cookie
app.config['SESSION_COOKIE_SECURE'] = True     # Hanya kirim lewat HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # Cegah CSRF
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # Session expire 1 jam
```

---

### 9. HTTP Security Headers Tidak Ada

Tidak ada middleware untuk menambahkan header keamanan standar. Risiko: Clickjacking, MIME sniffing, XSS via reflected responses.

**Fix:** Install `flask-talisman`:
```python
from flask_talisman import Talisman
Talisman(app,
    force_https=True,
    strict_transport_security=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "unpkg.com", "cdn.jsdelivr.net"],
    }
)
```

---

## 🟢 LOW / INFO

### 10. File `.bak` dan Log Tidak Boleh Di-deploy ke Server Publik

- `config.json.bak` — berisi traccar host
- `simulator.log` — berisi log lengkap termasuk koordinat GPS device
- `simulator.db.local_bak` — backup database

**Rekomendasi:** Tambahkan ke `.gitignore` dan pastikan file ini tidak ada di server produksi.

---

### 11. Logging Berlebihan (Info)

```python
print(f"[{device_id}] Sent position. Lat: {params['lat']:.5f}, Lon: {params['lon']:.5f}...")
```

Log yang sangat detail bisa membantu attacker memahami perilaku sistem jika `simulator.log` bisa diakses.

---

### 12. Server Berjalan di `host='0.0.0.0'` Tanpa Reverse Proxy

```python
app.run(host='0.0.0.0', port=8083, debug=False, threaded=True)
```

Flask development server sebaiknya **tidak** langsung diekspose ke publik. Gunakan Gunicorn/uWSGI di belakang Nginx.

---

## ✅ Yang Sudah Bagus

- ✅ Query database menggunakan **parameterized queries** (aman dari SQL Injection)
- ✅ `before_request` untuk auth check sudah ada dan bekerja dengan benar
- ✅ `.gitignore` sudah mengecualikan `.db`, `state/`, `routes/`
- ✅ `debug=False` di production

---

## 🛠️ Prioritas Perbaikan

| # | Tindakan | File | Prioritas |
|---|---|---|---|
| 1 | Ganti `static_folder='.'` ke direktori terisolasi | `simulator_server.py` | 🔴 SEGERA |
| 2 | Pindahkan credentials ke env variable, hash password | `simulator_server.py` | 🔴 SEGERA |
| 3 | Generate secret_key dari env variable | `simulator_server.py` | 🔴 SEGERA |
| 4 | Tambahkan rate limiting di `/api/login` | `simulator_server.py` | 🟠 TINGGI |
| 5 | Sanitasi `device_id` sebelum dipakai sebagai nama file | `simulator_server.py` | 🟠 TINGGI |
| 6 | Batasi CORS ke domain spesifik | `simulator_server.py` | 🟠 TINGGI |
| 7 | Tambahkan cookie security flags | `simulator_server.py` | 🟡 MEDIUM |
| 8 | Tambahkan HTTP security headers | `simulator_server.py` | 🟡 MEDIUM |
| 9 | Hapus file `.bak` dan `.log` dari server | Server | 🟢 LOW |
