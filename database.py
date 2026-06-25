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
            "rit_label": rit_label or "RIT-A"
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
            "rit_label": rit_label or "RIT-A"
        }
    return None

def add_device(dev):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO devices (
        id, name, type, start_lat, start_lon, end_lat, end_lon, 
        min_speed, avg_speed, max_speed, ferry_speed, interval, start_time, trip_type, return_time,
        nonstop_layover_min, nonstop_layover_max, rita_depart, rita_arrive, ritb_depart, ritb_arrive, waypoints, route_mode, rit_label
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        dev.get("rit_label", "RIT-A")
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
