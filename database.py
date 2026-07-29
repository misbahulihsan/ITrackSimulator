import sqlite3
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = "simulatorgps.db"
CONFIG_PATH = "config.json"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Create settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)
    
    # Create devices table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT NOT NULL,
        start_lat REAL NOT NULL,
        start_lon REAL NOT NULL,
        end_lat REAL NOT NULL,
        end_lon REAL NOT NULL,
        min_speed INTEGER NOT NULL,
        avg_speed INTEGER NOT NULL,
        max_speed INTEGER NOT NULL,
        interval INTEGER NOT NULL,
        start_time TEXT,
        trip_type TEXT DEFAULT 'single',
        return_time TEXT,
        nonstop_layover_min INTEGER DEFAULT 60,
        nonstop_layover_max INTEGER DEFAULT 60,
        waypoints TEXT
    )
    """)
    
    try:
        cursor.execute("ALTER TABLE devices ADD COLUMN nonstop_layover_min INTEGER DEFAULT 60")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE devices ADD COLUMN nonstop_layover_max INTEGER DEFAULT 60")
    except sqlite3.OperationalError:
        pass
    
    # Add columns for RIT scheduling, name, waypoints, route_mode, and rit_label
    for col in ["rita_depart", "rita_arrive", "ritb_depart", "ritb_arrive", "name", "waypoints", "route_mode", "rit_label"]:
        try:
            cursor.execute(f"ALTER TABLE devices ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE devices ADD COLUMN ferry_speed INTEGER DEFAULT 25")
    except sqlite3.OperationalError:
        pass

    # Create RIT runs report table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rit_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        rit_type TEXT NOT NULL,
        date TEXT NOT NULL,
        scheduled_depart TEXT,
        actual_depart TEXT,
        scheduled_arrive TEXT,
        actual_arrive TEXT,
        status TEXT
    )
    """)
    
    # Create users table for database-based login
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT
    )
    """)

    # ── New Architecture Tables ─────────────────────────────────────────────────────

    # Servers — daftar server Traccar tujuan
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        host TEXT NOT NULL,
        port INTEGER DEFAULT 443,
        protocol TEXT DEFAULT 'https',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Trips — definisi perjalanan (tanpa device)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_lat REAL NOT NULL DEFAULT 0,
        start_lon REAL NOT NULL DEFAULT 0,
        end_lat REAL NOT NULL DEFAULT 0,
        end_lon REAL NOT NULL DEFAULT 0,
        route_mode TEXT DEFAULT 'direction',
        waypoints TEXT DEFAULT '[]',
        min_speed INTEGER DEFAULT 20,
        avg_speed INTEGER DEFAULT 50,
        max_speed INTEGER DEFAULT 80,
        ferry_speed INTEGER DEFAULT 25,
        trip_type TEXT DEFAULT 'single',
        rita_depart TEXT DEFAULT '',
        rita_arrive TEXT DEFAULT '',
        ritb_depart TEXT DEFAULT '',
        ritb_arrive TEXT DEFAULT '',
        nonstop_layover_min INTEGER DEFAULT 60,
        nonstop_layover_max INTEGER DEFAULT 60,
        start_place_id INTEGER,
        start_subplace_id INTEGER,
        end_place_id INTEGER,
        end_subplace_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Sim Devices — device identifier (terpisah dari konfigurasi trip)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sim_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE NOT NULL,
        name TEXT DEFAULT '',
        type TEXT DEFAULT 'car',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Services — menghubungkan Server + Trip + Device menjadi satu simulasi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        server_id INTEGER REFERENCES servers(id),
        trip_id INTEGER REFERENCES trips(id),
        sim_device_id INTEGER REFERENCES sim_devices(id),
        interval INTEGER DEFAULT 30,
        status TEXT DEFAULT 'stopped',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create places_subplaces table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS places_subplaces (
        place_id INTEGER NOT NULL,
        place_name TEXT NOT NULL,
        subplace_id INTEGER NOT NULL,
        subplace_name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        PRIMARY KEY (place_id, subplace_id)
    )
    """)
    
    # Import placesubplace JSON if table is empty
    cursor.execute("SELECT COUNT(*) FROM places_subplaces")
    if cursor.fetchone()[0] == 0:
        json_path = "placesubplace29june2026.json"
        if os.path.exists(json_path):
            print("Importing placesubplace29june2026.json into database...")
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                for item in data:
                    cursor.execute("""
                    INSERT OR REPLACE INTO places_subplaces (place_id, place_name, subplace_id, subplace_name, latitude, longitude)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        item["place_id"],
                        item["place_name"],
                        item["SubPlace_ID"],
                        item["subplace_name"],
                        item["Latitude"],
                        item["Longitude"]
                    ))
                print(f"Successfully imported {len(data)} places/subplaces.")
            except Exception as e:
                print(f"Error importing places/subplaces: {e}")

    # Upgrade devices table schema to support Route linking
    for col, col_type in [("route_type", "TEXT DEFAULT 'manual'"), 
                          ("start_place_id", "INTEGER"), 
                          ("start_subplace_id", "INTEGER"), 
                          ("end_place_id", "INTEGER"), 
                          ("end_subplace_id", "INTEGER")]:
        try:
            cursor.execute(f"ALTER TABLE devices ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
        
    conn.commit()
    
    # Auto-migration from config.json if exists
    if os.path.exists(CONFIG_PATH):
        print("Migrating config.json configurations to SQLite database...")
        try:
            with open(CONFIG_PATH, "r") as f:
                config_data = json.load(f)
            
            # Migrate settings
            host = config_data.get("traccar", {}).get("host", "tracking.misbahulihsan.com")
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("traccar_host", host))
            
            # Migrate devices
            for dev in config_data.get("devices", []):
                cursor.execute("""
                INSERT OR REPLACE INTO devices (
                    id, type, start_lat, start_lon, end_lat, end_lon, 
                    min_speed, avg_speed, max_speed, interval, start_time, trip_type, return_time,
                    nonstop_layover_min, nonstop_layover_max
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dev["id"],
                    dev.get("type", "car"),
                    dev["start"]["lat"],
                    dev["start"]["lon"],
                    dev["end"]["lat"],
                    dev["end"]["lon"],
                    dev.get("min_speed", 20),
                    dev.get("avg_speed", 50),
                    dev.get("max_speed", 80),
                    dev.get("interval", 30),
                    dev.get("start_time", ""),
                    dev.get("trip_type", "single"),
                    dev.get("return_time", ""),
                    dev.get("nonstop_layover_min", 60),
                    dev.get("nonstop_layover_max", 60)
                ))
            
            conn.commit()
            conn.close()
            
            # Backup config.json
            bak_path = CONFIG_PATH + ".bak"
            os.rename(CONFIG_PATH, bak_path)
            print(f"Migration completed. Backup saved as {bak_path}")
        except Exception as e:
            print(f"Error during SQLite migration: {e}")
            conn.close()
    else:
        # Default setting if new install
        cursor.execute("SELECT 1 FROM settings WHERE key = ?", ("traccar_host",))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("traccar_host", "tracking.misbahulihsan.com"))
            conn.commit()
        conn.close()

    # Seed default admin user if no users exist
    conn2 = get_db()
    cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) FROM users")
    if cur2.fetchone()[0] == 0:
        default_hash = generate_password_hash("ihsan456")
        cur2.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", default_hash, "admin")
        )
        cur2.commit() if hasattr(cur2, 'commit') else None
        conn2.commit()
        print("[DB] Default admin user created. Username: admin | Password: ihsan456")
        print("[DB] Segera ganti password default via /api/users/change-password !")

    # Seed default server jika belum ada
    cur2.execute("SELECT COUNT(*) FROM servers")
    if cur2.fetchone()[0] == 0:
        cur2.execute(
            "INSERT INTO servers (name, host, port, protocol) VALUES (?, ?, ?, ?)",
            ("Dummy / Testing", "dummy.misbahulihsan.com", 443, "https")
        )
        conn2.commit()
        print("[DB] Default server seeded: dummy.misbahulihsan.com")

    # Seed default sim_devices jika belum ada
    cur2.execute("SELECT COUNT(*) FROM sim_devices")
    if cur2.fetchone()[0] == 0:
        default_devices = [
            ("BUS001", "K 1256 AT", "bus"),
            ("BUS002", "K 2342 ST", "bus"),
            ("mtr001", "B 1267 OK", "motorcycle"),
            ("mtr002", "L 2389 ST", "motorcycle"),
            ("car001", "K 1987 UR", "car"),
            ("car003", "P 2691 KD", "car"),
            ("BUS004", "BG 4523 GN", "bus")
        ]
        cur2.executemany(
            "INSERT INTO sim_devices (device_id, name, type) VALUES (?, ?, ?)",
            default_devices
        )
        conn2.commit()
        print(f"[DB] {len(default_devices)} default sim_devices seeded.")

    # Seed default trips jika belum ada (termasuk Semarang_Surabaya & Surabaya_Semarang)
    cur2.execute("SELECT COUNT(*) FROM trips")
    if cur2.fetchone()[0] == 0:
        default_trips = [
            {
                "name": "Semarang_Surabaya",
                "start_lat": -6.989373644295812, "start_lon": 110.42359556436682,
                "end_lat": -7.34840536472191, "end_lon": 112.72666089492228,
                "min_speed": 20, "avg_speed": 55, "max_speed": 120, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Surabaya_Semarang",
                "start_lat": -7.34840536472191, "start_lon": 112.72666089492228,
                "end_lat": -6.989373644295812, "end_lon": 110.42359556436682,
                "min_speed": 20, "avg_speed": 55, "max_speed": 120, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Yogyakarta_Bekasi",
                "start_lat": -7.813745, "start_lon": 110.362344,
                "end_lat": -6.247396, "end_lon": 106.997051,
                "min_speed": 20, "avg_speed": 65, "max_speed": 90, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Bekasi_Yogyakarta",
                "start_lat": -6.247396, "start_lon": 106.997051,
                "end_lat": -7.813745, "end_lon": 110.362344,
                "min_speed": 20, "avg_speed": 65, "max_speed": 90, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Kudus_Yogyakarta",
                "start_lat": -6.763278, "start_lon": 110.831666,
                "end_lat": -7.814668, "end_lon": 110.368623,
                "min_speed": 20, "avg_speed": 55, "max_speed": 120, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Yogyakarta_Kudus",
                "start_lat": -7.814668, "start_lon": 110.368623,
                "end_lat": -6.763278, "end_lon": 110.831666,
                "min_speed": 20, "avg_speed": 55, "max_speed": 120, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Palembang_Surabaya",
                "start_lat": -2.995822, "start_lon": 104.776611,
                "end_lat": -7.24875, "end_lon": 112.739639,
                "min_speed": 20, "avg_speed": 65, "max_speed": 120, "ferry_speed": 25,
                "trip_type": "nonstop"
            },
            {
                "name": "Surabaya_Palembang",
                "start_lat": -7.24875, "start_lon": 112.739639,
                "end_lat": -2.995822, "end_lon": 104.776611,
                "min_speed": 20, "avg_speed": 65, "max_speed": 120, "ferry_speed": 25,
                "trip_type": "nonstop"
            }
        ]
        for dt in default_trips:
            cur2.execute("""
            INSERT INTO trips (
                name, start_lat, start_lon, end_lat, end_lon,
                route_mode, waypoints, min_speed, avg_speed, max_speed, ferry_speed, trip_type
            ) VALUES (?, ?, ?, ?, ?, 'direction', '[]', ?, ?, ?, ?, ?)
            """, (
                dt["name"], dt["start_lat"], dt["start_lon"], dt["end_lat"], dt["end_lon"],
                dt["min_speed"], dt["avg_speed"], dt["max_speed"], dt["ferry_speed"], dt["trip_type"]
            ))
        conn2.commit()
        print(f"[DB] {len(default_trips)} default trips seeded.")

    cur2.close()
    conn2.close()


