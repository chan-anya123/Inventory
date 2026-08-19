# 🚀 NEXT Feature - Modular WMS & Optical Vision Platform

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![OpenCV](https://img.shields.io/badge/OpenCV-V4L2_Vision-5C3EE8.svg?logo=opencv&logoColor=white)](https://opencv.org)
[![Vue 3](https://img.shields.io/badge/Vue.js-3.0_SPA-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-Pastel_UI-38B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com)

**NEXT Feature** is an enterprise-grade, modular warehouse inventory control system and standalone optical vision processing platform. Built using a class-based, decoupled architecture with **FastAPI**, **OpenCV**, and **Vue 3**, it delivers high-performance inventory management and optical recognition while keeping modules completely independent and extensible.

---

## 🌟 Key Highlights & Architectural Features

```
                                  ┌─────────────────────────────────────────┐
                                  │      WMSApplication (main.py)           │
                                  │   FastAPI Web Server & UI Orchestrator  │
                                  └────┬─────────────────┬────────────────┬─┘
                                       │                 │                │
                   ┌───────────────────┴───┐     ┌───────┴──────┐   ┌─────┴──────────────────┐
                   │     FIFOManager       │     │ ManualService│   │    QRCameraManager     │
                   │ (scripts/fifo_manager)│     │(scripts/man..)│  │  (scripts/qr_camera)   │
                   └───────────┬───────────┘     └───────┬──────┘   └─────────────┬──────────┘
                               │                         │                        │
                    📦 Storage / Drops / Queues    📖 User Docs         📷 Standby / V4L2 Resets
```

1. **Decoupled 100% Modular Architecture**:
   - Core backend logic is cleanly separated into specialized classes located in `scripts/`:
     - [`FIFOManager`](scripts/fifo_manager.py): Pure FIFO queue management, priority reservation, node capacity limits, and audit logs.
     - [`QRCameraManager`](scripts/qr_camera.py): Standalone optical vision studio, real-time video decoder, physical Linux V4L2 register control, and setup profile manager.
     - [`ManualService`](scripts/manual.py): Markdown documentation reader and background manual server.
     - [`WMSApplication`](scripts/main.py): Central orchestrator managing HTTP routes, Jinja2 template rendering, static file mounts, and modern FastAPI lifespan lifecycle handlers.

2. **On-Demand (Lazy) Camera Hardware Lifecycle**:
   - Prevents multi-process device locks (`[Errno 98] Device Busy`) by launching in **`STANDBY`** mode on application startup without holding `/dev/video*`.
   - Opens the camera device strictly when a client requests `/video_feed`, `/read`, or `/camera/settings`, and automatically releases hardware back to the operating system after an idle timeout.

3. **Physical Hardware-Level V4L2 Register Resets**:
   - Queries the Linux kernel V4L2 controls directly (`v4l2-ctl --list-ctrls`) and restores native hardware manufacturer default registers whenever a device is activated or switched.
   - Camera never auto-tunes or alters settings on its own; settings remain clean and fixed until a custom profile is applied or the user triggers manual adjustments.

4. **Modular Single-Page Architecture (SPA)**:
   - Built on Vue 3 and Tailwind CSS with a **Collapsible Dropdown Accordion Sidebar**.
   - Expandable and scalable for adding dozens of new features without cluttering the screen.

---

## 📂 Project Structure

```
all_features/
├── captures/                           # Annotated snapshots of scanned barcodes/QR codes
│   └── qr_box.jpg
├── data/                               # Persistent runtime state & config files
│   ├── config.json                     # FIFO nodes & user permissions
│   ├── history.csv                     # Audit trail of inventory drop/pickup actions
│   ├── camera_setup.json               # Active camera settings
│   └── camera_setups/                  # Named vision profiles (JSON)
│       └── camera_setup_cam0.json
├── scripts/                            # Core Python backend classes
│   ├── __init__.py                     # Package export module
│   ├── fifo_manager.py                 # FIFOManager & inventory management logic
│   ├── qr_camera.py                    # QRCameraManager & V4L2 hardware vision engine
│   ├── manual.py                       # ManualService documentation reader
│   └── main.py                         # WMSApplication class & server entrypoint
├── static/                             # Frontend assets, icons, and branding logos
│   ├── white_logo.svg
│   └── *.png
├── templates/                          # Modular Jinja2 + Vue 3 templates
│   ├── components/                     # Reusable UI partials
│   │   ├── sidebar.html                # Collapsible Dropdown Accordion Navigation
│   │   └── header.html                 # Warehouse Status & Operator Badge
│   ├── pages/                          # Dedicated full-page feature views
│   │   ├── dashboard.html              # FIFO Inventory Flow & Drop/Pickup Dashboard
│   │   ├── config.html                 # FIFO Storage Nodes & Operator Settings
│   │   ├── activity_log.html           # Historical Audit Log & CSV Export
│   │   ├── qr_scanner.html             # Dedicated Optical Scanner Studio View
│   │   ├── qr_config.html              # Hardware Device & Image Filter Tuning View
│   │   └── manual_view.html            # Native Markdown Documentation View
│   ├── index.html                      # Main single-page application layout
│   └── manual.html                     # Standalone full-page user manual
├── MANUAL.md                           # System documentation in Markdown
├── README.md                           # Project technical overview
├── requirements.txt                    # Python dependencies
├── Dockerfile                          # Container specification with V4L2 & OpenCV
└── docker-compose.yml                  # Multi-container orchestration
```

---

## ⚡ Quick Start & Execution

### 1. Prerequisites
- **Python 3.10+**
- **V4L2 Utilities**: `sudo apt update && sudo apt install -y v4l2-utils libzbar0`

### 2. Environment Setup & Installation
```bash
# Clone or navigate to the project directory
cd /home/cookies/fifo/all_features

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Application
You can run the server directly from the `scripts/` directory or from the project root:

```bash
# Run from scripts directory:
cd /home/cookies/fifo/all_features/scripts
python3 main.py

# OR run with uvicorn from project root:
cd /home/cookies/fifo/all_features
python3 scripts/main.py
```

### 4. Access the Web Interfaces
| Service / View | URL | Description |
| :--- | :--- | :--- |
| **NEXT Feature Web App** | `http://localhost:8000/` | Main Single-Page UI (FIFO, Scanner Studio, Config) |
| **In-App User Manual** | `http://localhost:8000/` (Menu: *User Manual*) | Native in-page rendered documentation |
| **Standalone Full Manual** | `http://localhost:8000/manual` | Standalone full-page documentation |
| **Dedicated Docs Server** | `http://localhost:8081/` | Background documentation reader server |

---

## 🧭 Navigation & Feature Modules

The sidebar is organized into collapsible accordion dropdowns:

```
📦 NEXT Feature (Sidebar Navigation)
├── [▼] 📦 FIFO System
│   ├── • FIFO Dashboard       (Drop & Pickup Operations, Inventory Flow Table)
│   ├── • FIFO Config          (Storage Nodes, Allowed Items, Priority Users, Sensors)
│   └── • Activity Log         (Audit Trail, Filtering, CSV Export)
│
├── [▼] 📷 QR Scanner
│   ├── • Scanner Studio       (Live Video Feed, Instant Barcode Decoder, Raw Payload Inspector)
│   └── • Camera Config        (V4L2 Hardware Controls, Brightness/Contrast Sliders, Presets)
│
└── [▼] 📖 Documentation
    └── • User Manual          (System Guide, API Documentation & Shortcuts)
```

---

## 📡 RESTful API Reference

### 📦 1. FIFO & Inventory Management (`FIFOManager`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/slots` | Retrieve current status of all storage slots and items |
| `POST` | `/slot/suggest` | Get recommended storage slot for incoming item type |
| `POST` | `/slot/drop` | Execute item drop into designated storage slot |
| `POST` | `/slot/pickup` | Execute FIFO pickup for item type (earliest timestamp first) |
| `POST` | `/slot/clear` | Clear all items from a storage slot |
| `GET` | `/config` | Retrieve current storage nodes and user configurations |
| `POST` | `/config/update` | Update storage nodes, allowed item mappings, or users |
| `GET` | `/history` | Fetch historical transaction log |
| `POST` | `/sensor/state` | Update hardware photoelectric sensor state |
| `GET` | `/sensor/status`| Retrieve hardware sensor status |

### 📷 2. Optical Scanner & Vision Engine (`QRCameraManager`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/video_feed` | MJPEG multipart live video stream (activates camera on-demand) |
| `GET` | `/read`, `POST /read` | Trigger optical decode across consecutive frames |
| `GET` | `/cap_screen` | Return latest captured snapshot image |
| `GET` | `/cameras` | List connected video capture devices (`/dev/video*`) |
| `POST` | `/cameras/switch` | Switch active camera index and reset to hardware defaults |
| `POST` | `/camera/enable` | Manually activate camera video feed |
| `POST` | `/camera/disable` | Manually put camera into standby and release hardware |
| `POST` | `/camera/toggle` | Toggle camera active/standby state |
| `GET` | `/camera/settings` | Retrieve active image settings (Brightness, Contrast, Exposure, Threshold) |
| `POST` | `/camera/settings` | Apply custom image enhancement settings |
| `POST` | `/camera/settings/auto_adjust` | Trigger on-demand optical vision baseline calculation |
| `POST` | `/camera/settings/reset` | Reset device directly to manufacturer factory defaults via V4L2 |
| `GET` | `/camera/profiles` | List all saved camera preset profiles |
| `POST` | `/camera/profiles/save` | Save current camera tuning into a named JSON profile |
| `POST` | `/camera/profiles/load` | Load and apply a saved JSON preset profile |
| `GET` | `/camera/health` | Diagnostic metrics (uptime, latency, connection status) |

### 📖 3. Documentation (`ManualService`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/manual`, `/api/readme` | Plain-text Markdown of system documentation |
| `GET` | `/manual` | Standalone rendered HTML user manual on port 8000 |

---

## 🐳 Docker Deployment

The application includes a production-ready `Dockerfile` and `docker-compose.yml` configured for V4L2 device passthrough:

```yaml
version: '3.8'
services:
  next-feature:
    build: .
    container_name: next_feature_wms
    restart: unless-stopped
    ports:
      - "8000:8000"
      - "8081:8081"
    devices:
      - "/dev/video0:/dev/video0"
    volumes:
      - ./data:/app/data
      - ./captures:/app/captures
```

Run container with:
```bash
docker compose up -d
```

---

## 🛠️ Technology Stack

- **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com) + [Starlette](https://www.starlette.io) + [Uvicorn](https://www.uvicorn.org)
- **Computer Vision**: [OpenCV](https://opencv.org) + [pyzbar](https://github.com/NaturalHistoryMuseum/pyzbar) + Linux `v4l2-ctl`
- **Frontend SPA**: [Vue.js 3](https://vuejs.org) (Reactive Composition & Options API)
- **Styling & Icons**: [Tailwind CSS](https://tailwindcss.com) + Custom Modern Palette
- **Documentation Engine**: [Marked.js](https://marked.js.org) + [Mermaid.js](https://mermaid.js.org)

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
