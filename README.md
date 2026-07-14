# ITrack Simulator 🚀

ITrack Simulator adalah aplikasi full-stack Simulator Perangkat Traccar dan Panel Kontrol premium. Simulator ini memungkinkan Anda untuk mensimulasikan pergerakan kendaraan secara real-time (Mobil, Motor, Bus, dll.) di sepanjang rute yang diambil dari OSRM, dan mentransmisikan data telemetri protokol OsmAnd langsung ke server Traccar Anda.

Simulator ini memiliki fitur UI glassmorphic yang responsif, penentuan koordinat peta, penyesuaian status offline otomatis (offline catch-up), dan penyimpanan database persisten.

---

## 🌟 Fitur & Fungsi Utama

### 1. Panel Kontrol & Dashboard Interaktif
* **Portal Autentikasi Glassmorphic**: Akses dashboard yang aman menggunakan kredensial standar (`admin` / `ihsan456`) dengan antarmuka tema gelap yang modern.
* **Peta Leaflet Interaktif**: Lihat telemetri perangkat real-time (koordinat, bearing, kecepatan, status, progres) di peta interaktif.
* **Kontrol Lapisan Peta**: Beralih secara dinamis antara lapisan peta **Tema Terang** (Light) dan **Tema Gelap** (Dark) langsung dari antarmuka kontrol peta.
* **Menu Samping Lipat (Collapsible Sidebar)**: UI sidebar bersih yang mencantumkan kartu perangkat aktif beserta namanya, dan memungkinkan penambahan/pengeditan perangkat.
* **Kontrol Layanan Global**: Jalankan atau hentikan seluruh layanan simulasi dengan satu sakelar global.

### 2. CRUD Perangkat & Parameter Kustom
* **Manajemen Perangkat Cepat**: Tambah, perbarui, dan hapus perangkat simulasi.
* **Pemetik Koordinat Peta**: Klik langsung pada peta Leaflet untuk menangkap koordinat Awal (Start) dan Akhir (End) daripada memasukkannya secara manual.
* **Rentang Kecepatan Kendaraan Kustom**: Konfigurasikan kecepatan minimum, rata-rata, dan maksimum untuk perilaku berkendara yang realistis.
* **Interval Transmisi Kustom**: Kontrol frekuensi pembaruan telemetri yang dikirim ke server Traccar (dalam hitungan detik).

### 3. Perutean Perjalanan Lanjutan & Jalur Multi-Titik
* **Rute Tunggal (Titik A ke B)**: Panggilan otomatis ke API OSRM untuk mengambil rute berkendara terpendek.
* **Perutean Multi-Titik (Multi-Waypoint)**: Tambahkan beberapa titik pemeriksaan perantara langsung di UI untuk membuat jalur perjalanan kustom yang kompleks.
* **Perutean Tempat & Sub-Tempat yang Ditentukan (Rute Pilihan)**: Pilih rute menggunakan pemilih dropdown hierarki Tempat dan Sub-Tempat (misalnya Jakarta, Bandung, Kediri). Mendukung penambahan beberapa titik pemeriksaan tempat, penyusunan ulang dengan seret-dan-lepas (drag-and-drop), pergeseran peta otomatis saat pemilihan rute, dan pengisian koordinat otomatis dari database SQLite.
* **Sistem Caching Lokal**: Menyimpan geometri rute sebagai file JSON dan GeoJSON di direktori `routes/` untuk mempercepat waktu pemuatan dan meminimalkan kueri API.

### 4. Fisika Realistis & Perilaku Simulasi
* **Fisika & Akselerasi Dinamis**: Mensimulasikan transisi kecepatan yang mulus berdasarkan berat dan jenis kendaraan.
* **Profil Khusus Kendaraan**: Batasan dan perilaku yang berbeda untuk Mobil, Sepeda Motor, dan Bus.
* **Perlambatan Acak**: Memperkenalkan kejadian dunia nyata yang acak seperti mengebut, berhenti di lampu merah, perlambatan di tikungan, dan penundaan akibat macet.
* **Kecepatan Feri Rute Laut**: Secara otomatis mendeteksi ketika rute melintasi bagian laut/samudra (misalnya penyeberangan Selat Sunda) dari mode langkah OSRM. Sistem akan menampilkan segmen ini sebagai garis putus-putus pada peta Leaflet dan mengubah kecepatan kendaraan menjadi **Kecepatan Feri** yang dikonfigurasi (default 25 km/jam) dengan status "ON FERRY".

