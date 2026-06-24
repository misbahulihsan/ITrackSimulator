import sqlite3
import os
import json

DB_PATH = "simulator.db"
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
        nonstop_layover_max INTEGER DEFAULT 60
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
            
        devices.append({
            "id": r["id"],
            "type": r["type"],
            "start": {"lat": r["start_lat"], "lon": r["start_lon"]},
            "end": {"lat": r["end_lat"], "lon": r["end_lon"]},
            "min_speed": r["min_speed"],
            "avg_speed": r["avg_speed"],
            "max_speed": r["max_speed"],
            "interval": r["interval"],
            "start_time": r["start_time"],
            "trip_type": r["trip_type"],
            "return_time": r["return_time"],
            "nonstop_layover_min": layover_min if layover_min is not None else 60,
            "nonstop_layover_max": layover_max if layover_max is not None else 60
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
            
        return {
            "id": r["id"],
            "type": r["type"],
            "start": {"lat": r["start_lat"], "lon": r["start_lon"]},
            "end": {"lat": r["end_lat"], "lon": r["end_lon"]},
            "min_speed": r["min_speed"],
            "avg_speed": r["avg_speed"],
            "max_speed": r["max_speed"],
            "interval": r["interval"],
            "start_time": r["start_time"],
            "trip_type": r["trip_type"],
            "return_time": r["return_time"],
            "nonstop_layover_min": layover_min if layover_min is not None else 60,
            "nonstop_layover_max": layover_max if layover_max is not None else 60
        }
    return None

def add_device(dev):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO devices (
        id, type, start_lat, start_lon, end_lat, end_lon, 
        min_speed, avg_speed, max_speed, interval, start_time, trip_type, return_time,
        nonstop_layover_min, nonstop_layover_max
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dev["id"],
        dev["type"],
        dev["start"]["lat"],
        dev["start"]["lon"],
        dev["end"]["lat"],
        dev["end"]["lon"],
        dev["min_speed"],
        dev["avg_speed"],
        dev["max_speed"],
        dev["interval"],
        dev["start_time"],
        dev["trip_type"],
        dev["return_time"],
        dev.get("nonstop_layover_min", 60),
        dev.get("nonstop_layover_max", 60)
    ))
    conn.commit()
    conn.close()

def delete_device(device_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()

# Initialize tables
init_db()
