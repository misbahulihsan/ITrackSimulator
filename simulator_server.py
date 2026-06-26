import time
import random
import requests
import math
import os
import threading
import json
from flask import Flask, request, jsonify, send_from_directory, session, redirect
from flask_cors import CORS
from geopy.distance import great_circle
import database

app = Flask(__name__, static_folder='.')
app.secret_key = 'ihsan_traccar_secret_key_123'
CORS(app)

ROUTES_DIR = "routes"
STATE_DIR = "state"

os.makedirs(ROUTES_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

# Global memory to hold simulation states
# device_id -> telemetry dict
telemetry_data = {}
telemetry_lock = threading.Lock()

# Global memory for running simulation threads
# device_id -> { "shutdown_event": event, "thread": thread }
active_simulations = {}
simulations_lock = threading.Lock()

# Bridge database settings to the old load/save config APIs
def load_config():
    return {
        "traccar": {
            "host": database.get_setting("traccar_host", "tracking.misbahulihsan.com")
        },
        "devices": database.get_devices()
    }

def save_config(cfg):
    host = cfg.get("traccar", {}).get("host", "tracking.misbahulihsan.com")
    database.set_setting("traccar_host", host)
    
    # Sync devices
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices")
    for dev in cfg.get("devices", []):
        cursor.execute("""
        INSERT OR REPLACE INTO devices (
            id, name, type, start_lat, start_lon, end_lat, end_lon, 
            min_speed, avg_speed, max_speed, ferry_speed, interval, start_time, trip_type, return_time,
            nonstop_layover_min, nonstop_layover_max, rita_depart, rita_arrive, ritb_depart, ritb_arrive,
            waypoints, route_mode, rit_label
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

# Math Utilities
def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360

def angle_diff(a, b):
    return abs((b - a + 180) % 360 - 180)

def calculate_route_distances(route):
    segments_dist = []
    cumulative_dist = [0.0]
    for i in range(len(route) - 1):
        dist = great_circle(
            (route[i]["lat"], route[i]["lon"]),
            (route[i + 1]["lat"], route[i + 1]["lon"])
        ).meters
        segments_dist.append(dist)
        cumulative_dist.append(cumulative_dist[-1] + dist)
    return segments_dist, cumulative_dist

def interpolate_position(route, segments_dist, cumulative_dist, target_dist):
    import bisect
    idx = bisect.bisect_right(cumulative_dist, target_dist) - 1
    idx = max(0, min(idx, len(route) - 2))
    
    seg_len = segments_dist[idx]
    is_ferry = route[idx].get("is_ferry", False)
    if seg_len == 0:
        pt = {"lat": route[idx]["lat"], "lon": route[idx]["lon"], "is_ferry": is_ferry}
        bearing = calculate_bearing(
            route[idx]["lat"], route[idx]["lon"],
            route[idx + 1]["lat"], route[idx + 1]["lon"]
        )
    else:
        ratio = (target_dist - cumulative_dist[idx]) / seg_len
        ratio = max(0.0, min(1.0, ratio))
        lat = route[idx]["lat"] + (route[idx + 1]["lat"] - route[idx]["lat"]) * ratio
        lon = route[idx]["lon"] + (route[idx + 1]["lon"] - route[idx]["lon"]) * ratio
        pt = {"lat": lat, "lon": lon, "is_ferry": is_ferry}
        bearing = calculate_bearing(
            route[idx]["lat"], route[idx]["lon"],
            route[idx + 1]["lat"], route[idx + 1]["lon"]
        )
    return pt, bearing, idx

def check_upcoming_corners(route, cumulative_dist, current_dist, current_bearing, look_ahead=120):
    import bisect
    start_idx = bisect.bisect_right(cumulative_dist, current_dist) - 1
    start_idx = max(0, min(start_idx, len(route) - 2))
    end_idx = bisect.bisect_right(cumulative_dist, current_dist + look_ahead)
    end_idx = max(start_idx + 1, min(end_idx, len(route) - 1))
    
    for i in range(start_idx, end_idx):
        seg_bearing = calculate_bearing(
            route[i]["lat"], route[i]["lon"],
            route[i + 1]["lat"], route[i + 1]["lon"]
        )
        if angle_diff(current_bearing, seg_bearing) > 30:
            return True
    return False

def get_route(device, traccar_host):
    device_id = device["id"]
    safe_name = device_id.lower().replace(" ", "_")
    json_path = os.path.join(ROUTES_DIR, f"{safe_name}.json")
    geojson_path = os.path.join(ROUTES_DIR, f"{safe_name}.geojson")
    
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
            
    waypoints = device.get("waypoints", [])
    route_mode = device.get("route_mode", "direction")
    
    if route_mode == "multiple" and len(waypoints) >= 2:
        coords_str = ";".join([f"{pt['lon']},{pt['lat']}" for pt in waypoints])
    else:
        start = device["start"]
        end = device["end"]
        coords_str = f"{start['lon']},{start['lat']};{end['lon']},{end['lat']}"
    
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{coords_str}"
        "?overview=full&geometries=geojson&steps=true"
    )
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        if "routes" not in data or not data["routes"]:
            raise Exception("No routes found in OSRM response")
            
        route_data = data["routes"][0]
        legs = route_data.get("legs", [])
        
        route = []
        for leg in legs:
            steps = leg.get("steps", [])
            for step in steps:
                mode = step.get("mode")
                is_ferry = (mode == "ferry")
                step_coords = step.get("geometry", {}).get("coordinates", [])
                
                for coord in step_coords:
                    pt = {"lat": coord[1], "lon": coord[0], "is_ferry": is_ferry}
                    if not route:
                        route.append(pt)
                    else:
                        last_pt = route[-1]
                        if last_pt["lat"] == pt["lat"] and last_pt["lon"] == pt["lon"]:
                            if is_ferry:
                                last_pt["is_ferry"] = True
                        else:
                            route.append(pt)
                            
        with open(json_path, "w") as f:
            json.dump(route, f, indent=2)
            
        # Segment coordinates to create FeatureCollection of LineStrings
        features = []
        current_segment = []
        current_is_ferry = None
        
        for pt in route:
            is_ferry = pt.get("is_ferry", False)
            coord = [pt["lon"], pt["lat"]]
            
            if current_is_ferry is None:
                current_is_ferry = is_ferry
                current_segment.append(coord)
            elif is_ferry == current_is_ferry:
                current_segment.append(coord)
            else:
                # Add overlapping boundary point
                current_segment.append(coord)
                features.append({
                    "type": "Feature",
                    "properties": {
                        "deviceId": device_id,
                        "isFerry": current_is_ferry
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": current_segment
                    }
                })
                current_segment = [coord]
                current_is_ferry = is_ferry
                
        if current_segment:
            features.append({
                "type": "Feature",
                "properties": {
                    "deviceId": device_id,
                    "isFerry": current_is_ferry
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": current_segment
                }
            })
            
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        with open(geojson_path, "w") as f:
            json.dump(geojson, f, indent=2)
            
        return route
    except Exception as e:
        print(f"[{device_id}] Routing failed: {e}. Falling back to straight-line.")
        if route_mode == "multiple" and len(waypoints) >= 2:
            fallback = [{"lat": wp["lat"], "lon": wp["lon"]} for wp in waypoints]
        else:
            fallback = [
                {"lat": start["lat"], "lon": start["lon"]},
                {"lat": end["lat"], "lon": end["lon"]}
            ]
        return fallback

# Scheduling Helpers
def is_scheduled_time_reached(start_time_str):
    if not start_time_str:
        return True
    try:
        now = time.localtime()
        sh, sm = map(int, start_time_str.split(':'))
        if now.tm_hour > sh:
            return True
        elif now.tm_hour == sh and now.tm_min >= sm:
            return True
        return False
    except Exception:
        return True

# Simulation Runner Thread Function
# Helper to check if a specific time is reached at a given tick timestamp
def is_scheduled_time_reached_at(time_str, tick_time):
    if not time_str:
        return True
    try:
        tick_local = time.localtime(tick_time)
        sh, sm = map(int, time_str.split(':'))
        if tick_local.tm_hour > sh:
            return True
        elif tick_local.tm_hour == sh and tick_local.tm_min >= sm:
            return True
        return False
    except Exception:
        return True

def get_ideal_speed(arrive_time_str, tick_time, remaining_distance, min_speed, max_speed):
    if not arrive_time_str:
        return None
    try:
        local_struct = time.localtime(tick_time)
        h, m = map(int, arrive_time_str.split(':'))
        target_struct = time.struct_time((
            local_struct.tm_year, local_struct.tm_mon, local_struct.tm_mday,
            h, m, 0,
            local_struct.tm_wday, local_struct.tm_yday, local_struct.tm_isdst
        ))
        arrive_ts = time.mktime(target_struct)
        if arrive_ts < tick_time:
            arrive_ts += 86400  # overnight crossover
        remaining_time = arrive_ts - tick_time
        if remaining_time <= 0:
            return max_speed
        ideal_speed_mps = remaining_distance / remaining_time
        ideal_speed_kmh = ideal_speed_mps * 3.6
        ideal_speed_kmh += random.uniform(-3.0, 3.0)  # minor random traffic variance
        return max(min_speed, min(max_speed, int(ideal_speed_kmh)))
    except Exception as e:
        print(f"Error calculating ideal speed: {e}")
        return None

def simulation_step(device, route, segments_dist, cumulative_dist, total_dist,
                    state_vars, tick_time, interval):
    # Unpack state
    state = state_vars["state"]
    distance_traveled = state_vars["distance_traveled"]
    current_speed = state_vars["current_speed"]
    state_timer = state_vars["state_timer"]
    is_reversed = state_vars["is_reversed"]
    arrival_time = state_vars["arrival_time"]
    last_start_date = state_vars["last_start_date"]
    layover_duration = state_vars.get("layover_duration", 0)
    
    device_id = device["id"]
    vehicle_type = device.get("type", "car")
    start_time_str = device.get("start_time", "")
    trip_type = device.get("trip_type", "single")
    rit_label = device.get("rit_label", "RIT-A")
    return_time_str = device.get("return_time", "")
    min_speed = device.get("min_speed", 20)
    avg_speed = device.get("avg_speed", 50)
    max_speed = device.get("max_speed", 80)
    
    # RIT variable mappings
    rita_depart_str = device.get("rita_depart", "")
    rita_arrive_str = device.get("rita_arrive", "")
    ritb_depart_str = device.get("ritb_depart", "")
    ritb_arrive_str = device.get("ritb_arrive", "")
    
    # Map trip parameters based on trip_type and rit_label
    # Support old trip types for backward compatibility, but unified trip_type + rit_label is used.
    normalized_trip_type = trip_type
    if trip_type == "rita":
        normalized_trip_type = "single"
        rit_label = "RIT-A"
    elif trip_type == "ritb":
        normalized_trip_type = "single"
        rit_label = "RIT-B"
    elif trip_type == "round":
        normalized_trip_type = "nonstop"
        rit_label = "RIT-A"
        
    if normalized_trip_type == "single":
        if rit_label == "RIT-B":
            start_time_str = ritb_depart_str
            arrive_time_str = ritb_arrive_str
            is_reversed = True
        else:
            start_time_str = rita_depart_str
            arrive_time_str = rita_arrive_str
            is_reversed = False
    elif normalized_trip_type == "nonstop":
        start_time_str = device.get("start_time", "")
        if not start_time_str:
            start_time_str = ritb_depart_str if rit_label == "RIT-B" else rita_depart_str
        if not is_reversed:
            arrive_time_str = rita_arrive_str
        else:
            arrive_time_str = ritb_arrive_str

    active_rit_label = "RIT-B" if (normalized_trip_type == "single" and rit_label == "RIT-B") or (normalized_trip_type == "nonstop" and is_reversed) else "RIT-A"
    sched_depart_str = ritb_depart_str if active_rit_label == "RIT-B" else rita_depart_str
    sched_arrive_str = ritb_arrive_str if active_rit_label == "RIT-B" else rita_arrive_str
            
    # 1. Scheduled State
    if state == "SCHEDULED":
        today_str = time.strftime("%Y-%m-%d", time.localtime(tick_time))
        check_start_time = start_time_str
        if normalized_trip_type == "nonstop" and not check_start_time:
            check_start_time = ""
            
        if not check_start_time or (is_scheduled_time_reached_at(check_start_time, tick_time) and last_start_date != today_str):
            state = "DRIVING"
            last_start_date = today_str if check_start_time else ""
            current_speed = 0.0
            print(f"[{device_id}] Scheduled start time {check_start_time} reached! Starting driving.")
            
            # Log RIT depart with date and time
            actual_depart_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(tick_time))
            database.log_rit_depart(device_id, active_rit_label, today_str, sched_depart_str, actual_depart_str)
        else:
            pt = route[0]
            bearing = calculate_bearing(route[0]["lat"], route[0]["lon"], route[1]["lat"], route[1]["lon"])
            state_vars.update({
                "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": 0, "bearing": bearing,
                "distance_traveled": 0.0, "is_reversed": is_reversed, "last_start_date": last_start_date,
                "layover_duration": layover_duration
            })
            return pt, 0, bearing, "SCHEDULED"

    # 2. Completed State
    if state == "COMPLETED":
        pt = route[-1]
        bearing = calculate_bearing(route[-2]["lat"], route[-2]["lon"], route[-1]["lat"], route[-1]["lon"])
        state_vars.update({
            "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": 0, "bearing": bearing,
            "distance_traveled": total_dist, "is_reversed": is_reversed
        })
        return pt, 0, bearing, "COMPLETED"

    # 3. Waiting Return State
    if state == "WAITING_RETURN":
        elapsed_since_arrival = tick_time - arrival_time
        
        if normalized_trip_type == "nonstop":
            if elapsed_since_arrival >= layover_duration:
                state = "DRIVING"
                is_reversed = not is_reversed
                distance_traveled = 0.0
                current_speed = 0.0
                print(f"[{device_id}] Nonstop layover completed. Reversing direction and starting leg.")
                
                # Log new leg departure
                new_active_label = "RIT-B" if is_reversed else "RIT-A"
                new_sched_depart = ritb_depart_str if new_active_label == "RIT-B" else rita_depart_str
                today_str = time.strftime("%Y-%m-%d", time.localtime(tick_time))
                actual_depart_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(tick_time))
                database.log_rit_depart(device_id, new_active_label, today_str, new_sched_depart, actual_depart_str)
            else:
                pt = route[-1]
                bearing = calculate_bearing(route[-2]["lat"], route[-2]["lon"], route[-1]["lat"], route[-1]["lon"])
                state_vars.update({
                    "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": 0, "bearing": bearing,
                    "distance_traveled": total_dist, "is_reversed": is_reversed
                })
                return pt, 0, bearing, "WAITING_RETURN"
        else:
            time_reached = is_scheduled_time_reached_at(return_time_str, tick_time)
            min_wait = 10 if trip_type != "round" else 0
            if time_reached and elapsed_since_arrival >= min_wait:
                state = "DRIVING"
                is_reversed = True
                distance_traveled = 0.0
                current_speed = 0.0
                print(f"[{device_id}] WAITING_RETURN finished. Starting return leg.")
                
                today_str = time.strftime("%Y-%m-%d", time.localtime(tick_time))
                actual_depart_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(tick_time))
                database.log_rit_depart(device_id, "RIT-B", today_str, ritb_depart_str, actual_depart_str)
            else:
                pt = route[-1]
                bearing = calculate_bearing(route[-2]["lat"], route[-2]["lon"], route[-1]["lat"], route[-1]["lon"])
                
                wait_desc = "WAITING_RETURN"
                state_vars.update({
                    "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": 0, "bearing": bearing,
                    "distance_traveled": total_dist, "is_reversed": is_reversed
                })
                return pt, 0, bearing, wait_desc

    # 4. Traffic Light Stop
    if state == "TRAFFIC_LIGHT":
        current_speed = 0.0
        state_timer -= interval
        pt, bearing, _ = interpolate_position(route, segments_dist, cumulative_dist, distance_traveled)
        if state_timer <= 0:
            state = "DRIVING"
        state_vars.update({
            "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": 0, "bearing": bearing,
            "state_timer": state_timer, "distance_traveled": distance_traveled, "is_reversed": is_reversed
        })
        return pt, 0, bearing, "TRAFFIC_LIGHT"

    # 5. Parked Stop
    if state == "PARKED":
        current_speed = 0.0
        state_timer -= interval
        pt, bearing, _ = interpolate_position(route, segments_dist, cumulative_dist, distance_traveled)
        if state_timer <= 0:
            state = "DRIVING"
        state_vars.update({
            "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": 0, "bearing": bearing,
            "state_timer": state_timer, "distance_traveled": distance_traveled, "is_reversed": is_reversed
        })
        return pt, 0, bearing, "PARKED"

    # 6. Driving Leg
    if state == "DRIVING":
        pt, bearing, idx = interpolate_position(route, segments_dist, cumulative_dist, distance_traveled)
        has_corner = check_upcoming_corners(route, cumulative_dist, distance_traveled, bearing, look_ahead=120)
        
        # Behavior setup
        speeding_chance = 0.10
        traffic_light_chance = 0.04
        parking_chance = 0.01
        accel_factor = 5.0
        corner_min, corner_max = 15, 25
        
        if vehicle_type == "motorcycle":
            speeding_chance = 0.15
            traffic_light_chance = 0.03
            parking_chance = 0.00
            accel_factor = 8.0
            corner_min, corner_max = 25, 35
        elif vehicle_type == "bus":
            speeding_chance = 0.02
            traffic_light_chance = 0.06
            parking_chance = 0.03
            accel_factor = 3.0
            corner_min, corner_max = 10, 18
            
        # Check if the current segment is a ferry segment
        is_on_ferry = pt.get("is_ferry", False)
        
        if is_on_ferry:
            ferry_speed = device.get("ferry_speed", 25)
            target_speed = ferry_speed
            status_desc = "ON FERRY"
            accel_factor = 2.0  # smooth acceleration for ferry
        else:
            if has_corner:
                target_speed = random.randint(corner_min, corner_max)
                status_desc = "CORNERING"
            else:
                ideal_speed = None
                if normalized_trip_type == "single" and arrive_time_str:
                    remaining_dist = total_dist - distance_traveled
                    ideal_speed = get_ideal_speed(arrive_time_str, tick_time, remaining_dist, min_speed, max_speed)
                    
                if ideal_speed is not None:
                    target_speed = ideal_speed
                    status_desc = "CRUISING"
                else:
                    roll = random.random()
                    if roll < speeding_chance:
                        target_speed = random.randint(max_speed - 5, max_speed + 5)
                        status_desc = "SPEEDING"
                    elif roll < speeding_chance + 0.15:
                        target_speed = random.randint(min_speed, max(min_speed, avg_speed - 10))
                        status_desc = "TRAFFIC"
                    else:
                        target_speed = random.randint(avg_speed - 5, avg_speed + 5)
                        status_desc = "CRUISING"
                
        # Physics acceleration
        max_change = accel_factor * interval
        diff = target_speed - current_speed
        current_speed += max(-max_change, min(max_change, diff))
        
        if is_on_ferry:
            current_speed = max(5.0, min(current_speed, target_speed + 5))
        else:
            current_speed = max(min_speed, min(current_speed, max_speed + 10))
        
        # Move distance
        distance_moved = (current_speed * 1000.0 / 3600.0) * interval
        distance_traveled += distance_moved
        
        # Check destination reached
        if distance_traveled >= total_dist:
            distance_traveled = total_dist
            current_speed = 0.0
            
            # Log RIT arrive
            if normalized_trip_type in ["single", "nonstop"]:
                today_str = time.strftime("%Y-%m-%d", time.localtime(tick_time))
                actual_arrive_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(tick_time))
                database.log_rit_arrive(device_id, active_rit_label, today_str, sched_arrive_str, actual_arrive_str)
                
                # Fetch actual departure from DB to include in notification
                actual_depart_val = ""
                try:
                    conn = database.get_db()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT actual_depart FROM rit_runs 
                        WHERE device_id = ? AND rit_type = ? AND date = ?
                        ORDER BY id DESC LIMIT 1
                    """, (device_id, active_rit_label, today_str))
                    row = cursor.fetchone()
                    if row:
                        actual_depart_val = row["actual_depart"]
                    conn.close()
                except Exception as e:
                    print(f"[WhatsApp] Error fetching departure time: {e}")
                
                send_whatsapp_notification(
                    device_id=device_id,
                    rit_label=active_rit_label,
                    status_label="COMPLETED",
                    date=today_str,
                    scheduled_depart=sched_depart_str,
                    actual_depart=actual_depart_val,
                    scheduled_arrive=sched_arrive_str,
                    actual_arrive=actual_arrive_str
                )
                
            if normalized_trip_type == "single":
                state = "COMPLETED"
                status_desc = "COMPLETED"
            elif normalized_trip_type == "nonstop":
                state = "WAITING_RETURN"
                status_desc = "WAITING_RETURN"
                arrival_time = tick_time
                lay_min = device.get("nonstop_layover_min", 60)
                lay_max = device.get("nonstop_layover_max", 60)
                lay_min_val = min(lay_min, lay_max)
                lay_max_val = max(lay_min, lay_max)
                chosen_minutes = random.randint(lay_min_val, lay_max_val)
                layover_duration = chosen_minutes * 60
                print(f"[{device_id}] Reached destination. Entering WAITING_RETURN nonstop. Layover: {chosen_minutes} minutes ({layover_duration}s).")
            else: # round trip (legacy compatibility)
                if not is_reversed:
                    state = "WAITING_RETURN"
                    status_desc = "WAITING_RETURN"
                    arrival_time = tick_time
                else:
                    state = "SCHEDULED"
                    status_desc = "SCHEDULED"
                    is_reversed = False
        else:
            # Re-interpolate at new position
            pt, bearing, idx = interpolate_position(route, segments_dist, cumulative_dist, distance_traveled)
            
            # Check random event (only if not on ferry)
            if not pt.get("is_ferry", False):
                event_roll = random.random()
                if event_roll < traffic_light_chance:
                    state = "TRAFFIC_LIGHT"
                    state_timer = random.randint(20, 60)
                elif event_roll < traffic_light_chance + parking_chance:
                    state = "PARKED"
                    state_timer = random.randint(60, 180)
                
        state_vars.update({
            "state": state, "lat": pt["lat"], "lon": pt["lon"], "speed": int(current_speed), "bearing": bearing,
            "distance_traveled": distance_traveled, "current_speed": current_speed, "state_timer": state_timer,
            "is_reversed": is_reversed, "arrival_time": arrival_time, "last_start_date": last_start_date,
            "layover_duration": layover_duration
        })
        return pt, int(current_speed), bearing, status_desc

# Simulation Runner Thread Function
def run_simulation(device, traccar_host, shutdown_event):
    device_id = device["id"]
    safe_name = device_id.lower().replace(" ", "_")
    state_file = os.path.join(STATE_DIR, f"{safe_name}_state.json")
    
    interval = device.get("interval", 30)
    start_time_str = device.get("start_time", "")
    
    # 1. Fetch/load route
    route = get_route(device, traccar_host)
    
    # Default variables in state_vars
    state_vars = {
        "state": "DRIVING",
        "distance_traveled": 0.0,
        "current_speed": 0.0,
        "state_timer": 0,
        "is_reversed": False,
        "arrival_time": 0.0,
        "last_start_date": ""
    }
    
    trip_type = device.get("trip_type", "single")
    rit_label = device.get("rit_label", "RIT-A")
    rita_depart_str = device.get("rita_depart", "")
    ritb_depart_str = device.get("ritb_depart", "")
    
    # Backward compatibility mapping
    normalized_trip_type = trip_type
    if trip_type == "rita":
        normalized_trip_type = "single"
        rit_label = "RIT-A"
    elif trip_type == "ritb":
        normalized_trip_type = "single"
        rit_label = "RIT-B"
    elif trip_type == "round":
        normalized_trip_type = "nonstop"
        rit_label = "RIT-A"

    start_time_str = ""
    if normalized_trip_type == "single":
        if rit_label == "RIT-B":
            start_time_str = device.get("ritb_depart", "")
        else:
            start_time_str = device.get("rita_depart", "")
    elif normalized_trip_type == "nonstop":
        start_time_str = device.get("start_time", "")
        if not start_time_str:
            start_time_str = device.get("ritb_depart", "") if rit_label == "RIT-B" else device.get("rita_depart", "")
        
    if start_time_str:
        state_vars["state"] = "SCHEDULED"
        
    # Load state from file
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as sf:
                state_data = json.load(sf)
                state_vars["distance_traveled"] = state_data.get("distance_traveled", 0.0)
                state_vars["current_speed"] = state_data.get("current_speed", 0.0)
                state_vars["state_timer"] = state_data.get("state_timer", 0)
                state_vars["is_reversed"] = state_data.get("is_reversed", False)
                state_vars["state"] = state_data.get("state", "DRIVING")
                state_vars["arrival_time"] = state_data.get("arrival_time", 0.0)
                state_vars["last_start_date"] = state_data.get("last_start_date", "")
        except Exception as e:
            print(f"[{device_id}] Error loading state: {e}. Starting fresh.")
    else:
        if (normalized_trip_type == "single" and rit_label == "RIT-B") or (normalized_trip_type == "nonstop" and rit_label == "RIT-B"):
            state_vars["is_reversed"] = True
            
    if state_vars["is_reversed"]:
        route.reverse()
        
    segments_dist, cumulative_dist = calculate_route_distances(route)
    total_dist = cumulative_dist[-1]
    
    # Catch-up logic using simulation_step
    now = time.time()
    last_updated = 0.0
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as sf:
                last_updated = json.load(sf).get("last_updated_time", 0.0)
        except Exception:
            pass
            
    if last_updated > 0 and now > last_updated:
        elapsed = now - last_updated
        num_ticks = int(elapsed / interval)
        
        if num_ticks > 0:
            max_buffer = 200
            if num_ticks > max_buffer:
                print(f"[{device_id}] Offline for {elapsed/60:.1f} minutes. Cap replay buffer to {max_buffer}.")
                last_updated = now - (max_buffer * interval)
                num_ticks = max_buffer
                
            print(f"[{device_id}] Offline buffer replay: processing {num_ticks} ticks...")
            for t in range(1, num_ticks + 1):
                if shutdown_event.is_set():
                    break
                tick_time = last_updated + t * interval
                prev_reversed = state_vars["is_reversed"]
                
                pt, speed, bearing, status_desc = simulation_step(
                    device, route, segments_dist, cumulative_dist, total_dist,
                    state_vars, tick_time, interval
                )
                
                if state_vars["is_reversed"] != prev_reversed:
                    route = get_route(device, traccar_host)
                    if state_vars["is_reversed"]:
                        route.reverse()
                    segments_dist, cumulative_dist = calculate_route_distances(route)
                    total_dist = cumulative_dist[-1]
                    
                # Send offline replay position
                if state_vars["state"] in ["DRIVING", "TRAFFIC_LIGHT", "CORNERING", "SPEEDING", "TRAFFIC", "WAITING_RETURN"]:
                    send_osmand_position(traccar_host, device_id, pt, speed, bearing,
                                         (state_vars["state"] != "WAITING_RETURN"),
                                         "OFFLINE_REPLAY", int(tick_time))
                    time.sleep(0.05)
                    
    while not shutdown_event.is_set():
        tick_start = time.time()
        prev_reversed = state_vars["is_reversed"]
        
        pt, speed, bearing, status_desc = simulation_step(
            device, route, segments_dist, cumulative_dist, total_dist,
            state_vars, tick_start, interval
        )
        
        if state_vars["is_reversed"] != prev_reversed:
            route = get_route(device, traccar_host)
            if state_vars["is_reversed"]:
                route.reverse()
            segments_dist, cumulative_dist = calculate_route_distances(route)
            total_dist = cumulative_dist[-1]
            
        ignition = state_vars["state"] not in ["PARKED", "SCHEDULED", "COMPLETED", "WAITING_RETURN"]
        send_osmand_position(traccar_host, device_id, pt, speed, bearing, ignition, status_desc)
        
        # Telemetry updates
        progress_val = 0
        if total_dist > 0:
            progress_val = int((state_vars["distance_traveled"] / total_dist) * 100)
            
        state_label = status_desc
        
        curr_start_time_str = ""
        if normalized_trip_type == "single":
            curr_start_time_str = ritb_depart_str if rit_label == "RIT-B" else rita_depart_str
        elif normalized_trip_type == "nonstop":
            curr_start_time_str = ritb_depart_str if state_vars["is_reversed"] else rita_depart_str
            if not curr_start_time_str:
                curr_start_time_str = device.get("start_time", "")
            
        if state_vars["state"] == "SCHEDULED":
            state_label = f"SCHEDULED ({curr_start_time_str})"
        elif state_vars["state"] == "WAITING_RETURN":
            elapsed_since_arrival = tick_start - state_vars["arrival_time"]
            lay_dur = state_vars.get("layover_duration", 0)
            if elapsed_since_arrival < lay_dur:
                left_sec = int(lay_dur - elapsed_since_arrival)
                state_label = f"LAYOVER ({left_sec // 60}m {left_sec % 60}s left)"
            else:
                state_label = "WAITING"
                
        with telemetry_lock:
            active_rit_label = "RIT-B" if (normalized_trip_type == "single" and rit_label == "RIT-B") or (normalized_trip_type == "nonstop" and state_vars["is_reversed"]) else "RIT-A"
            telemetry_data[device_id] = {
                "lat": pt["lat"], "lon": pt["lon"], "speed": speed, "bearing": bearing,
                "state": f"{state_label} ({active_rit_label})" if state_label in ["DRIVING", "CRUISING", "CORNERING", "SPEEDING", "TRAFFIC", "ON FERRY"] or state_label.startswith("LAYOVER") else state_label,
                "progress": progress_val,
                "distance_traveled": state_vars["distance_traveled"], "total_distance": total_dist,
                "is_reversed": state_vars["is_reversed"],
                "start": device["start"],
                "end": device["end"],
                "waypoints": device.get("waypoints", []),
                "route_mode": device.get("route_mode", "direction"),
                "rit_label": active_rit_label,
                "name": device.get("name", device_id)
            }
            
        save_state_file_extended(
            state_file,
            state_vars["distance_traveled"],
            state_vars["is_reversed"],
            state_vars["state"],
            state_vars["arrival_time"],
            state_vars["last_start_date"]
        )
        
        sleep_gracefully(interval, tick_start, shutdown_event)

def send_osmand_position(traccar_host, device_id, point, speed_kmh, bearing, ignition, status, timestamp=None):
    speed_knots = round(speed_kmh * 0.539957, 2)
    if timestamp is None:
        timestamp = int(time.time())
        
    url = f"https://{traccar_host}/"
    params = {
        "id": device_id,
        "lat": round(point["lat"], 6),
        "lon": round(point["lon"], 6),
        "timestamp": timestamp,
        "speed": speed_knots,
        "bearing": round(bearing, 1),
        "ignition": "true" if ignition else "false",
        "batt": 85,
        "status": status
    }
    
    try:
        r = requests.post(url, params=params, timeout=5)
        if status != "OFFLINE_REPLAY":
            print(f"[{device_id}] Sent position. Lat: {params['lat']:.5f}, Lon: {params['lon']:.5f}, Speed: {speed_kmh} km/h, State: {status}, Response: {r.status_code}")
    except Exception as e:
        print(f"[{device_id}] Fail to send: {e}")

def save_state_file_extended(path, dist, rev, state, arrival, last_start_date="", layover_duration=0):
    try:
        with open(path, "w") as sf:
            json.dump({
                "distance_traveled": dist,
                "last_updated_time": time.time(),
                "is_reversed": rev,
                "state": state,
                "arrival_time": arrival,
                "last_start_date": last_start_date,
                "layover_duration": layover_duration
            }, sf, indent=2)
    except Exception as e:
        pass

def sleep_gracefully(interval, tick_start, shutdown_event):
    elapsed = time.time() - tick_start
    sleep_time = max(0.1, interval - elapsed)
    steps = int(sleep_time / 0.5)
    for _ in range(steps):
        if shutdown_event.is_set():
            break
        time.sleep(0.5)
    remainder = sleep_time - (steps * 0.5)
    if remainder > 0 and not shutdown_event.is_set():
        time.sleep(remainder)

def send_whatsapp_notification(device_id, rit_label, status_label, date, scheduled_depart, actual_depart, scheduled_arrive, actual_arrive):
    enabled = database.get_setting("wa_notif_enabled", "0") == "1"
    if not enabled:
        return
    
    number = database.get_setting("wa_target_number", "+6285727255841").strip()
    api_url = database.get_setting("wa_api_url", "https://waha.misbahulihsan.com").strip()
    api_key = database.get_setting("wa_api_key", "Aku123").strip()
    
    if not number or not api_url:
        print("[WhatsApp] Number or API URL not configured.")
        return
        
    clean_number = "".join(filter(str.isdigit, number))
    if not clean_number:
        print("[WhatsApp] Invalid phone number.")
        return
        
    chat_id = f"{clean_number}@c.us"
    
    device_name = device_id
    dep_lat, dep_lon = None, None
    arr_lat, arr_lon = None, None
    
    try:
        devs = database.get_devices()
        dev = next((d for d in devs if d["id"] == device_id), None)
        if dev:
            if dev.get("name"):
                device_name = f"{dev['name']} ({device_id})"
            
            s_lat = dev.get("start", {}).get("lat")
            s_lon = dev.get("start", {}).get("lon")
            e_lat = dev.get("end", {}).get("lat")
            e_lon = dev.get("end", {}).get("lon")
            
            if rit_label == "RIT-B":
                dep_lat, dep_lon = e_lat, e_lon
                arr_lat, arr_lon = s_lat, s_lon
            else:
                dep_lat, dep_lon = s_lat, s_lon
                arr_lat, arr_lon = e_lat, e_lon
    except Exception as e:
        print(f"[WhatsApp] Error fetching device details/coordinates: {e}")
        
    dep_link_str = f"https://www.google.com/maps/search/?api=1&query={dep_lat},{dep_lon}" if dep_lat is not None else "-"
    arr_link_str = f"https://www.google.com/maps/search/?api=1&query={arr_lat},{arr_lon}" if arr_lat is not None else "-"
        
    message = (
        f"🔔 *ITrack Simulator - RIT Report* 🔔\n\n"
        f"*Device:* {device_name}\n"
        f"*RIT Label:* {rit_label}\n"
        f"*Date:* {date}\n"
        f"*Status:* {status_label} ✅\n\n"
        f"📍 *Departure Details:*\n"
        f"- Location: {dep_link_str}\n"
        f"- Scheduled: {scheduled_depart or '-'}\n"
        f"- Actual: {actual_depart or '-'}\n\n"
        f"🏁 *Arrival Details:*\n"
        f"- Location: {arr_link_str}\n"
        f"- Scheduled: {scheduled_arrive or '-'}\n"
        f"- Actual: {actual_arrive or '-'}"
    )
    
    url = f"{api_url.rstrip('/')}/api/sendText"
    payload = {
        "session": "default",
        "chatId": chat_id,
        "text": message
    }
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["X-Api-Key"] = api_key
        
    def make_request():
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            print(f"[WhatsApp] Notification sent to {chat_id}. Response: {r.status_code}")
        except Exception as e:
            print(f"[WhatsApp] Failed to send notification: {e}")
            
    t = threading.Thread(target=make_request)
    t.daemon = True
    t.start()

@app.before_request
def check_auth():
    # Allow login.html and api/login to bypass auth
    if request.path == '/login.html':
        if session.get("logged_in"):
            return redirect('/')
        return
    if request.path == '/api/login':
        return
        
    # All other paths require auth
    if not session.get("logged_in"):
        if request.path.startswith('/api/'):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect('/login.html')

@app.route('/login.html')
def login_page():
    return send_from_directory('.', 'login.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if username == "admin" and password == "ihsan456":
        session["logged_in"] = True
        return jsonify({"success": True})
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop("logged_in", None)
    return jsonify({"success": True})

# REST API Endpoints
@app.route('/')
def index():
    return send_from_directory('.', 'map.html')

@app.route('/map.html')
def map_html():
    return send_from_directory('.', 'map.html')

@app.route('/routes/<path:filename>')
def serve_routes(filename):
    return send_from_directory(ROUTES_DIR, filename)

@app.route('/api/devices', methods=['GET'])
def get_devices():
    cfg = load_config()
    devices = cfg.get("devices", [])
    
    # Enrich with running status
    enriched = []
    with simulations_lock:
        for dev in devices:
            dev_id = dev["id"]
            dev_copy = dev.copy()
            dev_copy["status"] = "Running" if dev_id in active_simulations else "Stopped"
            enriched.append(dev_copy)
            
    return jsonify({"traccar": cfg.get("traccar", {}), "devices": enriched})

@app.route('/api/devices', methods=['POST'])
def add_device():
    data = request.json
    if not data or "id" not in data:
        return jsonify({"error": "Missing device ID"}), 400
        
    cfg = load_config()
    devices = cfg.get("devices", [])
    
    # Check if exists, update it, otherwise add it
    idx = -1
    for i, dev in enumerate(devices):
        if dev["id"] == data["id"]:
            idx = i
            break
            
    new_device = {
        "id": data["id"],
        "name": data.get("name", ""),
        "start": data["start"],
        "end": data["end"],
        "min_speed": int(data.get("min_speed", 20)),
        "avg_speed": int(data.get("avg_speed", 50)),
        "max_speed": int(data.get("max_speed", 80)),
        "ferry_speed": int(data.get("ferry_speed", 25)),
        "type": data.get("type", "car"),
        "start_time": data.get("start_time", ""),
        "trip_type": data.get("trip_type", "single"),
        "return_time": data.get("return_time", ""),
        "nonstop_layover_min": int(data.get("nonstop_layover_min", 60)),
        "nonstop_layover_max": int(data.get("nonstop_layover_max", 60)),
        "interval": int(data.get("interval", 30)),
        "rita_depart": data.get("rita_depart", ""),
        "rita_arrive": data.get("rita_arrive", ""),
        "ritb_depart": data.get("ritb_depart", ""),
        "ritb_arrive": data.get("ritb_arrive", ""),
        "waypoints": data.get("waypoints", []),
        "route_mode": data.get("route_mode", "direction"),
        "rit_label": data.get("rit_label", "RIT-A")
    }
    
    if idx >= 0:
        # Check if coordinates changed
        old_device = devices[idx]
        coords_changed = (
            old_device.get("route_mode", "direction") != new_device["route_mode"] or
            old_device.get("waypoints", []) != new_device["waypoints"] or
            old_device["start"]["lat"] != new_device["start"]["lat"] or
            old_device["start"]["lon"] != new_device["start"]["lon"] or
            old_device["end"]["lat"] != new_device["end"]["lat"] or
            old_device["end"]["lon"] != new_device["end"]["lon"]
        )
        if coords_changed:
            safe_name = data["id"].lower().replace(" ", "_")
            files_to_delete = [
                os.path.join(STATE_DIR, f"{safe_name}_state.json"),
                os.path.join(ROUTES_DIR, f"{safe_name}.json"),
                os.path.join(ROUTES_DIR, f"{safe_name}.geojson")
            ]
            for p in files_to_delete:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        stop_simulation_thread(data["id"])
        devices[idx] = new_device
    else:
        devices.append(new_device)
        
    cfg["devices"] = devices
    save_config(cfg)
    
    # Start it by default only if global service is running
    if database.get_setting("service_status", "running") == "running":
        start_simulation_thread(new_device, cfg["traccar"]["host"])
    
    return jsonify({"success": True, "device": new_device})

@app.route('/api/devices/<device_id>', methods=['DELETE'])
def delete_device(device_id):
    cfg = load_config()
    devices = cfg.get("devices", [])
    
    new_list = [dev for dev in devices if dev["id"] != device_id]
    if len(new_list) == len(devices):
        return jsonify({"error": "Device not found"}), 404
        
    stop_simulation_thread(device_id)
    cfg["devices"] = new_list
    save_config(cfg)
    
    # Clean up telemetry and cached routes/states
    with telemetry_lock:
        if device_id in telemetry_data:
            del telemetry_data[device_id]
            
    safe_name = device_id.lower().replace(" ", "_")
    files_to_delete = [
        os.path.join(ROUTES_DIR, f"{safe_name}.json"),
        os.path.join(ROUTES_DIR, f"{safe_name}.geojson"),
        os.path.join(STATE_DIR, f"{safe_name}_state.json")
    ]
    for path in files_to_delete:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
                    
    return jsonify({"success": True})

@app.route('/api/devices/<device_id>/start', methods=['POST'])
def start_device(device_id):
    if database.get_setting("service_status", "running") == "stopped":
        return jsonify({"error": "Global service is stopped. Start it first."}), 400
        
    cfg = load_config()
    devices = cfg.get("devices", [])
    
    device = None
    for dev in devices:
        if dev["id"] == device_id:
            device = dev
            break
            
    if not device:
        return jsonify({"error": "Device not found"}), 404
        
    started = start_simulation_thread(device, cfg["traccar"]["host"])
    return jsonify({"success": started})

@app.route('/api/devices/<device_id>/stop', methods=['POST'])
def stop_device(device_id):
    stopped = stop_simulation_thread(device_id)
    return jsonify({"success": stopped})

@app.route('/api/status', methods=['GET'])
def get_status():
    with telemetry_lock:
        return jsonify(telemetry_data)

@app.route('/api/reports/rit', methods=['GET'])
def get_rit_report():
    runs = database.get_rit_runs()
    return jsonify(runs)

@app.route('/api/settings/whatsapp', methods=['GET'])
def get_whatsapp_settings():
    return jsonify({
        "enabled": database.get_setting("wa_notif_enabled", "0") == "1",
        "number": database.get_setting("wa_target_number", "+6285727255841"),
        "url": database.get_setting("wa_api_url", "https://waha.misbahulihsan.com"),
        "key": database.get_setting("wa_api_key", "Aku123")
    })

@app.route('/api/settings/whatsapp', methods=['POST'])
def save_whatsapp_settings():
    data = request.json or {}
    database.set_setting("wa_notif_enabled", "1" if data.get("enabled") else "0")
    database.set_setting("wa_target_number", data.get("number", "+6285727255841").strip())
    database.set_setting("wa_api_url", data.get("url", "https://waha.misbahulihsan.com").strip())
    database.set_setting("wa_api_key", data.get("key", "Aku123").strip())
    return jsonify({"success": True})

@app.route('/api/service/status', methods=['GET'])
def get_service_status():
    status = database.get_setting("service_status", "running")
    return jsonify({"status": status})

@app.route('/api/service/start', methods=['POST'])
def start_service():
    database.set_setting("service_status", "running")
    touch_all_states()
    start_all_simulations()
    return jsonify({"success": True})

@app.route('/api/service/stop', methods=['POST'])
def stop_service():
    database.set_setting("service_status", "stopped")
    stop_all_simulations()
    return jsonify({"success": True})

def touch_all_states():
    now = time.time()
    if os.path.exists(STATE_DIR):
        for filename in os.listdir(STATE_DIR):
            if filename.endswith("_state.json"):
                path = os.path.join(STATE_DIR, filename)
                try:
                    with open(path, "r") as sf:
                        state_data = json.load(sf)
                    state_data["last_updated_time"] = now
                    with open(path, "w") as sf:
                        json.dump(state_data, sf, indent=2)
                    print(f"Touched state file: {filename} to skip catchup.")
                except Exception as e:
                    print(f"Error touching state file {filename}: {e}")

# Helper thread managers
def start_simulation_thread(device, traccar_host):
    device_id = device["id"]
    with simulations_lock:
        if device_id in active_simulations:
            return True
            
        shutdown_event = threading.Event()
        t = threading.Thread(
            target=run_simulation,
            args=(device, traccar_host, shutdown_event),
            name=f"Sim-{device_id}"
        )
        t.daemon = True
        t.start()
        
        active_simulations[device_id] = {
            "shutdown_event": shutdown_event,
            "thread": t
        }
    return True

def stop_simulation_thread(device_id):
    with simulations_lock:
        if device_id not in active_simulations:
            return False
            
        sim = active_simulations[device_id]
        sim["shutdown_event"].set()
        sim["thread"].join(timeout=1.0)
        del active_simulations[device_id]
        
    with telemetry_lock:
        if device_id in telemetry_data:
            telemetry_data[device_id]["state"] = "PAUSED"
            telemetry_data[device_id]["speed"] = 0
            
    return True

def start_all_simulations():
    cfg = load_config()
    for dev in cfg.get("devices", []):
        start_simulation_thread(dev, cfg["traccar"]["host"])

def stop_all_simulations():
    with simulations_lock:
        keys = list(active_simulations.keys())
    for key in keys:
        stop_simulation_thread(key)

if __name__ == '__main__':
    status = database.get_setting("service_status", "running")
    if status == "running":
        print("Starting all simulations on startup...")
        start_all_simulations()
    else:
        print("Service is stopped. Not starting simulations on startup.")
        
    try:
        app.run(host='0.0.0.0', port=8083, debug=False, threaded=True)
    finally:
        print("Stopping all active simulations before exit...")
        stop_all_simulations()
