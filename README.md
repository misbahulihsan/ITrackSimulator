# ITrack Simulator 🚀

ITrack Simulator is a premium, full-stack Traccar Device Simulator and Control Panel. It allows you to simulate real-time vehicle movements (Cars, Motorcycles, Buses, etc.) along routes fetched from OSRM and transmit OsmAnd protocol telemetry directly to your Traccar server.

The simulator features a responsive, glassmorphic UI, map coordinate picking, automated offline catch-up, and persistent database storage.

---

## 🌟 Key Features & Functions

### 1. Interactive Control Panel & Dashboard
* **Glassmorphic Authentication Portal**: Secure dashboard access using standard credentials (`admin` / `ihsan456`) with a modern dark theme interface.
* **Interactive Leaflet Map**: View real-time device telemetries (coordinates, bearing, speed, state, progress) on an interactive map.
* **Map Layer Control**: Switch dynamically between **Light Theme** and **Dark Theme** map layers directly from the map control interface.
* **Collapsible Side Menu**: Clean sidebar UI that lists active device cards with responsive names, and allows adding/editing devices.
* **Global Service Controls**: Run or stop the entire simulation service with a single global switch.

### 2. Device CRUD & Custom Parameters
* **Quick Device Management**: Add, update, and delete simulated devices.
* **Map Coordinate Picker**: Click directly on the Leaflet map to capture Start and End coordinates instead of entering them manually.
* **Custom Vehicle Speed Ranges**: Configure minimum, average, and maximum speeds for realistic driving behaviors.
* **Custom Transmission Intervals**: Control the frequency of telemetry updates sent to the Traccar server (in seconds).

### 3. Advanced Trip Routing & Multi-Waypoint Paths
* **Single Route (Point A to B)**: Automated call to OSRM API to fetch the shortest driving path.
* **Multi-Waypoint Routing**: Add multiple intermediate checkpoints directly in the UI to create complex, customized travel paths.
* **Predefined Place & Subplace Routing (Selected Route)**: Choose routes using hierarchical Place and Subplace dropdown selectors (e.g. Jakarta, Bandung, Kediri). Supports adding multiple place checkpoints, drag-and-drop reordering, auto-pans the map on selection, and populates coordinates automatically from the SQLite database.
* **Local Caching System**: Caches route geometry as JSON and GeoJSON files in the `routes/` directory to speed up load times and minimize API queries.

### 4. Realistic Physics & Simulation Behaviors
* **Dynamic Physics & Acceleration**: Simulates smooth speed transitions based on vehicle weight and type.
* **Vehicle-Specific Profiles**: Different limits and behaviors for Cars, Motorcycles, and Buses.
* **Event Slowdowns**: Introduces random real-world events like speeding, traffic light stops, cornering deceleration, and heavy traffic delays.
* **Sea Route Ferry Speeds**: Automatically detects when a route crosses sea/ocean sections (e.g. Sunda Strait crossing) from OSRM step modes. It styles these segments as dashed lines on the Leaflet map and overrides vehicle speeds to the configured **Ferry Speed** (default 25 km/h) with an "ON FERRY" status.

### 5. RIT Scheduling & Runs Report
* **Flexible Trip Modes**:
  * **Single Trip**: Stop simulation upon destination arrival.
  * **24-Hour Nonstop**: Continuously loop back and forth between coordinates with randomized layover rests (e.g. 1 to 5 hours).
* **RIT Labels**: Supports tracking outbound leg (`RIT-A`) and return/inbound leg (`RIT-B`).
* **RIT Scheduled Times**: Setup scheduled departure and arrival times for RIT-A and RIT-B.
* **RIT Database Logging**: Automatically logs actual departure and arrival times to the database under the `rit_runs` table.
* **RIT Reports Portal**: Search, filter, and review logs of completed and ongoing RIT runs with automatic cleanup (retains data for 4 days).

### 6. Robust Offline Catch-Up Replay
* **Telemetry Gap Prevention**: If the simulator is restarted or loses connection, it calculates the duration it was offline.
* **Buffer Playback**: Replays up to 200 missed positions with correct historical timestamps at rapid 0.05-second intervals to restore state continuity on the Traccar map.

---

## 🛠️ Tech Stack

* **Frontend**: HTML5, Vanilla CSS3 (Custom Glassmorphic styles, Dark Theme), Javascript (ES6), Leaflet.js (Map rendering & layers)
* **Backend**: Python 3, Flask (REST APIs & session management), Flask-CORS, Threading
* **Database**: SQLite3 (persistent storage for settings, devices, and reports)
* **Routing**: OSRM (Open Source Routing Machine) API

---

## 📁 Directory Structure

```text
├── simulator_server.py         # Main Flask server & simulation runners thread manager
├── database.py                 # SQLite database schema, migrations, and query interfaces
├── map.html                    # Main Leaflet Control Panel UI
├── login.html                  # Glassmorphic Login UI
├── requirements.txt            # Python dependencies
├── simulator.db                # SQLite database file (generated automatically)
├── placesubplace29june2026.json # Predefined places and subplaces database seed file
├── routes/                     # Local cache directory for GeoJSON and JSON routes
└── state/                      # Local cache directory for device simulation state checkpoints
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

## 💾 Production Deployment & STB Details

In the production environment, the project is deployed on a Set Top Box (STB) running Docker.

* **STB IP Address**: `192.168.18.8`
* **Production Path**: `/mnt/usb-docker/IhsanTraccarDeviceSimulator`
* **System Service Aliases** (defined in `~/.zshrc`):
  * `sshstb`: Logs into the STB via SSH (`ssh root@192.168.18.8`)

### Syncing Data from STB to Local
To fetch the latest production database and cached route files to your local environment, use `rsync` via `sshpass` (password: `ihsan123`):
```bash
# Sync SQLite database
sshpass -p 'ihsan123' rsync -avz -e "ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no" root@192.168.18.8:/mnt/usb-docker/IhsanTraccarDeviceSimulator/simulator.db ./

# Sync cached routes
sshpass -p 'ihsan123' rsync -avz -e "ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no" root@192.168.18.8:/mnt/usb-docker/IhsanTraccarDeviceSimulator/routes/ ./routes/

# Sync active tracking states
sshpass -p 'ihsan123' rsync -avz -e "ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no" root@192.168.18.8:/mnt/usb-docker/IhsanTraccarDeviceSimulator/state/ ./state/
```

---

## 🧭 How to Use

1. Open your browser and navigate to `http://localhost:8083`.
2. Login with the credentials:
   * **Username**: `admin`
   * **Password**: `ihsan456`
3. Set your Traccar Server host (e.g. `tracking.misbahulihsan.com`) in the settings.
4. Click **+ Add Device** to register a new vehicle simulator:
   * Select a **Vehicle Type** (Car, Motorcycle, Bus).
   * Pick **Start/End Coordinates** directly by clicking the "Pick on Map" button and selecting locations on the map. Or choose **Multiple** route mode to add multiple manual waypoints, or select **Selected Route** to pick coordinates from predefined Place & Subplace dropdown selectors.
   * Configure **Trip Type** (Single or Nonstop) and set the relevant scheduled departure/arrival times for RIT-A and RIT-B.
5. Click **Save & Start**. The simulator will fetch the route, cache it, and begin transmitting positions to your Traccar Server.
6. Monitor live progress, speed, bearing, and distance directly on the map.