def get_setting(key, default_val=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["value"]
    return default_val

def set_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_devices():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices")
    rows = cursor.fetchall()
    conn.close()
    
    devices = []
    for r in rows:
        try:
            layover_min = r["nonstop_layover_min"]
            layover_max = r["nonstop_layover_max"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            layover_min = 60
            layover_max = 60
            
        try:
            rita_depart = r["rita_depart"]
            rita_arrive = r["rita_arrive"]
            ritb_depart = r["ritb_depart"]
            ritb_arrive = r["ritb_arrive"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            rita_depart = ""
            rita_arrive = ""
            ritb_depart = ""
            ritb_arrive = ""
            
        try:
            name = r["name"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            name = ""
            
        try:
            waypoints_str = r["waypoints"]
            waypoints = json.loads(waypoints_str) if waypoints_str else []
        except (IndexError, KeyError, sqlite3.OperationalError, Exception):
            waypoints = []
            
        try:
            route_mode = r["route_mode"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            route_mode = "direction"
            
        try:
            rit_label = r["rit_label"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            rit_label = "RIT-A"
            
        try:
            ferry_speed = r["ferry_speed"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            ferry_speed = 25

        # WhatsApp and route selection mappings
        route_type = "manual"
        start_place_id = None
        start_subplace_id = None
        end_place_id = None
        end_subplace_id = None
        try:
            route_type = r["route_type"] or "manual"
            start_place_id = r["start_place_id"]
            start_subplace_id = r["start_subplace_id"]
            end_place_id = r["end_place_id"]
            end_subplace_id = r["end_subplace_id"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            pass
            
        devices.append({
            "id": r["id"],
            "name": name or "",
            "type": r["type"],
            "start": {"lat": r["start_lat"], "lon": r["start_lon"]},
            "end": {"lat": r["end_lat"], "lon": r["end_lon"]},
            "min_speed": r["min_speed"],
            "avg_speed": r["avg_speed"],
            "max_speed": r["max_speed"],
            "ferry_speed": ferry_speed if ferry_speed is not None else 25,
            "interval": r["interval"],
            "start_time": r["start_time"],
            "trip_type": r["trip_type"],
            "return_time": r["return_time"],
            "nonstop_layover_min": layover_min if layover_min is not None else 60,
            "nonstop_layover_max": layover_max if layover_max is not None else 60,
            "rita_depart": rita_depart or "",
            "rita_arrive": rita_arrive or "",
            "ritb_depart": ritb_depart or "",
            "ritb_arrive": ritb_arrive or "",
            "waypoints": waypoints,
            "route_mode": route_mode or "direction",
            "rit_label": rit_label or "RIT-A",
            "route_type": route_type,
            "start_place_id": start_place_id,
            "start_subplace_id": start_subplace_id,
            "end_place_id": end_place_id,
            "end_subplace_id": end_subplace_id
        })
    return devices

def get_device(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
    r = cursor.fetchone()
    conn.close()
    
    if r:
        try:
            layover_min = r["nonstop_layover_min"]
            layover_max = r["nonstop_layover_max"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            layover_min = 60
            layover_max = 60
            
        try:
            rita_depart = r["rita_depart"]
            rita_arrive = r["rita_arrive"]
            ritb_depart = r["ritb_depart"]
            ritb_arrive = r["ritb_arrive"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            rita_depart = ""
            rita_arrive = ""
            ritb_depart = ""
            ritb_arrive = ""
            
        try:
            name = r["name"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            name = ""
            
        try:
            waypoints_str = r["waypoints"]
            waypoints = json.loads(waypoints_str) if waypoints_str else []
        except (IndexError, KeyError, sqlite3.OperationalError, Exception):
            waypoints = []
            
        try:
            route_mode = r["route_mode"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            route_mode = "direction"
            
        try:
            rit_label = r["rit_label"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            rit_label = "RIT-A"
            
        try:
            ferry_speed = r["ferry_speed"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            ferry_speed = 25

        # WhatsApp and route selection mappings
        route_type = "manual"
        start_place_id = None
        start_subplace_id = None
        end_place_id = None
        end_subplace_id = None
        try:
            route_type = r["route_type"] or "manual"
            start_place_id = r["start_place_id"]
            start_subplace_id = r["start_subplace_id"]
            end_place_id = r["end_place_id"]
            end_subplace_id = r["end_subplace_id"]
        except (IndexError, KeyError, sqlite3.OperationalError):
            pass
            
        return {
            "id": r["id"],
            "name": name or "",
            "type": r["type"],
            "start": {"lat": r["start_lat"], "lon": r["start_lon"]},
            "end": {"lat": r["end_lat"], "lon": r["end_lon"]},
            "min_speed": r["min_speed"],
            "avg_speed": r["avg_speed"],
            "max_speed": r["max_speed"],
            "ferry_speed": ferry_speed if ferry_speed is not None else 25,
            "interval": r["interval"],
            "start_time": r["start_time"],
            "trip_type": r["trip_type"],
            "return_time": r["return_time"],
            "nonstop_layover_min": layover_min if layover_min is not None else 60,
            "nonstop_layover_max": layover_max if layover_max is not None else 60,
            "rita_depart": rita_depart or "",
            "rita_arrive": rita_arrive or "",
            "ritb_depart": ritb_depart or "",
            "ritb_arrive": ritb_arrive or "",
            "waypoints": waypoints,
            "route_mode": route_mode or "direction",
            "rit_label": rit_label or "RIT-A",
            "route_type": route_type,
            "start_place_id": start_place_id,
            "start_subplace_id": start_subplace_id,
            "end_place_id": end_place_id,
            "end_subplace_id": end_subplace_id
        }
    return None

def add_device(dev):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO devices (
        id, name, type, start_lat, start_lon, end_lat, end_lon, 
        min_speed, avg_speed, max_speed, ferry_speed, interval, start_time, trip_type, return_time,
        nonstop_layover_min, nonstop_layover_max, rita_depart, rita_arrive, ritb_depart, ritb_arrive, waypoints, route_mode, rit_label,
        route_type, start_place_id, start_subplace_id, end_place_id, end_subplace_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dev["id"],
        dev.get("name", ""),
        dev["type"],
        dev["start"]["lat"],
        dev["start"]["lon"],
        dev["end"]["lat"],
        dev["end"]["lon"],
        dev["min_speed"],
        dev["avg_speed"],
        dev["max_speed"],
        dev.get("ferry_speed", 25),
        dev["interval"],
        dev.get("start_time", ""),
        dev["trip_type"],
        dev.get("return_time", ""),
        dev.get("nonstop_layover_min", 60),
        dev.get("nonstop_layover_max", 60),
        dev.get("rita_depart", ""),
        dev.get("rita_arrive", ""),
        dev.get("ritb_depart", ""),
        dev.get("ritb_arrive", ""),
        json.dumps(dev.get("waypoints", [])),
        dev.get("route_mode", "direction"),
        dev.get("rit_label", "RIT-A"),
        dev.get("route_type", "manual"),
        dev.get("start_place_id"),
        dev.get("start_subplace_id"),
        dev.get("end_place_id"),
        dev.get("end_subplace_id")
    ))
    conn.commit()
    conn.close()

def delete_device(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()

def log_rit_depart(device_id, rit_type, date, scheduled_depart, actual_depart):
    conn = get_db()
    cursor = conn.cursor()
    # Check if there is already an active RUNNING trip today for this device and RIT label
    cursor.execute("""
        SELECT id FROM rit_runs 
        WHERE device_id = ? AND rit_type = ? AND date = ? AND status = 'RUNNING'
    """, (device_id, rit_type, date))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
        UPDATE rit_runs SET actual_depart = ? WHERE id = ?
        """, (actual_depart, row["id"]))
    else:
        cursor.execute("""
        INSERT INTO rit_runs (device_id, rit_type, date, scheduled_depart, actual_depart, status)
        VALUES (?, ?, ?, ?, ?, 'RUNNING')
        """, (device_id, rit_type, date, scheduled_depart, actual_depart))
    conn.commit()
    conn.close()

def log_rit_arrive(device_id, rit_type, date, scheduled_arrive, actual_arrive):
    conn = get_db()
    cursor = conn.cursor()
    # Find the most recent RUNNING run for this device and RIT type to mark it completed
    cursor.execute("""
        SELECT id FROM rit_runs 
        WHERE device_id = ? AND rit_type = ? AND status = 'RUNNING'
        ORDER BY id DESC LIMIT 1
    """, (device_id, rit_type))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
        UPDATE rit_runs SET actual_arrive = ?, status = 'COMPLETED' WHERE id = ?
        """, (actual_arrive, row["id"]))
    else:
        # Fallback to update any run from today or insert new completed run
        cursor.execute("""
            SELECT id FROM rit_runs 
            WHERE device_id = ? AND rit_type = ? AND date = ?
            ORDER BY id DESC LIMIT 1
        """, (device_id, rit_type, date))
        row = cursor.fetchone()
        if row:
            cursor.execute("""
            UPDATE rit_runs SET actual_arrive = ?, status = 'COMPLETED' WHERE id = ?
            """, (actual_arrive, row["id"]))
        else:
            cursor.execute("""
            INSERT INTO rit_runs (device_id, rit_type, date, scheduled_arrive, actual_arrive, status)
            VALUES (?, ?, ?, ?, ?, 'COMPLETED')
            """, (device_id, rit_type, date, scheduled_arrive, actual_arrive))
    conn.commit()
    conn.close()

def get_rit_runs():
    import datetime
    conn = get_db()
    cursor = conn.cursor()
    
    # Automatically clean up RIT runs older than 4 days
    threshold = (datetime.date.today() - datetime.timedelta(days=4)).strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM rit_runs WHERE date < ?", (threshold,))
    conn.commit()
    
    cursor.execute("SELECT * FROM rit_runs ORDER BY id DESC LIMIT 200")
    rows = cursor.fetchall()
    conn.close()
    
    runs = []
    for r in rows:
        runs.append({
            "id": r["id"],
            "device_id": r["device_id"],
            "rit_type": r["rit_type"],
            "date": r["date"],
            "scheduled_depart": r["scheduled_depart"],
            "actual_depart": r["actual_depart"],
            "scheduled_arrive": r["scheduled_arrive"],
            "actual_arrive": r["actual_arrive"],
            "status": r["status"]
        })
    return runs

# Initialize tables
init_db()

def get_places():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT place_id, place_name FROM places_subplaces ORDER BY place_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"place_id": r["place_id"], "place_name": r["place_name"]} for r in rows]

def get_subplaces(place_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT subplace_id, subplace_name, latitude, longitude FROM places_subplaces WHERE place_id = ? ORDER BY subplace_name ASC", (place_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{
        "subplace_id": r["subplace_id"],
        "subplace_name": r["subplace_name"],
        "latitude": r["latitude"],
        "longitude": r["longitude"]
    } for r in rows]

def get_subplace(place_id, subplace_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM places_subplaces WHERE place_id = ? AND subplace_id = ?", (place_id, subplace_id))
    r = cursor.fetchone()
    conn.close()
    if r:
        return {
            "place_id": r["place_id"],
            "place_name": r["place_name"],
            "subplace_id": r["subplace_id"],
            "subplace_name": r["subplace_name"],
            "latitude": r["latitude"],
            "longitude": r["longitude"]
        }
    return None

# ── User Management (Database Login) ─────────────────────────────────────────

def verify_user(username: str, password: str):
    """
    Verifikasi username dan password.
    Mengembalikan dict user jika valid, None jika gagal.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "created_at": row["created_at"],
            "last_login": row["last_login"]
        }
    return None

def get_user(username: str):
    """Ambil data user berdasarkan username (tanpa password hash)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at, last_login FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_all_users():
    """Ambil semua user (tanpa password hash)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at, last_login FROM users ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_user(username: str, password: str, role: str = "admin"):
    """
    Buat user baru dengan password yang di-hash.
    Kembalikan True jika berhasil, False jika username sudah ada.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        hashed = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hashed, role)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # username duplikat
    finally:
        conn.close()

def change_password(username: str, new_password: str):
    """Ganti password user. Kembalikan True jika berhasil."""
    conn = get_db()
    cursor = conn.cursor()
    hashed = generate_password_hash(new_password)
    cursor.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hashed, username)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def update_last_login(username: str):
    """Update waktu login terakhir user."""
    import datetime
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE users SET last_login = ? WHERE username = ?",
        (now_str, username)
    )
    conn.commit()
    conn.close()

def delete_user(username: str):
    """
    Hapus user. Tidak boleh hapus user terakhir (minimal harus ada 1 user).
    Kembalikan True jika berhasil, False jika gagal/ditolak.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count <= 1:
        conn.close()
        return False  # Tidak boleh hapus user terakhir
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ── Servers CRUD ──────────────────────────────────────────────────────────────

def get_servers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM servers ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_server(server_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
    r = cursor.fetchone()
    conn.close()
    return dict(r) if r else None

def create_server(name, host, port=443, protocol='https'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO servers (name, host, port, protocol) VALUES (?, ?, ?, ?)",
        (name, host, int(port), protocol)
    )
    server_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return server_id

def update_server(server_id, name, host, port, protocol):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE servers SET name=?, host=?, port=?, protocol=? WHERE id=?",
        (name, host, int(port), protocol, server_id)
    )
    conn.commit()
    conn.close()

def delete_server(server_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM servers WHERE id=?", (server_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ── Trips CRUD ────────────────────────────────────────────────────────────────

def get_trips():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trips ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d['waypoints'] = json.loads(d.get('waypoints') or '[]')
        except Exception:
            d['waypoints'] = []
        result.append(d)
    return result

def get_trip(trip_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
    r = cursor.fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    try:
        d['waypoints'] = json.loads(d.get('waypoints') or '[]')
    except Exception:
        d['waypoints'] = []
    return d

def create_trip(data: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO trips (
        name, start_lat, start_lon, end_lat, end_lon,
        route_mode, waypoints, min_speed, avg_speed, max_speed, ferry_speed,
        trip_type, rita_depart, rita_arrive, ritb_depart, ritb_arrive,
        nonstop_layover_min, nonstop_layover_max,
        start_place_id, start_subplace_id, end_place_id, end_subplace_id
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data['name'],
        data.get('start_lat', 0), data.get('start_lon', 0),
        data.get('end_lat', 0), data.get('end_lon', 0),
        data.get('route_mode', 'direction'),
        json.dumps(data.get('waypoints', [])),
        data.get('min_speed', 20), data.get('avg_speed', 50), data.get('max_speed', 80),
        data.get('ferry_speed', 25),
        data.get('trip_type', 'single'),
        data.get('rita_depart', ''), data.get('rita_arrive', ''),
        data.get('ritb_depart', ''), data.get('ritb_arrive', ''),
        data.get('nonstop_layover_min', 60), data.get('nonstop_layover_max', 60),
        data.get('start_place_id'), data.get('start_subplace_id'),
        data.get('end_place_id'), data.get('end_subplace_id'),
    ))
    trip_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trip_id

def update_trip(trip_id, data: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE trips SET
        name=?, start_lat=?, start_lon=?, end_lat=?, end_lon=?,
        route_mode=?, waypoints=?, min_speed=?, avg_speed=?, max_speed=?, ferry_speed=?,
        trip_type=?, rita_depart=?, rita_arrive=?, ritb_depart=?, ritb_arrive=?,
        nonstop_layover_min=?, nonstop_layover_max=?,
        start_place_id=?, start_subplace_id=?, end_place_id=?, end_subplace_id=?
    WHERE id=?
    """, (
        data['name'],
        data.get('start_lat', 0), data.get('start_lon', 0),
        data.get('end_lat', 0), data.get('end_lon', 0),
        data.get('route_mode', 'direction'),
        json.dumps(data.get('waypoints', [])),
        data.get('min_speed', 20), data.get('avg_speed', 50), data.get('max_speed', 80),
        data.get('ferry_speed', 25),
        data.get('trip_type', 'single'),
        data.get('rita_depart', ''), data.get('rita_arrive', ''),
        data.get('ritb_depart', ''), data.get('ritb_arrive', ''),
        data.get('nonstop_layover_min', 60), data.get('nonstop_layover_max', 60),
        data.get('start_place_id'), data.get('start_subplace_id'),
        data.get('end_place_id'), data.get('end_subplace_id'),
        trip_id
    ))
    conn.commit()
    conn.close()

def delete_trip(trip_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trips WHERE id=?", (trip_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ── Sim Devices CRUD ──────────────────────────────────────────────────────────

def get_sim_devices():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sim_devices ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sim_device(sim_device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sim_devices WHERE id = ?", (sim_device_id,))
    r = cursor.fetchone()
    conn.close()
    return dict(r) if r else None

def create_sim_device(device_id, name='', device_type='car'):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO sim_devices (device_id, name, type) VALUES (?, ?, ?)",
            (device_id, name, device_type)
        )
        new_id = cursor.lastrowid
        conn.commit()
        return new_id
    except sqlite3.IntegrityError:
        return None  # device_id duplikat
    finally:
        conn.close()

def update_sim_device(sim_device_id, device_id, name, device_type):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE sim_devices SET device_id=?, name=?, type=? WHERE id=?",
            (device_id, name, device_type, sim_device_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_sim_device(sim_device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sim_devices WHERE id=?", (sim_device_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ── Services CRUD ─────────────────────────────────────────────────────────────

def get_services():
    """Ambil semua services dengan join ke servers, trips, sim_devices."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            svc.id, svc.name, svc.interval, svc.status, svc.created_at,
            svc.server_id, svc.trip_id, svc.sim_device_id,
            srv.name AS server_name, srv.host AS server_host,
            srv.port AS server_port, srv.protocol AS server_protocol,
            t.name AS trip_name,
            sd.device_id, sd.name AS device_name, sd.type AS device_type
        FROM services svc
        LEFT JOIN servers srv ON svc.server_id = srv.id
        LEFT JOIN trips t ON svc.trip_id = t.id
        LEFT JOIN sim_devices sd ON svc.sim_device_id = sd.id
        ORDER BY svc.id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_service(service_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            svc.id, svc.name, svc.interval, svc.status, svc.created_at,
            svc.server_id, svc.trip_id, svc.sim_device_id,
            srv.name AS server_name, srv.host AS server_host,
            srv.port AS server_port, srv.protocol AS server_protocol,
            t.name AS trip_name,
            sd.device_id, sd.name AS device_name, sd.type AS device_type
        FROM services svc
        LEFT JOIN servers srv ON svc.server_id = srv.id
        LEFT JOIN trips t ON svc.trip_id = t.id
        LEFT JOIN sim_devices sd ON svc.sim_device_id = sd.id
        WHERE svc.id = ?
    """, (service_id,))
    r = cursor.fetchone()
    conn.close()
    return dict(r) if r else None

def create_service(name, server_id, trip_id, sim_device_id, interval=30):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO services (name, server_id, trip_id, sim_device_id, interval) VALUES (?,?,?,?,?)",
        (name, server_id, trip_id, sim_device_id, int(interval))
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def update_service(service_id, name, server_id, trip_id, sim_device_id, interval=30):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE services SET name=?, server_id=?, trip_id=?, sim_device_id=?, interval=? WHERE id=?",
        (name, server_id, trip_id, sim_device_id, int(interval), service_id)
    )
    conn.commit()
    conn.close()

def set_service_status(service_id, status):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE services SET status=? WHERE id=?", (status, service_id))
    conn.commit()
    conn.close()

def delete_service(service_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE id=?", (service_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0