### 5. Penjadwalan RIT & Laporan Run
* **Mode Perjalanan Fleksibel**:
  * **Sekali Jalan (Single Trip)**: Hentikan simulasi setelah tiba di tujuan.
  * **24-Jam Nonstop**: Terus berputar bolak-balik antara koordinat rute dengan waktu istirahat (layover) acak (misalnya 1 hingga 5 jam).
  * **Continuous RIT**: Berjalan bolak-balik sepanjang hari dengan keberangkatan setiap RIT yang diatur ketat berdasarkan jadwal **RIT-A Depart Time** dan **RIT-B Depart Time** (bukan waktu layover acak).
    * *Contoh*: Jika diatur `RIT-A Depart Time` = `09:15` dan `RIT-B Depart Time` = `21:15`. Kendaraan akan diam di lokasi awal (Start) hingga jam `09:15` untuk memulai perjalanan RIT-A. Ketika sampai di tujuan (misalkan pukul `18:25`), kendaraan akan parkir dan diam di lokasi tujuan menunggu hingga jam `21:15` tiba untuk secara otomatis berbalik arah dan memulai perjalanan pulang RIT-B. Setelah RIT-B selesai, kendaraan akan menunggu hingga keesokan harinya pukul `09:15` untuk mengulangi siklus.
* **Label RIT**: Mendukung pelacakan rute berangkat (`RIT-A`) dan rute kembali (`RIT-B`).
* **Jadwal Waktu RIT**: Mengatur jadwal keberangkatan dan kedatangan untuk RIT-A dan RIT-B.
* **Pencatatan Database RIT**: Secara otomatis mencatat waktu keberangkatan dan kedatangan aktual ke database di tabel `rit_runs`.
* **Portal Laporan RIT**: Cari, filter, dan tinjau log dari jalannya RIT yang selesai maupun sedang berlangsung dengan pembersihan otomatis (menyimpan data selama 4 hari).

### 6. Pemutaran Ulang Offline (Offline Catch-Up Replay)
* **Pencegahan Kesenjangan Telemetri**: Jika simulator dimulai ulang atau kehilangan koneksi, sistem akan menghitung durasi waktu saat simulator offline.
* **Pemutaran Ulang Penyangga (Buffer Playback)**: Memutar ulang hingga 200 posisi yang terlewat dengan stempel waktu historis yang benar pada interval cepat 0,05 detik untuk memulihkan kontinuitas status pada peta Traccar.

### 7. Deteksi Gerakan Pintar (Smart Movement Detection)
* **Penghematan Beban Server**: Menghentikan simulator mengirimkan permintaan HTTP POST yang tidak perlu ke server Traccar saat kendaraan sedang diam (misalnya: saat parkir, layover, atau berhenti di lampu merah).
* **Kondisi Pengiriman Telemetri**: Data telemetri hanya akan dikirim ke server Traccar jika memenuhi salah satu kondisi berikut:
  * Kendaraan bergerak sejauh **10 meter atau lebih** dari posisi terakhir yang berhasil dikirim.
  * Status mesin berubah (`ignition` berubah dari hidup ke mati, atau sebaliknya).
  * Status/label simulasi kendaraan berubah (misalnya berubah dari `CRUISING` ke `TRAFFIC_LIGHT` or `PARKED`).
  * Batas waktu **10 menit (Heartbeat)** terlampaui sejak pengiriman terakhir. Ini memastikan perangkat tidak dianggap benar-benar mati/offline pada peta Traccar selama periode diam yang lama.
* **UI Lokal Tetap Real-Time**: Panel kontrol UI lokal dan log simulator akan terus diperbarui secara real-time pada setiap detak interval, meskipun transmisi ke server Traccar luar sedang disaring/dihentikan.

---

## 🛠️ Stack Teknologi

* **Frontend**: HTML5, Vanilla CSS3 (Gaya Glassmorphic Kustom, Tema Gelap), Javascript (ES6), Leaflet.js (Perenderan peta & lapisan)
* **Backend**: Python 3, Flask (REST APIs & manajemen sesi), Flask-CORS, Threading
* **Database**: SQLite3 (penyimpanan persisten untuk pengaturan, perangkat, dan laporan)
* **Perutean (Routing)**: API OSRM (Open Source Routing Machine)

