# ITrack Simulator 🚀

ITrack Simulator is a premium, full-stack Traccar Device Simulator and Control Panel. It allows you to simulate real-time vehicle movements (Cars, Motorcycles, Buses, etc.) along routes fetched from OSRM and transmit OsmAnd protocol telemetry directly to your Traccar server.

The simulator features a responsive, glassmorphic UI, map coordinate picking, automated offline catch-up, and persistent database storage.

---

## 🌟 Key Features

* **Glassmorphic Authentication Portal**: Secure dashboard access using standard credentials (`admin` / `ihsan456`) with a modern dark theme interface.
* **Interactive Leaflet Control Panel**: View real-time device telemetries (coordinates, bearing, speed, state, progress) on an interactive map.
* **Map Coordinate Picking**: Click directly on the Leaflet map to capture Start and End coordinates instead of entering them manually.
* **SQLite Backend Persistence**: Complete storage transition from JSON files to SQLite (`simulator.db`) for robust caching and concurrent reads/writes.
* **Advanced Trip Routing & Behaviors**:
  * **Single Trip**: Stop simulation upon destination arrival.
  * **Round Trip**: Drive from A to B, enter layover mode, and automatically perform the return leg at the scheduled return time.
  * **24-Hour Nonstop**: Continuously loop back and forth between A and B with randomized layover rests (e.g. 1 to 5 hours).
* **Automatic Route Generation**: Automatic calling of the OSRM Router API to calculate routes, caching them locally as JSON and GeoJSON.
* **Robust Offline Catch-Up Replay**: Replays missed telemetry positions if the simulator is restarted, preserving state continuity in Traccar.
* **Smart Coordinate Change Reset**: Automatically clears cached state files whenever coordinates are modified to start fresh.

---

## 🛠️ Tech Stack

* **Frontend**: HTML5, Vanilla CSS3 (Custom Glassmorphic styles, Dark Theme), Javascript (ES6), Leaflet.js (Map rendering)
* **Backend**: Python 3, Flask (REST APIs & session management), Flask-CORS
* **Database**: SQLite3 (schema initialization, settings persistence, device configurations)
* **Routing**: OSRM (Open Source Routing Machine) API

---

## 📁 Directory Structure

```text
├── simulator_server.py    # Main Flask server & simulation runners thread manager
├── database.py            # SQLite database schema, migrations, and query interfaces
├── map.html               # Main Leaflet Control Panel UI
├── login.html             # Glassmorphic Login UI
├── requirements.txt       # Python dependencies
├── simulator.db           # SQLite database file (generated automatically)
├── routes/                # Local cache directory for GeoJSON and JSON routes
└── state/                 # Local cache directory for device simulation state checkpoints
```

---

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/misbahulihsan/ITrackSimulator.git
cd ITrackSimulator
```

### 2. Setup Virtual Environment
Create and activate a Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate   # On Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Server
Launch the Flask simulator server:
```bash
python simulator_server.py
```
The server will boot on `http://localhost:8083`.

---

## 🧭 How to Use

1. Open your browser and navigate to `http://localhost:8083`.
2. Login with the credentials:
   * **Username**: `admin`
   * **Password**: `ihsan456`
3. Set your Traccar Server host (e.g. `tracking.misbahulihsan.com`) in the settings.
4. Click **+ Add Device** to register a new vehicle simulator:
   * Select a **Vehicle Type** (Car, Motorcycle, Bus).
   * Pick **Start/End Coordinates** directly by clicking the "Pick on Map" button and selecting locations on the map.
   * Configure **Trip Type** (Single, Round, or Nonstop) and set the relevant times.
5. Click **Save & Start**. The simulator will immediately cache the route coordinates and begin transmitting positions to your Traccar Server at the specified interval.
6. Monitor live progress, speed, bearing, and distance directly on the map.
7. Click **Log Out** at the bottom of the sidebar when you're done.

---

## 📝 License
This project is open-source. Feel free to modify and adapt it for your telemetry tracking requirements.
