#!/usr/bin/env python3
"""
Main WMS Application Entrypoint
Class-based FastAPI Server integrating FIFO Manager, QR Camera Manager, and Manual Service.
"""

import os
import sys
import time
import uvicorn
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

# Ensure scripts/ directory is first in sys.path so modules resolve directly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "scripts" else CURRENT_DIR

while CURRENT_DIR in sys.path:
    sys.path.remove(CURRENT_DIR)
sys.path.insert(0, CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

import cv2
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fifo_manager import FIFOManager, FIFO
from qr_camera import QRCameraManager, QRCamera, list_available_cameras
from manual import ManualService, ManualReader


def get_default_base_dir() -> str:
    """Resolve project base directory (parent of scripts directory)."""
    curr = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(curr) == "scripts":
        return os.path.dirname(curr)
    return curr


class WMSApplication:
    """
    Class-based Main WMS Application coordinating feature classes and web routes.
    
    Feature Architecture:
    - FIFO Core:        FIFOManager    (fifo_manager.py)
    - Optical Scanner:  QRCameraManager (qr_camera.py)
    - Manual Docs:      ManualService  (manual.py)
    - Future Features:  Easily pluggable via self.register_feature(...)
    """

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or get_default_base_dir()
        
        # 1. Feature Registry & Core Feature Classes
        self.features: Dict[str, Any] = {}
        
        self.fifo_manager = FIFOManager(base_dir=self.base_dir)
        self.camera_manager = QRCameraManager(base_dir=self.base_dir)
        self.manual_service = ManualService(base_dir=self.base_dir)

        # Register core features
        self.register_feature("fifo", self.fifo_manager)
        self.register_feature("camera", self.camera_manager)
        self.register_feature("manual", self.manual_service)

        # 2. Initialize Templates & Static Directories
        self.templates_dir = os.path.join(self.base_dir, "templates")
        self.static_dir = os.path.join(self.base_dir, "static")
        self.templates = Jinja2Templates(directory=self.templates_dir)

        # 3. Lifespan & FastAPI App
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            yield
            self.camera_manager.release()
            for feat in self.features.values():
                if hasattr(feat, "release") and callable(feat.release):
                    try:
                        feat.release()
                    except Exception:
                        pass

        self.app = FastAPI(title="NEXT Feature - Modular WMS & Vision Platform", lifespan=lifespan)
        
        # Setup mounts, routes, and background services
        self._setup_mounts()
        self._setup_routes()
    def register_feature(self, name: str, feature_instance: Any):
        """Register a new feature class service into the WMS application."""
        self.features[name] = feature_instance
        return feature_instance

    def get_feature(self, name: str) -> Optional[Any]:
        """Retrieve a registered feature service by name."""
        return self.features.get(name)

    def _setup_mounts(self):
        """Mount static assets and captures directories."""
        if os.path.exists(self.static_dir):
            self.app.mount("/static", StaticFiles(directory=self.static_dir), name="static")
        if os.path.exists(self.camera_manager.captures_dir):
            self.app.mount("/captures", StaticFiles(directory=self.camera_manager.captures_dir), name="captures")

    def _start_background_servers(self):
        """Start manual documentation reader server on background thread if enabled."""
        if os.environ.get("DISABLE_MANUAL_SERVER") != "true":
            self.manual_service.run_server_in_thread()

    def _setup_routes(self):
        """Register all HTTP endpoints."""
        app = self.app
        fifo = self.fifo_manager
        cam = self.camera_manager
        manual = self.manual_service
        templates = self.templates

        # ---------------------------------------------------------------------
        # Web UI Routes
        # ---------------------------------------------------------------------
        @app.get("/", response_class=HTMLResponse)
        def index(request: Request):
            """Render the modular dashboard UI."""
            return templates.TemplateResponse(request=request, name="index.html")

        @app.get("/api/manual", response_class=PlainTextResponse)
        @app.get("/api/readme", response_class=PlainTextResponse)
        def get_manual():
            """Return markdown documentation contents."""
            return manual.get_readme_markdown()

        @app.get("/manual", response_class=HTMLResponse)
        def get_manual_page():
            """Return standalone user manual HTML on port 8000."""
            return manual.get_manual_html()

        # ---------------------------------------------------------------------
        # Core WMS & Inventory Routes
        # ---------------------------------------------------------------------
        @app.get("/slots")
        def get_slots():
            return fifo.get_slots_data()

        @app.post("/slot/suggest")
        def suggest(req: dict):
            item = req.get("item_type", "").strip()
            user_id = req.get("user_id", "")
            if not item:
                raise HTTPException(400, "Item empty")
            matches = fifo.suggest_slots(item, user_id)
            if not matches:
                raise HTTPException(404, "No slots found")
            return {"slots": matches}

        @app.post("/slot/drop")
        def drop(req: dict):
            point_name = req.get("point_name")
            item_type = req.get("item_type")
            user_id = req.get("user_id")
            note = req.get("note", "")
            try:
                return fifo.drop_item(point_name, item_type, user_id, note)
            except ValueError as ve:
                raise HTTPException(400, str(ve))

        @app.post("/item/pickup")
        def pickup(req: dict):
            item_type = req.get("item_type")
            user_id = req.get("user_id")
            try:
                return fifo.pickup_item(item_type, user_id)
            except KeyError:
                raise HTTPException(404, "Stock not found")

        @app.post("/slot/reset")
        def reset(req: dict):
            fifo.reset_slot(req.get("point_name", ""))
            return {"message": "Reset"}

        @app.post("/slot/confirm")
        def confirm(req: dict):
            point_name = req.get("point_name")
            try:
                return fifo.confirm_slot(point_name)
            except ValueError as ve:
                raise HTTPException(400, str(ve))
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.post("/config/update/users")
        def update_users_route(payload: dict):
            fifo.update_users(payload.get("users", []))
            return {"status": "OK"}

        @app.post("/config/update")
        def update_config_route(payload: dict):
            fifo.update_config(payload)
            return {"status": "OK"}

        @app.get("/history")
        def get_history_route(limit: int = 100):
            return {"history": fifo.get_history(limit)}

        @app.post("/sensor/state")
        def receive_sensor(data: dict):
            fifo.set_sensor_state(data.get("sensor_id"), data.get("detected", False))
            return {"status": "ok", "timestamp": time.time()}

        @app.get("/sensor/status")
        def sensor_status():
            return fifo.get_sensors_status()

        # ---------------------------------------------------------------------
        # QR Code & Camera Routes
        # ---------------------------------------------------------------------
        @app.api_route("/read", methods=["GET", "POST"])
        def read_qr_endpoint(retries: int = 3, retry_interval: float = 0.2, payload: Optional[dict] = None):
            """Scan and decode QR code from camera."""
            if payload:
                retries = payload.get("retries", retries)
                retry_interval = payload.get("retry_interval", retry_interval)

            if not cam.is_ready():
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "error_code": "CAMERA_NOT_READY",
                        "message": "Camera is disconnected or frame grabber is failing",
                        "timestamp": time.time()
                    }
                )

            try:
                text = cam.read_qr(retries=retries, retry_interval=retry_interval)
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "error_code": "SCAN_ERROR",
                        "message": str(e),
                        "timestamp": time.time()
                    }
                )

            if text is not None:
                parsed = fifo.parse_qr_payload(text)
                return {
                    "status": "ok",
                    "data": text,
                    "parsed": parsed,
                    "timestamp": time.time()
                }

            return {
                "status": "no_qr",
                "message": "No QR code detected after retries",
                "timestamp": time.time()
            }

        @app.get("/video_feed")
        def video_feed():
            """Live MJPEG video stream feed."""
            return StreamingResponse(
                cam.generate_mjpeg_stream(),
                media_type="multipart/x-mixed-replace; boundary=frame"
            )

        @app.api_route("/cap_screen", methods=["GET", "POST"])
        def cap_screen(raw: Optional[str] = None, image: Optional[str] = None, json_mode: Optional[str] = None):
            """Retrieve last captured QR frame image or metadata."""
            frame, data, timestamp, filename = cam.get_last_qr_capture()
            if raw == "1" or image == "1":
                if frame is None:
                    raise HTTPException(404, "No QR capture available yet")
                ret, buffer = cv2.imencode('.jpg', frame)
                return Response(content=buffer.tobytes(), media_type="image/jpeg")

            if frame is None:
                return {"status": "no_capture", "message": "No QR code frame has been captured yet"}

            return {
                "status": "ok",
                "qr_data": data,
                "timestamp": timestamp,
                "filename": filename,
                "image_url": f"/captures/{filename}" if filename else "/cap_screen?raw=1"
            }

        @app.get("/cameras")
        def get_cameras():
            return {
                "status": "ok",
                "active_index": cam.index,
                "enabled": cam.running,
                "available_cameras": list_available_cameras()
            }

        @app.post("/camera/enable")
        def enable_camera():
            success = cam._ensure_camera_active()
            return {"status": "ok" if success else "camera_unavailable", "enabled": bool(cam.running), "active_index": cam.index}

        @app.post("/camera/disable")
        def disable_camera():
            cam.stop_camera()
            return {"status": "ok", "enabled": False, "active_index": cam.index}

        @app.post("/camera/toggle")
        def toggle_camera():
            if cam.running:
                cam.stop_camera()
                return {"status": "ok", "enabled": False}
            else:
                success = cam._ensure_camera_active()
                return {"status": "ok" if success else "camera_unavailable", "enabled": bool(cam.running)}

        @app.post("/cameras/switch")
        def switch_camera(payload: dict):
            new_idx = payload.get("index")
            if new_idx is None:
                raise HTTPException(400, "Missing 'index' parameter")
            try:
                active_idx = cam.switch_camera(int(new_idx))
                return {
                    "status": "ok",
                    "message": f"Switched to camera index {active_idx}",
                    "active_index": active_idx
                }
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/camera/settings")
        @app.get("/settings")
        def get_camera_settings():
            return cam.get_settings()

        @app.post("/camera/settings")
        @app.post("/settings")
        def update_camera_settings(payload: dict):
            updated = cam.update_settings(payload)
            return {"status": "ok", "settings": updated}

        @app.post("/camera/settings/auto_adjust")
        @app.post("/settings/auto_adjust")
        def auto_adjust_camera():
            new_settings = cam.auto_adjust_settings()
            return {
                "status": "ok",
                "message": "V4L2 Hardware Auto-Adjust baseline calculated and applied",
                "settings": new_settings
            }

        @app.post("/camera/settings/reset")
        @app.post("/settings/reset")
        def reset_camera_settings():
            defaults = cam.reset_to_factory()
            return {
                "status": "ok",
                "message": "Camera hardware & software restored to dynamic camera defaults",
                "settings": defaults
            }

        @app.get("/camera/profiles")
        @app.get("/profiles")
        def list_profiles():
            return {"status": "ok", "profiles": cam.list_profiles()}

        @app.post("/camera/profiles/save")
        @app.post("/profiles/save")
        def save_profile(payload: dict):
            pname = payload.get("name") or payload.get("profile_name")
            saved_data = cam.save_profile(name=pname, new_settings=payload)
            return {
                "status": "ok",
                "message": f"Camera setup saved to profile file {saved_data.get('filename')}",
                "data": saved_data
            }

        @app.post("/camera/profiles/load")
        @app.post("/profiles/load")
        def load_profile(payload: dict):
            target = payload.get("name") or payload.get("filename") or payload.get("profile_name")
            if not target:
                raise HTTPException(400, "Missing 'name' or 'filename' parameter")
            try:
                active_settings = cam.load_profile(target)
                return {
                    "status": "ok",
                    "message": f"Profile '{target}' loaded and applied successfully",
                    "settings": active_settings
                }
            except FileNotFoundError as e:
                raise HTTPException(404, str(e))
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/camera/health")
        @app.get("/health")
        def health_check():
            return cam.get_health()

        @app.get("/ping")
        def ping():
            return {"status": "pong", "timestamp": time.time()}

        # ---------------------------------------------------------------------
        # Smart QR Workflow Routes
        # ---------------------------------------------------------------------
        @app.post("/slot/drop/scan")
        def drop_via_qr(payload: Optional[dict] = None):
            """Scan QR barcode via camera and suggest or reserve drop slot."""
            payload = payload or {}
            user_id = payload.get("user_id") or (fifo.users_db[0]["user_id"] if fifo.users_db else "operator")
            note = payload.get("note", "")

            if not cam.is_ready():
                raise HTTPException(503, "Camera not ready for QR scan")

            text = cam.read_qr(retries=payload.get("retries", 3), retry_interval=payload.get("retry_interval", 0.2))
            if not text:
                return {"status": "no_qr", "message": "No QR code detected"}

            parsed = fifo.parse_qr_payload(text)
            item_type = parsed["item_type"]
            if not item_type:
                return {"status": "error", "message": f"Could not determine item type from QR: '{text}'"}

            target_slot = parsed["point_name"] or payload.get("point_name")
            if parsed["note"]:
                note = f"{note} | {parsed['note']}" if note else parsed["note"]
            if parsed["user_id"]:
                user_id = parsed["user_id"]

            if target_slot:
                s = fifo.find_slot(target_slot)
                if s and s.get("enabled", True):
                    return fifo.drop_item(target_slot, item_type, user_id, note)

            matches = fifo.suggest_slots(item_type, user_id)
            return {
                "status": "SCANNED",
                "qr_data": text,
                "item_type": item_type,
                "suggested_slots": matches,
                "message": f"Scanned '{item_type}'. Found {len(matches)} matching slot(s)"
            }

        @app.post("/item/pickup/scan")
        def pickup_via_qr(payload: Optional[dict] = None):
            """Scan QR barcode via camera and dispatch oldest item in FIFO order."""
            payload = payload or {}
            user_id = payload.get("user_id") or (fifo.users_db[0]["user_id"] if fifo.users_db else "operator")

            if not cam.is_ready():
                raise HTTPException(503, "Camera not ready for QR scan")

            text = cam.read_qr(retries=payload.get("retries", 3), retry_interval=payload.get("retry_interval", 0.2))
            if not text:
                return {"status": "no_qr", "message": "No QR code detected"}

            parsed = fifo.parse_qr_payload(text)
            item_type = parsed["item_type"]
            if not item_type:
                return {"status": "error", "message": f"Could not determine item type from QR: '{text}'"}

            if parsed["user_id"]:
                user_id = parsed["user_id"]

            return fifo.pickup_item(item_type, user_id)


# Instantiate the application
wms_app = WMSApplication()
app = wms_app.app

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