---

## 📁 Struktur Direktori

```text
├── simulator_server.py         # Server Flask Utama & pengelola thread simulasi
├── database.py                 # Schema database SQLite, migrasi, dan antarmuka kueri
├── map.html                    # UI Utama Panel Kontrol Leaflet
├── login.html                  # UI Login Glassmorphic
├── requirements.txt            # Dependensi Python
├── simulator.db                # File database SQLite (dihasilkan otomatis)
├── placesubplace29june2026.json # File benih database tempat dan sub-tempat
├── routes/                     # Direktori cache lokal untuk rute GeoJSON dan JSON
└── state/                      # Direktori cache lokal untuk titik pemulihan status simulasi perangkat
```

---

## 🚀 Instalasi & Penyiapan

### 1. Klon Repositori
```bash
git clone https://github.com/misbahulihsan/ITrackSimulator.git
cd ITrackSimulator
```

### 2. Siapkan Virtual Environment
Buat dan aktifkan virtual environment Python:
```bash
python3 -m venv venv
source venv/bin/activate  # Di macOS/Linux
# venv\Scripts\activate   # Di Windows
```

### 3. Instal Dependensi
```bash
pip install -r requirements.txt
```

### 4. Jalankan Server
Luncurkan server Flask simulator:
```bash
python simulator_server.py
```
Server akan berjalan pada alamat `http://localhost:8083`.

---

## 💾 Penerapan Produksi & Detail STB (Set Top Box)

Dalam lingkungan produksi, proyek ini diterapkan pada Set Top Box (STB) yang menjalankan Docker.

* **Alamat IP STB**: `192.168.18.8`
* **Jalur Produksi**: `/mnt/usb-docker/IhsanTraccarDeviceSimulator`
* **Alias Layanan Sistem** (ditentukan dalam `~/.zshrc`):
  * `sshstb`: Masuk ke STB via SSH (`ssh root@192.168.18.8`)

### Sinkronisasi Data dari STB ke Lokal
To fetch the latest production database and cached route files to your local environment, use `rsync` via `sshpass` (password: `ihsan123`):
```bash
# Sinkronisasi database SQLite
sshpass -p 'ihsan123' rsync -avz -e "ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no" root@192.168.18.8:/mnt/usb-docker/IhsanTraccarDeviceSimulator/simulator.db ./

# Sinkronisasi rute dalam cache
sshpass -p 'ihsan123' rsync -avz -e "ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no" root@192.168.18.8:/mnt/usb-docker/IhsanTraccarDeviceSimulator/routes/ ./routes/

# Sinkronisasi status pelacakan aktif
sshpass -p 'ihsan123' rsync -avz -e "ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no" root@192.168.18.8:/mnt/usb-docker/IhsanTraccarDeviceSimulator/state/ ./state/
```

---

## 🧭 Cara Penggunaan

1. Buka browser Anda dan navigasikan ke `http://localhost:8083`.
2. Masuk dengan kredensial:
   * **Username**: `admin`
   * **Password**: `ihsan456`
3. Tetapkan host Server Traccar Anda (misal `tracking.misbahulihsan.com`) di pengaturan.
4. Klik **+ Tambah Perangkat** untuk mendaftarkan simulator kendaraan baru:
   * Pilih **Jenis Kendaraan** (Mobil, Sepeda Motor, Bus).
   * Pilih **Koordinat Awal/Akhir** langsung dengan mengklik tombol "Pilih di Peta" dan memilih lokasi di peta. Atau pilih mode rute **Multi-titik** untuk menambahkan beberapa koordinat manual, atau pilih **Rute Pilihan** untuk memilih koordinat dari dropdown Tempat & Sub-Tempat yang telah ditentukan.
   * Konfigurasikan **Jenis Perjalanan** (Sekali Jalan, Nonstop, atau Continuous RIT) dan atur waktu keberangkatan/kedatangan RIT-A dan RIT-B yang relevan.
5. Klik **Simpan & Mulai**. Simulator akan mengambil rute, menyimpannya di cache, dan mulai mengirimkan posisi ke Server Traccar Anda.
6. Pantau progres langsung, kecepatan, bearing, dan jarak langsung di peta.
